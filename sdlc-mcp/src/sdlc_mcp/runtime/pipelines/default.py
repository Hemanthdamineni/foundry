from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sdlc_mcp.engine.dependency_graph import DependencyGraphEngine, parse_file
from sdlc_mcp.log import get_logger
from sdlc_mcp.models import IndexConfig

if TYPE_CHECKING:
    from sdlc_mcp.adapters.tools.graphify import GraphifyAdapter
    from sdlc_mcp.adapters.tools.tree_sitter import TreeSitterAdapter

log = get_logger("index_pipeline")

_SHA_CACHE_FILE = "sha_cache.json"
_MIN_KEYWORD_LENGTH = 3
_GRAPH_LOAD_BYTES_PER_FILE = 4096
_MIN_GRAPH_LOAD_BYTES = 1024 * 1024


def _compute_sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _matches_any(pattern: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(pattern, p) for p in patterns)


def _path_candidates(file_path: Path, workspace: Path | None = None) -> set[str]:
    candidates = {file_path.name, file_path.as_posix()}
    if workspace is not None:
        with contextlib.suppress(ValueError):
            candidates.add(file_path.relative_to(workspace).as_posix())

    segments = file_path.as_posix().split("/")
    candidates.update("/".join(segments[i:]) for i in range(len(segments)) if segments[i:])
    return candidates


def _matches_any_path(
    file_path: Path,
    patterns: list[str],
    workspace: Path | None = None,
) -> bool:
    candidates = _path_candidates(file_path, workspace)
    return any(_matches_any(candidate, patterns) for candidate in candidates)


def _should_index(
    file_path: Path,
    config: IndexConfig,
    workspace: Path | None = None,
) -> bool:
    if not file_path.is_file():
        return False
    try:
        size = file_path.stat().st_size
    except OSError:
        return False
    if size > config.max_file_size_kb * 1024:
        return False

    if _matches_any_path(file_path, config.exclude_patterns, workspace):
        return False

    return _matches_any_path(file_path, config.include_patterns, workspace)


