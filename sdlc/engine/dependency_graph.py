from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdlc.log import get_logger
from sdlc.models import (
    CodeSymbol,
    ContextChunk,
    DependencyGraph,
    FileIndex,
    ImportInfo,
    SymbolKind,
)

log = get_logger("dependency_graph")

_SECTION_RE = re.compile(r"^#{2,4}\s+", re.MULTILINE)
_SYMBOL_RE = re.compile(
    r"^(?:async\s+)?(?:def|class)\s+(\w+)|"
    r"^(\w+)\s*[=:]\s*(?:lambda|class|def|\[|\{)|"
    r"^(?:const|let|var|fun|func|fn|def|function)\s+(\w+)",
    re.MULTILINE,
)
_IMPORT_PY_RE = re.compile(
    r"^(?:from\s+([.\w]+)\s+)?import\s+(.+)$",
    re.MULTILINE,
)
_IMPORT_JS_RE = re.compile(
    r"(?:import\s+(?:\{[^}]*\}|[^;{]+)\s+from\s+[\"']([^\"']+)[\"']|"
    r"require\s*\(\s*[\"']([^\"']+)[\"'])",
    re.MULTILINE,
)


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    mapping: dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".rb": "ruby",
        ".swift": "swift",
        ".kt": "kotlin",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".php": "php",
        ".scala": "scala",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
    }
    return mapping.get(ext, "unknown")


def _compute_sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


def _extract_python_symbols(file_path: str, content: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    try:
        tree = ast.parse(content, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        kind=SymbolKind.CLASS,
                        file_path=file_path,
                        start_line=node.lineno or 0,
                        end_line=node.end_lineno or node.lineno or 0,
                        docstring=doc,
                    ),
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_doc = ast.get_docstring(item)
                        symbols.append(
                            CodeSymbol(
                                name=item.name,
                                kind=SymbolKind.METHOD,
                                file_path=file_path,
                                start_line=item.lineno or 0,
                                end_line=item.end_lineno or item.lineno or 0,
                                parent=node.name,
                                docstring=method_doc,
                            ),
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        kind=SymbolKind.FUNCTION,
                        file_path=file_path,
                        start_line=node.lineno or 0,
                        end_line=node.end_lineno or node.lineno or 0,
                        docstring=doc,
                    ),
                )
    except SyntaxError:
        pass
    return symbols


