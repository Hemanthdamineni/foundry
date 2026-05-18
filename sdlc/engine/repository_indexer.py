"""Repository indexer — full-repo understanding with architecture summarization and API surface mapping.

Builds on DependencyGraphEngine to provide:
- Repository-wide file indexing with language detection
- API surface extraction (public functions, classes, endpoints)
- Architecture summarization (modules, layers, boundaries)
- Dependency graph for hierarchical planning and subagent routing
"""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.engine.dependency_graph import (
    DependencyGraphEngine,
    parse_file,
)
from sdlc.log import get_logger
from sdlc.models import CodeSymbol, IndexConfig, SymbolKind

logger = get_logger("engine.repository_indexer")


class APIEndpoint(BaseModel):
    """A detected API endpoint or public interface."""

    name: str
    kind: str  # function, method, class, route, tool
    file_path: str
    line: int = 0
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"  # public, internal, private
    decorators: list[str] = Field(default_factory=list)


class ModuleSummary(BaseModel):
    """Summary of a single module/package."""

    path: str
    language: str = "unknown"
    file_count: int = 0
    symbol_count: int = 0
    public_api_count: int = 0
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    responsibility: str = ""


class ArchitectureSummary(BaseModel):
    """Full architecture summary of the repository."""

    root: str = ""
    total_files: int = 0
    total_symbols: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    modules: list[ModuleSummary] = Field(default_factory=list)
    api_surface: list[APIEndpoint] = Field(default_factory=list)
    layer_map: dict[str, list[str]] = Field(default_factory=dict)
    entry_points: list[str] = Field(default_factory=list)
    test_modules: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)