class IndexPipeline:
    """Repository indexing pipeline — scans, parses, and maintains a dependency graph.

    Provides deterministic context retrieval for agents based on structural
    code relationships (not embeddings or LLM calls).
    """

    def __init__(
        self,
        workspace: str | Path,
        store_dir: str | Path,
        config: IndexConfig | None = None,
        ts_adapter: TreeSitterAdapter | None = None,
        graphify_adapter: GraphifyAdapter | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._config = config or IndexConfig()
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._graph_engine = DependencyGraphEngine(store_dir)
        self._ts_adapter = ts_adapter
        self._graphify_adapter = graphify_adapter
        self._sha_cache_path = self._store_dir / _SHA_CACHE_FILE
        self._sha_cache: dict[str, str] = {}
        self._indexed_count = 0
        self._skipped_count = 0

    @property
    def graph(self) -> DependencyGraphEngine:
        return self._graph_engine

    @property
    def stats(self) -> dict[str, Any]:
        g = self._graph_engine.graph
        return {
            "indexed_count": self._indexed_count,
            "skipped_count": self._skipped_count,
            "total_files": g.file_count,
            "total_symbols": g.symbol_count,
            "enabled": self._config.enabled,
        }

    def _collect_indexable_files(self) -> list[Path]:
        indexable: list[Path] = []
        for root, dirs, files in os.walk(self._workspace):
            root_path = Path(root)
            dirs[:] = sorted(
                d
                for d in dirs
                if not _matches_any_path(
                    root_path / d,
                    self._config.exclude_patterns,
                    self._workspace,
                )
            )
            for filename in sorted(files):
                fp = root_path / filename
                if _should_index(fp, self._config, self._workspace):
                    indexable.append(fp)
                    if len(indexable) >= self._config.max_files:
                        return indexable
        return indexable

    async def initialize(self) -> None:
        max_graph_bytes = max(
            _MIN_GRAPH_LOAD_BYTES,
            self._config.max_files * _GRAPH_LOAD_BYTES_PER_FILE,
        )
        loaded = await self._graph_engine.load(max_bytes=max_graph_bytes)
        self._load_sha_cache()
        if loaded:
            self._prune_sha_cache()
        else:
            self._sha_cache = {}
        log.info(
            "Index pipeline initialized",
            extra={
                "workspace": str(self._workspace),
                "graph_files": self._graph_engine.graph.file_count,
                "graph_symbols": self._graph_engine.graph.symbol_count,
            },
        )

    async def run_full_index(self) -> dict[str, Any]:
        """Full repository index — scan all files and rebuild the graph."""
        if not self._config.enabled:
            return {"status": "disabled", "files_indexed": 0, "files_skipped": 0}

        self._indexed_count = 0
        self._skipped_count = 0
        errors: list[str] = []

        all_files = self._collect_indexable_files()
        total = len(all_files)

        log.info(
            "Full index starting",
            extra={"total_files": total, "workspace": str(self._workspace)},
        )

        for i, fp in enumerate(all_files):
            if i > 0 and i % 500 == 0:
                log.debug("Index progress", extra={"indexed": i, "total": total})

            try:
                await self._index_file(fp, force=True)
                self._indexed_count += 1
            except (OSError, UnicodeError, TypeError, ValueError) as e:
                errors.append(f"{fp}: {e}")
                self._skipped_count += 1

        self._graph_engine.graph.indexed_at = datetime.now(UTC).isoformat()
        await self._graph_engine.persist()
        self._save_sha_cache()

        result = {
            "status": "ok",
            "files_indexed": self._indexed_count,
            "files_skipped": self._skipped_count,
            "total_files": self._graph_engine.graph.file_count,
            "total_symbols": self._graph_engine.graph.symbol_count,
            "errors": errors[:20],
        }

        log.info("Full index complete", extra=result)
        return result

    async def run_incremental_index(self) -> dict[str, Any]:
        """Incremental index — only process files with changed content."""
        if not self._config.enabled:
            return {"status": "disabled", "files_indexed": 0, "files_skipped": 0}

        self._indexed_count = 0
        self._skipped_count = 0
        errors: list[str] = []

        all_files = self._collect_indexable_files()

        for fp in all_files:
            try:
                if await self._is_changed(fp):
                    await self._index_file(fp, force=False)
                    self._indexed_count += 1
                else:
                    self._skipped_count += 1
            except (OSError, UnicodeError, TypeError, ValueError) as e:
                errors.append(f"{fp}: {e}")
                self._skipped_count += 1

        if self._indexed_count > 0:
            await self._graph_engine.persist()
            self._save_sha_cache()

        result = {
            "status": "ok",
            "files_indexed": self._indexed_count,
            "files_skipped": self._skipped_count,
            "total_files": self._graph_engine.graph.file_count,
            "total_symbols": self._graph_engine.graph.symbol_count,
            "errors": errors[:20],
        }

        if self._indexed_count > 0:
            log.info("Incremental index complete", extra=result)
        return result

    async def index_files(self, file_paths: list[str]) -> dict[str, Any]:
        """Index specific files (e.g., after edits)."""
        if not self._config.enabled:
            return {"status": "disabled", "files_indexed": 0}

        indexed = 0
        errors: list[str] = []

        for fp_str in file_paths:
            fp = Path(fp_str)
            if not fp.exists() or not _should_index(fp, self._config, self._workspace):
                continue
            try:
                await self._index_file(fp, force=True)
                indexed += 1
            except (OSError, UnicodeError, TypeError, ValueError) as e:
                errors.append(f"{fp}: {e}")

        if indexed > 0:
            await self._graph_engine.persist()
            self._save_sha_cache()

        return {
            "status": "ok",
            "files_indexed": indexed,
            "errors": errors[:10],
        }

    async def get_context_for_phase(
        self,
        phase: str,
        target_files: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Get relevant code context for the agent in the current phase."""
        if not self._config.enabled:
            return {"relevant_files": [], "context_chunks": [], "graph_summary": {}}

        related_files: list[str] = []
        if target_files:
            related_files.extend(target_files)

        if not related_files and description:
            keywords = [
                w.lower()
                for w in description.split()
                if len(w) > _MIN_KEYWORD_LENGTH
            ]
            all_files = self._graph_engine.graph.files
            for fp in all_files:
                for kw in keywords:
                    if kw in fp.lower():
                        related_files.append(fp)
                        break

        if not related_files:
            related_files = list(self._graph_engine.graph.files.keys())[:10]

        chunks = await self._graph_engine.get_relevant_context(
            target_files=related_files,
            max_files=self._config.context_file_count,
            max_chunks=self._config.context_chunk_count,
            chunk_size=self._config.chunk_size_lines,
        )

        g = self._graph_engine.graph
        graph_summary = {
            "file_count": g.file_count,
            "symbol_count": g.symbol_count,
            "indexed_at": g.indexed_at or "",
            "phase": phase,
        }

        return {
            "relevant_files": list(set(related_files)),
            "context_chunks": [c.model_dump(mode="json") for c in chunks],
            "graph_summary": graph_summary,
        }

    async def get_dependency_context(self, file_path: str) -> dict[str, Any]:
        """Get dependency context for a specific file."""
        deps = await self._graph_engine.get_dependencies(file_path)
        dep_files = [d for d in deps if d in self._graph_engine.graph.files]

        dependents = await self._graph_engine.get_dependents(file_path)
        dep_of_files = [d for d in dependents if d in self._graph_engine.graph.files]

        symbols = self._graph_engine.graph.files.get(file_path)
        symbol_list = [s.model_dump(mode="json") for s in (symbols.symbols if symbols else [])]

        return {
            "file": file_path,
            "symbols": symbol_list,
            "dependencies": dep_files,
            "dependents": dep_of_files,
        }

    async def run_graphify_index(self) -> dict[str, Any]:
        """Optionally run Graphify index if the adapter is registered."""
        if not self._graphify_adapter:
            return {"status": "skipped", "reason": "Graphify adapter not available"}
        available = await self._graphify_adapter.healthcheck()
        if not available:
            return {"status": "skipped", "reason": "Graphify CLI not installed"}
        return await self._graphify_adapter.execute(
            {
                "path": str(self._workspace),
                "mode": "incremental",
            },
        )

    async def _index_file(self, fp: Path, *, force: bool = False) -> None:
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeError:
            try:
                content = fp.read_text(encoding="latin-1")
            except (OSError, UnicodeError):
                return

        sha = _compute_sha256(content)
        if not force:
            prev_sha = self._sha_cache.get(str(fp))
            if prev_sha == sha:
                return

        fi = parse_file(str(fp), content)
        await self._graph_engine.update_file(str(fp), fi)
        self._sha_cache[str(fp)] = sha

    async def _is_changed(self, fp: Path) -> bool:
        if not fp.exists():
            return True
        if str(fp) not in self._graph_engine.graph.files:
            return True
        prev_sha = self._sha_cache.get(str(fp))
        if prev_sha is None:
            return True
        try:
            content = fp.read_bytes()
        except OSError:
            return True
        else:
            return _compute_sha256(content) != prev_sha

    def _load_sha_cache(self) -> None:
        if self._sha_cache_path.exists():
            try:
                self._sha_cache = json.loads(
                    self._sha_cache_path.read_text(encoding="utf-8"),
                )
            except (json.JSONDecodeError, OSError):
                self._sha_cache = {}

    def _prune_sha_cache(self) -> None:
        self._sha_cache = {
            fp: sha
            for fp, sha in self._sha_cache.items()
            if _should_index(Path(fp), self._config, self._workspace)
        }

    def _save_sha_cache(self) -> None:
        try:
            tmp = self._sha_cache_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._sha_cache, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.rename(self._sha_cache_path)
        except OSError as exc:
            log.warning("Failed to save SHA cache", extra={"error": str(exc)})
