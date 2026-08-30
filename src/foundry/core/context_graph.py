"""ContextGraph — symbol-level repository understanding.

The ContextGraph builds a queryable graph of symbols (functions, classes,
methods, variables) and their relationships (calls, imports, inherits, uses).
This enables intelligent context assembly: instead of stuffing 100 files into
a prompt, the system queries the graph for the most relevant symbols.

Architecture reference:
    L5 Context & Memory — "Repository graph query → top relevant symbols → context assembly"
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.context_graph")


# --------------------------------------------------------------------------- #
#  Symbol types and relationships
# --------------------------------------------------------------------------- #


class SymbolKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    MODULE = "module"
    IMPORT = "import"


class RelationshipKind(StrEnum):
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    USES = "uses"
    DEFINES = "defines"
    DECORATES = "decorates"
    RETURNS = "returns"
    YIELDS = "yields"
    RAISES = "raises"
    ASSIGNS = "assigns"


@dataclass(frozen=True)
class Symbol:
    """A code symbol (function, class, method, etc.)."""

    name: str
    kind: SymbolKind
    file_path: str
    line_start: int
    line_end: int
    docstring: str | None = None
    parent_class: str | None = None  # For methods
    parent_module: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Fully qualified name (e.g. 'module.Class.method')."""
        parts = []
        if self.parent_module:
            parts.append(self.parent_module)
        if self.parent_class:
            parts.append(self.parent_class)
        parts.append(self.name)
        return ".".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "parent_class": self.parent_class,
            "parent_module": self.parent_module,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class Relationship:
    """A relationship between two symbols."""

    source: str  # qualified name of source symbol
    target: str  # qualified name of target symbol
    kind: RelationshipKind
    file_path: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "file_path": self.file_path,
            "line": self.line,
        }


# --------------------------------------------------------------------------- #
#  ContextGraph
# --------------------------------------------------------------------------- #