class RepositoryIndexer:
    """Indexes a repository and produces structured architecture understanding.

    This is the foundational module that feeds:
    - Hierarchical planning (which modules to change)
    - Subagent routing (which subagent owns which module)
    - Parallel execution (which modules can be changed concurrently)
    - Drift detection (expected vs actual architecture)
    """

    def __init__(
        self,
        workspace: str | Path,
        dep_engine: DependencyGraphEngine,
        config: IndexConfig | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._dep_engine = dep_engine
        self._config = config or IndexConfig()
        self._summary: ArchitectureSummary | None = None

    @property
    def dep_engine(self) -> DependencyGraphEngine:
        return self._dep_engine

    @property
    def summary(self) -> ArchitectureSummary | None:
        return self._summary

    async def index(self) -> ArchitectureSummary:
        """Run full repository indexing and return architecture summary."""
        # 1. Discover and index files
        files_indexed = await self._index_files()
        logger.info("Files indexed", extra={"count": files_indexed})

        # 2. Build architecture summary
        self._summary = await self._build_summary()

        # 3. Extract API surface
        self._summary.api_surface = await self._extract_api_surface()

        # 4. Classify entry points, tests, configs
        self._summary.entry_points = self._find_entry_points()
        self._summary.test_modules = self._find_test_modules()
        self._summary.config_files = self._find_config_files()

        # 5. Persist
        await self._dep_engine.persist()

        logger.info(
            "Repository indexed",
            extra={
                "total_files": self._summary.total_files,
                "total_symbols": self._summary.total_symbols,
                "modules": len(self._summary.modules),
                "api_endpoints": len(self._summary.api_surface),
            },
        )
        return self._summary

    async def _index_files(self) -> int:
        """Walk workspace and index all matching files."""
        count = 0
        for path in self._walk_files():
            try:
                content = path.read_text(encoding="utf-8")
                if len(content.encode("utf-8")) > self._config.max_file_size_kb * 1024:
                    continue
                fi = parse_file(str(path), content)
                await self._dep_engine.update_file(str(path), fi)
                count += 1
                if count >= self._config.max_files:
                    break
            except (OSError, UnicodeDecodeError):
                continue
        return count

    def _walk_files(self) -> list[Path]:
        """Walk workspace applying include/exclude patterns."""
        files: list[Path] = []
        for path in sorted(self._workspace.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(self._workspace))
            if any(fnmatch.fnmatch(rel, ep) for ep in self._config.exclude_patterns):
                continue
            if not any(fnmatch.fnmatch(path.name, ip) for ip in self._config.include_patterns):
                continue
            files.append(path)
        return files

    async def _build_summary(self) -> ArchitectureSummary:
        """Build architecture summary from indexed data."""
        graph = self._dep_engine.graph
        summary = ArchitectureSummary(
            root=str(self._workspace),
            total_files=graph.file_count,
            total_symbols=graph.symbol_count,
        )

        # Count languages
        lang_counts: dict[str, int] = defaultdict(int)
        for fi in graph.files.values():
            lang_counts[fi.language] += 1
        summary.languages = dict(lang_counts)

        # Group files into modules (by top-level directory)
        module_files: dict[str, list[str]] = defaultdict(list)
        for fp in graph.files:
            rel = Path(fp).relative_to(self._workspace) if fp.startswith(str(self._workspace)) else Path(fp)
            parts = rel.parts
            module_name = parts[0] if len(parts) > 1 else str(rel)
            module_files[module_name].append(fp)

        for mod_name, files in module_files.items():
            fi_list = [graph.files[f] for f in files if f in graph.files]
            sym_count = sum(len(fi.symbols) for fi in fi_list)
            public_count = sum(
                1 for fi in fi_list for sym in fi.symbols
                if not sym.name.startswith("_")
            )
            deps: set[str] = set()
            dep_of: set[str] = set()
            for f in files:
                deps.update(graph.import_edges.get(f, []))
                dep_of.update(graph.dependents.get(f, []))

            summary.modules.append(ModuleSummary(
                path=mod_name,
                language=fi_list[0].language if fi_list else "unknown",
                file_count=len(files),
                symbol_count=sym_count,
                public_api_count=public_count,
                dependencies=list(deps - set(files)),  # External deps only
                dependents=list(dep_of - set(files)),
            ))

        # Build layer map
        summary.layer_map = self._classify_layers(module_files)

        return summary

    async def _extract_api_surface(self) -> list[APIEndpoint]:
        """Extract public API endpoints from all indexed files."""
        endpoints: list[APIEndpoint] = []
        graph = self._dep_engine.graph

        for fi in graph.files.values():
            for sym in fi.symbols:
                if sym.name.startswith("_") and not sym.name.startswith("__"):
                    continue

                visibility = "public"
                if sym.name.startswith("_"):
                    visibility = "private" if sym.name.startswith("__") else "internal"

                kind = "function"
                if sym.kind == SymbolKind.CLASS:
                    kind = "class"
                elif sym.kind == SymbolKind.METHOD:
                    kind = "method"

                # Detect special kinds
                doc = sym.docstring or ""
                if any(kw in doc.lower() for kw in ["route", "endpoint", "api"]):
                    kind = "route"
                elif any(kw in doc.lower() for kw in ["tool", "mcp"]):
                    kind = "tool"

                endpoints.append(APIEndpoint(
                    name=sym.name,
                    kind=kind,
                    file_path=sym.file_path,
                    line=sym.start_line,
                    docstring=doc[:200] if doc else "",
                    visibility=visibility,
                ))

        return endpoints

    def _find_entry_points(self) -> list[str]:
        """Find entry point files (main, __main__, app, cli)."""
        graph = self._dep_engine.graph
        entry_patterns = ["__main__.py", "main.py", "app.py", "cli.py", "server.py"]
        return [fp for fp in graph.files if Path(fp).name in entry_patterns]

    def _find_test_modules(self) -> list[str]:
        """Find test directories and files."""
        graph = self._dep_engine.graph
        return [
            fp for fp in graph.files
            if "test" in Path(fp).name.lower() or "/tests/" in fp or "/test/" in fp
        ]

    def _find_config_files(self) -> list[str]:
        """Find configuration files."""
        graph = self._dep_engine.graph
        config_patterns = ["*.yaml", "*.yml", "*.toml", "*.ini", "*.cfg", "*.json"]
        return [
            fp for fp in graph.files
            if any(fnmatch.fnmatch(Path(fp).name, p) for p in config_patterns)
            and "config" in fp.lower() or Path(fp).name in [
                "pyproject.toml", "setup.cfg", "package.json", "tsconfig.json",
            ]
        ]

    def _classify_layers(self, module_files: dict[str, list[str]]) -> dict[str, list[str]]:
        """Classify modules into architectural layers."""
        layer_map: dict[str, list[str]] = {
            "foundation": [],
            "domain": [],
            "infrastructure": [],
            "presentation": [],
            "testing": [],
        }
        for mod_name in module_files:
            name_lower = mod_name.lower()
            if any(kw in name_lower for kw in ["model", "schema", "type", "exception"]):
                layer_map["foundation"].append(mod_name)
            elif any(kw in name_lower for kw in ["engine", "core", "service", "domain"]):
                layer_map["domain"].append(mod_name)
            elif any(kw in name_lower for kw in ["adapter", "runtime", "infra", "db", "store"]):
                layer_map["infrastructure"].append(mod_name)
            elif any(kw in name_lower for kw in ["cli", "api", "web", "ui", "view"]):
                layer_map["presentation"].append(mod_name)
            elif any(kw in name_lower for kw in ["test", "spec", "fixture"]):
                layer_map["testing"].append(mod_name)
            else:
                layer_map["domain"].append(mod_name)
        return layer_map

    def get_files_for_module(self, module_name: str) -> list[str]:
        """Get all files belonging to a module."""
        graph = self._dep_engine.graph
        return [
            fp for fp in graph.files
            if module_name in fp
        ]

    def get_impact_analysis(self, changed_files: list[str]) -> dict[str, Any]:
        """Analyze the impact of changing specific files."""
        graph = self._dep_engine.graph
        affected: set[str] = set()
        for fp in changed_files:
            affected.update(graph.dependents.get(fp, []))

        # Transitive dependents (1 level)
        transitive: set[str] = set()
        for fp in affected:
            transitive.update(graph.dependents.get(fp, []))

        return {
            "changed_files": changed_files,
            "directly_affected": list(affected),
            "transitively_affected": list(transitive - affected),
            "total_impact_files": len(affected | transitive),
            "test_files_affected": [
                f for f in (affected | transitive)
                if "test" in Path(f).name.lower()
            ],
        }
