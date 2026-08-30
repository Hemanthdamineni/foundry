from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("pipelines.default")


@dataclass
class IndexConfig:
    """Configuration for the index pipeline."""

    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: tuple[str, ...] = (
        "*.py",
        "*.js",
        "*.ts",
        "*.jsx",
        "*.tsx",
        "*.rs",
        "*.go",
        "*.java",
        "*.yaml",
        "*.yml",
        "*.json",
        "*.md",
    )
    exclude_patterns: tuple[str, ...] = (
        "*.pyc",
        "__pycache__/*",
        ".git/*",
        "node_modules/*",
        ".pixi/*",
        ".venv/*",
        "data/*",
        ".opencode/*",
    )
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20


@dataclass
class IndexEntry:
    """A single file's index data."""

    path: str
    language: str
    mtime: float
    size_bytes: int
    sha256: str
    symbols: list[dict[str, Any]] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    indexed_at: str = ""


class IndexPipeline:
    """Scans workspace files, extracts basic symbols, and provides context retrieval.

    Parameters
    ----------
    workspace:
        Root path of the workspace to index.
    store_dir:
        Directory where the index metadata is persisted.
    config:
        Index configuration.
    """

    def __init__(
        self,
        workspace: str | Path,
        store_dir: str | Path,
        config: IndexConfig | None = None,
    ) -> None:
        self._workspace = Path(workspace).resolve()
        self._store_dir = Path(store_dir)
        self._config = config or IndexConfig()
        self._entries: dict[str, IndexEntry] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Prepare the pipeline — create store directory and load cached index."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._store_dir / "index_cache.json"
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                for path, data in raw.items():
                    self._entries[path] = IndexEntry(**data)
                log.info("Loaded %d cached index entries", len(self._entries))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("Failed to load index cache: %s — rebuilding", exc)
                self._entries.clear()
        self._initialized = True

    @property
    def stats(self) -> dict[str, Any]:
        """Return index statistics."""
        return {
            "file_count": len(self._entries),
            "workspace": str(self._workspace),
            "initialized": self._initialized,
            "config": {
                "enabled": self._config.enabled,
                "max_files": self._config.max_files,
                "incremental": self._config.incremental,
            },
        }

    async def run_incremental_index(self) -> dict[str, Any]:
        """Run an incremental index — scan files that have changed since last run.

        Returns
        -------
        dict
            Summary of indexed, skipped, and removed files.
        """
        if not self._config.enabled:
            return {"status": "disabled", "indexed": 0}

        indexed = 0
        skipped = 0
        errors = 0

        for file_path in self._iter_workspace_files():
            if indexed >= self._config.max_files:
                break
            stat = self._stat_file(file_path)
            if stat is None:
                continue
            rel_path = str(file_path.relative_to(self._workspace))
            cached = self._entries.get(rel_path)
            if cached and cached.mtime == stat.st_mtime and cached.size_bytes == stat.st_size:
                skipped += 1
                continue
            entry = self._scan_file(file_path, rel_path, stat)
            if entry is not None:
                self._entries[rel_path] = entry
                indexed += 1
            else:
                errors += 1

        self._save_cache()

        log.info(
            "Incremental index: %d indexed, %d skipped, %d errors",
            indexed,
            skipped,
            errors,
        )
        return {
            "status": "ok",
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
            "total": len(self._entries),
        }

    async def run_full_index(self) -> dict[str, Any]:
        """Run a full index rebuild — scan all files from scratch.

        Returns
        -------
        dict
            Summary of indexed files.
        """
        self._entries.clear()
        result = await self.run_incremental_index()
        result["mode"] = "full"
        return result

    async def index_files(self, file_paths: list[str]) -> dict[str, Any]:
        """Index specific files by their workspace-relative paths.

        Parameters
        ----------
        file_paths:
            Workspace-relative file paths to index.

        Returns
        -------
        dict
            Indexed file counts.
        """
        indexed = 0
        errors = 0
        for rel_path in file_paths:
            abs_path = self._workspace / rel_path
            if not abs_path.exists() or not abs_path.is_file():
                errors += 1
                continue
            stat = self._stat_file(abs_path)
            if stat is None:
                errors += 1
                continue
            entry = self._scan_file(abs_path, rel_path, stat)
            if entry is not None:
                self._entries[rel_path] = entry
                indexed += 1
            else:
                errors += 1

        if indexed > 0:
            self._save_cache()

        return {"indexed": indexed, "errors": errors, "total": len(self._entries)}

    async def get_dependency_context(self, file_path: str) -> dict[str, Any]:
        """Retrieve dependency context for a given file.

        Identifies files that import or are imported by the target,
        and returns their indexed content summaries.

        Parameters
        ----------
        file_path:
            Workspace-relative path to the file.

        Returns
        -------
        dict
            Dependency context with related files.
        """
        entry = self._entries.get(file_path)
        if entry is None:
            return {"file": file_path, "dependencies": [], "error": "File not indexed"}

        # Reverse-dependency lookup: find files that import this one
        dependents: list[str] = []
        for path, e in self._entries.items():
            if file_path in e.imports:
                dependents.append(path)

        return {
            "file": file_path,
            "language": entry.language,
            "dependencies": list(entry.imports),
            "dependents": dependents,
            "symbol_count": len(entry.symbols),
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _iter_workspace_files(self) -> list[Path]:
        """Walk the workspace and yield files matching include patterns."""
        matched: list[Path] = []
        try:
            for root_str, _dirs, files in os.walk(self._workspace):
                root = Path(root_str)
                rel_root = root.relative_to(self._workspace)
                if any(fnmatch(str(rel_root), pat) for pat in self._config.exclude_patterns):
                    continue
                for name in files:
                    rel_path = rel_root / name if str(rel_root) != "." else Path(name)
                    if any(fnmatch(str(rel_path), pat) for pat in self._config.exclude_patterns):
                        continue
                    if any(fnmatch(name, pat) for pat in self._config.include_patterns):
                        matched.append(root / name)
        except (OSError, ValueError) as exc:
            log.warning("Workspace walk error: %s", exc)
        return matched[: self._config.max_files]

    def _stat_file(self, path: Path) -> os.stat_result | None:
        try:
            return path.stat()
        except OSError:
            return None

    def _scan_file(self, path: Path, rel_path: str, stat: os.stat_result) -> IndexEntry | None:
        """Scan a single file — compute hash and extract basic symbols."""
        if stat.st_size > self._config.max_file_size_kb * 1024:
            log.debug("Skipping oversized file: %s", rel_path)
            return None
        try:
            content = path.read_bytes()
        except OSError:
            return None

        sha256 = hashlib.sha256(content).hexdigest()
        language = self._detect_language(rel_path)

        # Basic symbol extraction: function/class def lines and imports
        symbols: list[dict[str, Any]] = []
        imports: list[str] = []
        try:
            text = content.decode("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                # Simple pattern-based extraction for common languages
                for kw in ("def ", "class ", "fn ", "func ", "public class ", "impl "):
                    if stripped.startswith(kw):
                        symbols.append({
                            "name": stripped[len(kw):].split("(")[0].split("{")[0].split()[0].strip(),
                            "kind": "function" if kw in ("def ", "fn ", "func ") else "class",
                            "line": i,
                        })
                        break
                for imp_kw in ("import ", "use ", "extern crate ", "#include", "require("):
                    if stripped.startswith(imp_kw):
                        imports.append(stripped)
                        break
        except UnicodeDecodeError:
            pass

        return IndexEntry(
            path=rel_path,
            language=language,
            mtime=stat.st_mtime,
            size_bytes=stat.st_size,
            sha256=sha256,
            symbols=symbols,
            imports=imports,
            indexed_at=datetime.now(UTC).isoformat(),
        )

    def _save_cache(self) -> None:
        """Persist the in-memory index to disk."""
        cache_path = self._store_dir / "index_cache.json"
        serializable = {
            path: {
                "path": e.path,
                "language": e.language,
                "mtime": e.mtime,
                "size_bytes": e.size_bytes,
                "sha256": e.sha256,
                "symbols": e.symbols[:50],
                "imports": e.imports,
                "indexed_at": e.indexed_at,
            }
            for path, e in self._entries.items()
        }
        tmp = cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(serializable, indent=2, default=str))
        tmp.rename(cache_path)

    @staticmethod
    def _detect_language(path: str) -> str:
        ext = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
            ".toml": "toml",
            ".html": "html",
            ".css": "css",
        }.get(ext, "unknown")