class ContextGraph:
    """Queryable graph of symbols and their relationships.

    Usage::

        graph = ContextGraph()
        graph.add_file("src/auth.py", content)
        graph.add_file("src/api.py", content)

        # Query for relevant symbols
        symbols = graph.query("authentication login")
        # Returns: [Symbol(name="authenticate_user", ...), ...]

        # Get call graph for a symbol
        callers = graph.get_callers("authenticate_user")
        callees = graph.get_callees("authenticate_user")
    """

    def __init__(self) -> None:
        self._symbols: dict[str, Symbol] = {}  # qualified_name → Symbol
        self._relationships: list[Relationship] = []
        self._file_symbols: dict[str, list[str]] = defaultdict(list)  # file → [qualified_names]
        self._name_index: dict[str, list[str]] = defaultdict(list)  # lower_name → [qualified_names]

    def add_file(self, file_path: str, content: str) -> int:
        """Parse a file and add its symbols and relationships to the graph.

        Returns the number of symbols added.
        """
        symbols = self._parse_symbols(file_path, content)
        relationships = self._parse_relationships(file_path, content, symbols)

        count = 0
        for sym in symbols:
            self._symbols[sym.qualified_name] = sym
            self._file_symbols[file_path].append(sym.qualified_name)
            self._name_index[sym.name.lower()].append(sym.qualified_name)
            count += 1

        self._relationships.extend(relationships)
        return count

    def add_symbols(self, symbols: list[Symbol], relationships: list[Relationship]) -> None:
        """Bulk-add symbols and relationships."""
        for sym in symbols:
            self._symbols[sym.qualified_name] = sym
            self._file_symbols[sym.file_path].append(sym.qualified_name)
            self._name_index[sym.name.lower()].append(sym.qualified_name)
        self._relationships.extend(relationships)

    def query(self, text: str, limit: int = 10) -> list[Symbol]:
        """Query for symbols relevant to a text prompt.

        Uses name matching and docstring matching to find relevant symbols.
        """
        words = set(text.lower().split())
        scored: list[tuple[float, str]] = []

        for qname, sym in self._symbols.items():
            score = 0.0

            # Name match
            name_lower = sym.name.lower()
            for word in words:
                if word in name_lower:
                    score += 2.0

            # Docstring match
            if sym.docstring:
                doc_lower = sym.docstring.lower()
                for word in words:
                    if word in doc_lower:
                        score += 1.0

            # Qualified name match
            for word in words:
                if word in qname.lower():
                    score += 0.5

            if score > 0:
                scored.append((score, qname))

        # Sort by score, return top N
        scored.sort(reverse=True)
        return [
            self._symbols[qname]
            for _, qname in scored[:limit]
        ]

    def get_symbol(self, qualified_name: str) -> Symbol | None:
        """Get a symbol by its qualified name."""
        return self._symbols.get(qualified_name)

    def get_callers(self, qualified_name: str) -> list[Symbol]:
        """Get all symbols that call the given symbol."""
        callers = set()
        for rel in self._relationships:
            if rel.target == qualified_name and rel.kind == RelationshipKind.CALLS:
                if rel.source in self._symbols:
                    callers.add(rel.source)
        return [self._symbols[qn] for qn in callers if qn in self._symbols]

    def get_callees(self, qualified_name: str) -> list[Symbol]:
        """Get all symbols called by the given symbol."""
        callees = set()
        for rel in self._relationships:
            if rel.source == qualified_name and rel.kind == RelationshipKind.CALLS:
                if rel.target in self._symbols:
                    callees.add(rel.target)
        return [self._symbols[qn] for qn in callees if qn in self._symbols]

    def get_imports(self, qualified_name: str) -> list[Symbol]:
        """Get all symbols imported by the given symbol."""
        imports = set()
        for rel in self._relationships:
            if rel.source == qualified_name and rel.kind == RelationshipKind.IMPORTS:
                if rel.target in self._symbols:
                    imports.add(rel.target)
        return [self._symbols[qn] for qn in imports if qn in self._symbols]

    def get_inherits(self, qualified_name: str) -> list[Symbol]:
        """Get all classes inherited by the given class."""
        inherits = set()
        for rel in self._relationships:
            if rel.source == qualified_name and rel.kind == RelationshipKind.INHERITS:
                if rel.target in self._symbols:
                    inherits.add(rel.target)
        return [self._symbols[qn] for qn in inherits if qn in self._symbols]

    def get_file_symbols(self, file_path: str) -> list[Symbol]:
        """Get all symbols in a file."""
        qnames = self._file_symbols.get(file_path, [])
        return [self._symbols[qn] for qn in qnames if qn in self._symbols]

    def search_by_name(self, name: str) -> list[Symbol]:
        """Search symbols by name (case-insensitive substring match)."""
        name_lower = name.lower()
        return [
            sym for sym in self._symbols.values()
            if name_lower in sym.name.lower()
        ]

    @property
    def stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        kind_counts = defaultdict(int)
        for sym in self._symbols.values():
            kind_counts[sym.kind.value] += 1

        rel_counts = defaultdict(int)
        for rel in self._relationships:
            rel_counts[rel.kind.value] += 1

        return {
            "total_symbols": len(self._symbols),
            "total_relationships": len(self._relationships),
            "symbols_by_kind": dict(kind_counts),
            "relationships_by_kind": dict(rel_counts),
            "files_indexed": len(self._file_symbols),
        }

    # -- Parsing (Python-specific) ------------------------------------------ #

    def _parse_symbols(self, file_path: str, content: str) -> list[Symbol]:
        """Parse Python source to extract symbols."""
        symbols: list[Symbol] = []
        lines = content.split("\n")
        module_name = Path(file_path).stem

        current_class: str | None = None
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            # Class definition
            class_match = re.match(r"^class\s+(\w+)", stripped)
            if class_match:
                class_name = class_match.group(1)
                current_class = class_name

                # Find docstring
                docstring = self._extract_docstring(lines, i + 1)

                # Find end of class (next class or end of indent)
                line_end = self._find_block_end(lines, i)

                symbols.append(Symbol(
                    name=class_name,
                    kind=SymbolKind.CLASS,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end + 1,
                    docstring=docstring,
                    parent_module=module_name,
                ))
                # Don't skip — continue processing methods inside the class
                i += 1
                continue

            # If we hit something at top-level (not indented), we're outside the class
            if not line.startswith(" ") and not line.startswith("\t") and stripped:
                current_class = None

            # Function/method definition
            func_match = re.match(r"^(\s*)def\s+(\w+)\s*\(", stripped)
            if func_match:
                indent = len(func_match.group(1))
                func_name = func_match.group(2)

                # Skip dunder methods (except __init__)
                if func_name.startswith("__") and func_name.endswith("__") and func_name != "__init__":
                    i += 1
                    continue

                docstring = self._extract_docstring(lines, i + 1)
                line_end = self._find_block_end(lines, i)

                kind = SymbolKind.METHOD if current_class else SymbolKind.FUNCTION

                symbols.append(Symbol(
                    name=func_name,
                    kind=kind,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end + 1,
                    docstring=docstring,
                    parent_class=current_class,
                    parent_module=module_name if not current_class else None,
                ))
                i = line_end + 1
                continue

            i += 1

        return symbols

    def _extract_docstring(self, lines: list[str], start: int) -> str | None:
        """Extract docstring from lines following a definition."""
        for i in range(start, min(start + 5, len(lines))):
            stripped = lines[i].strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # Single-line docstring
                if stripped.count(stripped[:3]) >= 2:
                    return stripped[3:-3].strip()
                # Multi-line docstring — find end
                quote = stripped[:3]
                doc_lines = [stripped[3:]]
                for j in range(i + 1, min(i + 20, len(lines))):
                    if quote in lines[j]:
                        doc_lines.append(lines[j].split(quote)[0])
                        return "\n".join(doc_lines).strip()
                    doc_lines.append(lines[j].strip())
                return "\n".join(doc_lines).strip()
            elif stripped and not stripped.startswith("#"):
                break
        return None

    def _find_block_end(self, lines: list[str], start: int) -> int:
        """Find the last line of an indented block."""
        if start >= len(lines) - 1:
            return start

        # Get the indent of the definition line
        def_line = lines[start]
        base_indent = len(def_line) - len(def_line.lstrip())

        # Find where indent returns to base level
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _parse_relationships(
        self,
        file_path: str,
        content: str,
        symbols: list[Symbol],
    ) -> list[Relationship]:
        """Parse Python source to extract relationships between symbols."""
        relationships: list[Relationship] = []
        lines = content.split("\n")

        # Build a name → qualified_name map
        name_to_qname: dict[str, str] = {}
        for sym in symbols:
            name_to_qname[sym.name] = sym.qualified_name

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Import statements
            import_match = re.match(r"^(?:from\s+(\S+)\s+)?import\s+(.+)", stripped)
            if import_match:
                module = import_match.group(1) or ""
                names = import_match.group(2)
                for name in names.split(","):
                    name = name.strip().split(" as ")[0].strip()
                    if name in name_to_qname:
                        relationships.append(Relationship(
                            source=name_to_qname[name],
                            target=f"{module}.{name}" if module else name,
                            kind=RelationshipKind.IMPORTS,
                            file_path=file_path,
                            line=i + 1,
                        ))

            # Function calls (simple pattern)
            call_match = re.findall(r"(\w+)\s*\(", stripped)
            for called_name in call_match:
                if called_name in name_to_qname and called_name != "def":
                    # Find which symbol this call is in
                    caller = self._find_enclosing_symbol(i + 1, symbols)
                    if caller:
                        relationships.append(Relationship(
                            source=caller.qualified_name,
                            target=name_to_qname[called_name],
                            kind=RelationshipKind.CALLS,
                            file_path=file_path,
                            line=i + 1,
                        ))

            # Inheritance
            inherit_match = re.match(r"^class\s+(\w+)\s*\((.+)\)", stripped)
            if inherit_match:
                class_name = inherit_match.group(1)
                bases = inherit_match.group(2)
                for base in bases.split(","):
                    base = base.strip()
                    if base in name_to_qname:
                        relationships.append(Relationship(
                            source=name_to_qname[class_name],
                            target=name_to_qname[base],
                            kind=RelationshipKind.INHERITS,
                            file_path=file_path,
                            line=i + 1,
                        ))

        return relationships

    def _find_enclosing_symbol(self, line_num: int, symbols: list[Symbol]) -> Symbol | None:
        """Find the symbol that encloses the given line number."""
        for sym in symbols:
            if sym.line_start <= line_num <= sym.line_end:
                return sym
        return None