def _extract_generic_symbols(file_path: str, content: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    for match in _SYMBOL_RE.finditer(content):
        name = next(g for g in match.groups() if g is not None)
        line_num = content[: match.start()].count("\n") + 1
        kind = (
            SymbolKind.FUNCTION
            if match.group(0).startswith(("def", "fun"))
            else SymbolKind.UNKNOWN
        )
        symbols.append(
            CodeSymbol(
                name=name,
                kind=kind,
                file_path=file_path,
                start_line=line_num,
                end_line=line_num,
            ),
        )
    return symbols


def _extract_imports_python(file_path: str, content: str) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for match in _IMPORT_PY_RE.finditer(content):
        module = match.group(1) or ""
        targets = match.group(2)
        line_num = content[: match.start()].count("\n") + 1
        is_rel = module.startswith(".")
        if module and targets:
            for name in re.split(r"\s*,\s*", targets.strip()):
                clean = name.split(" as ")[0].split(".")[0].strip()
                if clean:
                    imports.append(
                        ImportInfo(
                            source=clean,
                            alias=name.split(" as ")[1].strip() if " as " in name else None,
                            file_path=file_path,
                            line=line_num,
                            is_relative=is_rel,
                        ),
                    )
        elif targets:
            names = re.split(r"\s*,\s*", targets.strip())
            for name in names:
                clean = name.split(" as ")[0].split(".")[0].strip()
                if clean:
                    imports.append(
                        ImportInfo(
                            source=clean,
                            file_path=file_path,
                            line=line_num,
                            is_relative=False,
                        ),
                    )
    return imports


def _extract_imports_js(file_path: str, content: str) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for match in _IMPORT_JS_RE.finditer(content):
        source = match.group(1) or match.group(2) or ""
        line_num = content[: match.start()].count("\n") + 1
        if source and not source.startswith("."):
            top = source.split("/")[0]
            imports.append(
                ImportInfo(
                    source=top,
                    file_path=file_path,
                    line=line_num,
                    is_relative=source.startswith("."),
                ),
            )
    return imports


def parse_file(file_path: str, content: str | None = None) -> FileIndex:
    if content is None:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""

    lang = _detect_language(file_path)
    size_bytes = len(content.encode("utf-8"))
    mtime = 0.0
    with suppress(OSError):
        mtime = Path(file_path).stat().st_mtime
    sha256 = _compute_sha256(content)

    symbols: list[CodeSymbol] = []
    imports: list[ImportInfo] = []

    if lang == "python":
        symbols = _extract_python_symbols(file_path, content)
        imports = _extract_imports_python(file_path, content)
    else:
        symbols = _extract_generic_symbols(file_path, content)
        imports = _extract_imports_js(file_path, content)

    return FileIndex(
        path=file_path,
        language=lang,
        symbols=symbols,
        imports=imports,
        mtime=mtime,
        sha256=sha256,
        size_bytes=size_bytes,
        indexed_at=datetime.now(UTC).isoformat(),
    )


def resolve_import_to_file(
    import_info: ImportInfo,
    known_files: set[str],
    search_paths: list[str] | None = None,
) -> str | None:
    source = import_info.source
    candidates: list[str] = []

    if search_paths:
        for sp in search_paths:
            candidates.append(f"{sp}/{source}.py")
            candidates.append(f"{sp}/{source}/__init__.py")
            candidates.append(f"{sp}/{source}.js")
            candidates.append(f"{sp}/{source}.ts")
            candidates.append(f"{sp}/{source}/index.js")
            candidates.append(f"{sp}/{source}/index.ts")

    candidates.append(f"{source}.py")
    candidates.append(f"{source}/__init__.py")
    candidates.append(f"{source}.js")
    candidates.append(f"{source}.ts")

    for candidate in candidates:
        if candidate in known_files:
            return candidate
    return None


_DEP_GRAPH_VERSION = 1
_DEP_GRAPH_FILE = "dependency_graph.json"


class DependencyGraphEngine:
    def __init__(self, store_dir: str | Path) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / _DEP_GRAPH_FILE
        self._graph = DependencyGraph()

    @property
    def graph(self) -> DependencyGraph:
        return self._graph

    async def update_file(self, file_path: str, index: FileIndex | None = None) -> None:
        if index is None:
            index = parse_file(file_path)

        old = self._graph.files.get(file_path)
        old_imports: set[str] = set()
        if old:
            old_imports = {imp.source for imp in old.imports}

        self._graph.files[file_path] = index

        new_import_sources = {imp.source for imp in index.imports}
        removed = old_imports - new_import_sources

        for imp_src in removed:
            if file_path in self._graph.import_edges:
                self._graph.import_edges[file_path] = [
                    f for f in self._graph.import_edges.get(file_path, [])
                    if f != imp_src
                ]

        known_files = set(self._graph.files.keys())
        search_path = Path(file_path).parent
        search_paths = [str(search_path)] if search_path else None

        resolved_files: list[str] = []
        for imp_info in index.imports:
            resolved = resolve_import_to_file(imp_info, known_files, search_paths)
            if resolved:
                resolved_files.append(resolved)

        self._graph.import_edges[file_path] = resolved_files

        for resolved in resolved_files:
            if resolved not in self._graph.dependents:
                self._graph.dependents[resolved] = []
            if file_path not in self._graph.dependents[resolved]:
                self._graph.dependents[resolved].append(file_path)

        self._graph.file_count = len(self._graph.files)
        self._graph.symbol_count = sum(
            len(fi.symbols) for fi in self._graph.files.values()
        )
        self._graph.indexed_at = datetime.now(UTC).isoformat()

    async def remove_file(self, file_path: str) -> None:
        self._graph.files.pop(file_path, None)
        self._graph.import_edges.pop(file_path, None)
        self._graph.dependents.pop(file_path, None)

        for deps in self._graph.import_edges.values():
            if file_path in deps:
                deps.remove(file_path)
        for deps in self._graph.dependents.values():
            if file_path in deps:
                deps.remove(file_path)

        self._graph.file_count = len(self._graph.files)
        self._graph.symbol_count = sum(
            len(fi.symbols) for fi in self._graph.files.values()
        )

    async def get_dependents(self, file_path: str) -> list[str]:
        return list(self._graph.dependents.get(file_path, []))

    async def get_dependencies(self, file_path: str) -> list[str]:
        return list(self._graph.import_edges.get(file_path, []))

    async def get_symbol(self, name: str) -> list[CodeSymbol]:
        results: list[CodeSymbol] = []
        for fi in self._graph.files.values():
            results.extend(sym for sym in fi.symbols if sym.name == name)
        return results

    async def get_symbols_by_kind(self, kind: SymbolKind) -> list[CodeSymbol]:
        results: list[CodeSymbol] = []
        for fi in self._graph.files.values():
            results.extend(sym for sym in fi.symbols if sym.kind == kind)
        return results

    async def get_file_context(
        self,
        file_path: str,
        chunk_size: int = 50,
        max_chunks: int = 10,
    ) -> list[ContextChunk]:
        fi = self._graph.files.get(file_path)
        if fi is None:
            return []

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            return []

        lines = content.splitlines()
        chunks: list[ContextChunk] = []

        if fi.symbols:
            for sym in fi.symbols:
                start = max(0, sym.start_line - 1)
                end = min(len(lines), sym.end_line)
                chunk_lines = lines[start:end]
                chunk_text = "\n".join(chunk_lines)
                if chunk_text.strip():
                    chunks.append(
                        ContextChunk(
                            file_path=file_path,
                            language=fi.language,
                            content=chunk_text,
                            start_line=start + 1,
                            end_line=end,
                            symbol_name=sym.name,
                            symbol_kind=sym.kind.value,
                            relevance_score=0.9,
                        ),
                    )

        if not chunks:
            for i in range(0, len(lines), chunk_size):
                chunk_lines = lines[i : i + chunk_size]
                chunk_text = "\n".join(chunk_lines)
                if chunk_text.strip():
                    chunks.append(
                        ContextChunk(
                            file_path=file_path,
                            language=fi.language,
                            content=chunk_text,
                            start_line=i + 1,
                            end_line=min(i + chunk_size, len(lines)),
                            relevance_score=0.5,
                        ),
                    )

        chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        return chunks[:max_chunks]

    async def get_relevant_context(
        self,
        target_files: list[str],
        max_files: int = 10,
        max_chunks: int = 20,
        chunk_size: int = 50,
    ) -> list[ContextChunk]:
        seen_files: set[str] = set()
        files_to_check: list[str] = list(target_files)
        result_chunks: list[ContextChunk] = []

        while files_to_check and len(seen_files) < max_files:
            fp = files_to_check.pop(0)
            if fp in seen_files or fp not in self._graph.files:
                continue
            seen_files.add(fp)

            chunks = await self.get_file_context(fp, chunk_size=chunk_size, max_chunks=5)
            result_chunks.extend(chunks)

            deps = await self.get_dependencies(fp)
            dep_fps = await self.get_dependents(fp)
            files_to_check.extend(
                related
                for related in deps + dep_fps
                if related not in seen_files and related in self._graph.files
            )

        result_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        return result_chunks[:max_chunks]

    def to_dump(self) -> dict[str, Any]:
        return {
            "_version": _DEP_GRAPH_VERSION,
            "graph": self._graph.model_dump(mode="json"),
            "exported_at": datetime.now(UTC).isoformat(),
        }

    def load_dump(self, data: dict[str, Any]) -> None:
        self._graph = DependencyGraph(**data.get("graph", {}))

    async def persist(self) -> None:
        data = self.to_dump()
        tmp = self._path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            tmp.rename(self._path)
        except OSError as exc:
            log.warning("Failed to persist dependency graph", extra={"error": str(exc)})

    async def load(self, max_bytes: int | None = None) -> bool:
        if not self._path.exists():
            return False
        try:
            if max_bytes is not None:
                stat = self._path.stat()
                if stat.st_size > max_bytes:
                    log.warning(
                        "Skipping oversized dependency graph",
                        extra={"path": str(self._path), "size_bytes": stat.st_size},
                    )
                    return False
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self.load_dump(data)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.warning("Failed to load dependency graph", extra={"error": str(exc)})
            return False
        else:
            return True

    async def find_files_matching(self, pattern: str) -> list[str]:
        return [
            fp
            for fp in self._graph.files
            if fnmatch.fnmatch(Path(fp).name, pattern) or fnmatch.fnmatch(fp, pattern)
        ]

    async def find_files_by_symbol(self, symbol_name: str) -> list[str]:
        files: list[str] = []
        for fi in self._graph.files.values():
            for sym in fi.symbols:
                if sym.name == symbol_name:
                    files.append(fi.path)
                    break
        return files
