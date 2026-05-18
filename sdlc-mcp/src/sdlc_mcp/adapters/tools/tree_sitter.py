from __future__ import annotations

import ast as _ast
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

from sdlc_mcp.adapters.base import ToolAdapter, ToolCapability
from sdlc_mcp.engine.dependency_graph import (
    _detect_language,
    parse_file,
)
from sdlc_mcp.log import get_logger
from sdlc_mcp.models import CodeSymbol, SymbolKind

log = get_logger("tree_sitter_adapter")


_CHUNK_SEPARATOR_RE = re.compile(r"\n\s*\n\s*(?:def |class |async def |@|\"\"\"|# |// )")


def _syntax_aware_chunk(content: str, max_lines: int = 50) -> list[tuple[int, int, str]]:
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[tuple[int, int, str]] = []
    start = 0

    positions = [m.start() for m in _CHUNK_SEPARATOR_RE.finditer(content)]
    positions.append(len(content))

    for pos in positions:
        chunk_line = content[:pos].count("\n")
        if chunk_line <= start:
            continue
        chunk_text = "\n".join(lines[start:chunk_line])
        if chunk_text.strip():
            chunks.append((start + 1, chunk_line, chunk_text))
        start = chunk_line

    if not chunks and content.strip():
        chunks.append((1, len(lines), content))

    merged: list[tuple[int, int, str]] = []
    for s, e, t in chunks:
        chunk_lines = t.splitlines()
        if len(chunk_lines) > max_lines:
            for i in range(0, len(chunk_lines), max_lines):
                sub_lines = chunk_lines[i : i + max_lines]
                sub_text = "\n".join(sub_lines)
                merged.append((s + i, s + i + len(sub_lines) - 1, sub_text))
        else:
            merged.append((s, e, t))

    return merged


class TreeSitterAdapter(ToolAdapter):
    """AST-based code analysis adapter using Python's built-in ast module."""

    name: str = "tree_sitter"
    capability: ToolCapability = ToolCapability.CODE_GRAPH

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        self._workspace = Path(workspace_path) if workspace_path else None

    async def validate(self, task: Any) -> bool:
        if isinstance(task, dict):
            return "path" in task or self._workspace is not None
        return self._workspace is not None

    async def execute(self, task: Any) -> dict[str, Any]:
        errors: list[str] = []
        files_parsed: list[dict[str, Any]] = []

        paths = self._resolve_paths(task)
        if not paths:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": "No paths provided",
                "details": {
                    "files": [],
                    "errors": ["No paths to analyze"],
                    "total_files": 0,
                    "total_symbols": 0,
                },
            }

        for path in paths:
            result = self._parse_file_safe(path)
            if result.get("error"):
                errors.append(result["error"])
            if result.get("file_index"):
                files_parsed.append(result["file_index"])

        total_symbols = sum(len(f.get("symbols", [])) for f in files_parsed)
        summary = (
            f"Parsed {len(files_parsed)} files, {total_symbols} symbols"
            if files_parsed
            else "No files parsed"
        )
        if errors:
            summary += f", {len(errors)} errors"

        return {
            "adapter": self.name,
            "capability": self.capability.value,
            "passed": len(errors) == 0,
            "summary": summary,
            "details": {
                "files": files_parsed,
                "errors": errors,
                "total_files": len(files_parsed),
                "total_symbols": total_symbols,
            },
        }

    async def healthcheck(self) -> bool:
        return True

    def _resolve_paths(self, task: Any) -> list[Path]:
        paths: list[Path] = []
        if isinstance(task, dict):
            raw = task.get("path", "")
            if raw:
                p = Path(raw)
                if p.is_dir():
                    paths.extend(
                        sorted(p.rglob("*"))
                        if task.get("recursive", True)
                        else list(p.iterdir()),
                    )
                elif p.exists():
                    paths.append(p)
        elif self._workspace:
            paths.append(self._workspace)

        exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java", ".rb"}
        return [p for p in paths if p.is_file() and p.suffix in exts]

    def _parse_file_safe(self, path: Path) -> dict[str, Any]:
        try:
            content = path.read_text(encoding="utf-8")
            if _detect_language(str(path)) == "python":
                try:
                    _ast.parse(content, filename=str(path))
                except SyntaxError as e:
                    fi_partial = parse_file(str(path), content)
                    return {
                        "file_index": fi_partial.model_dump(mode="json"),
                        "error": f"Syntax error in {path}: {e}",
                    }
            fi = parse_file(str(path), content)
            return {"file_index": fi.model_dump(mode="json")}
        except (OSError, UnicodeError) as e:
            log.debug("IO error reading %s: %s", path, e)
            return {
                "file_index": {
                    "path": str(path),
                    "language": "unknown",
                    "symbols": [],
                    "imports": [],
                },
                "error": f"IO error reading {path}: {e}",
            }
        except (TypeError, ValueError) as e:
            log.warning("Unexpected error parsing %s: %s", path, e)
            return {
                "file_index": {
                    "path": str(path),
                    "language": "unknown",
                    "symbols": [],
                    "imports": [],
                },
                "error": f"Parse error in {path}: {e}",
            }

    async def query_symbol(self, name: str, file_path: str | None = None) -> list[CodeSymbol]:
        results: list[CodeSymbol] = []
        if file_path:
            search_paths: Iterable[Path] = [Path(file_path)]
        elif self._workspace:
            search_paths = self._workspace.rglob("*")
        else:
            search_paths = []

        for p in search_paths:
            if p.is_file() and _detect_language(str(p)) == "python":
                try:
                    source = p.read_text(encoding="utf-8")
                    tree = _ast.parse(source)
                    for node in _ast.walk(tree):
                        if (
                            isinstance(
                                node,
                                (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef),
                            )
                            and node.name == name
                        ):
                            kind = (
                                SymbolKind.CLASS
                                if isinstance(node, _ast.ClassDef)
                                else SymbolKind.FUNCTION
                            )
                            results.append(
                                CodeSymbol(
                                    name=node.name,
                                    kind=kind,
                                    file_path=str(p),
                                    start_line=node.lineno or 0,
                                    end_line=node.end_lineno or node.lineno or 0,
                                ),
                            )
                except (SyntaxError, OSError, UnicodeError):
                    pass
        return results

    async def chunk_file(self, file_path: str, max_lines: int = 50) -> list[dict[str, Any]]:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return []
        chunks = _syntax_aware_chunk(content, max_lines=max_lines)
        return [
            {
                "start_line": s,
                "end_line": e,
                "content": t,
                "language": _detect_language(file_path),
            }
            for s, e, t in chunks
        ]
