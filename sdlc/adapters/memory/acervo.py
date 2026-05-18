"""Acervo — cross-task memory store with JSONL persistence and tag-based query."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdlc.log import get_logger
from sdlc.models import Engram

log = get_logger("acervo")

_ENGRAM_FILE = "engrams.jsonl"
_DEFAULT_IMPORTANCE_THRESHOLD = 0.3


class Acervo:
    """Cross-task memory store.

    Stores Engrams as JSONL, indexed by tags for deterministic retrieval.
    No embeddings or LLM calls — purely tag/keyword matching.
    """

    def __init__(self, store_dir: str | Path) -> None:
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._store_dir / _ENGRAM_FILE
        self._engrams: list[Engram] = []
        self._loaded = False

    async def initialize(self) -> None:
        self._load()
        self._loaded = True
        log.info("Acervo initialized", extra={"engram_count": len(self._engrams)})

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "engram_count": len(self._engrams),
            "store_dir": str(self._store_dir),
            "loaded": self._loaded,
            "tags": list(self._all_tags()),
        }

    async def store(  # noqa: PLR0913 - memory records expose these fields directly.
        self,
        content: str,
        task_id: str = "",
        phase: str = "",
        tags: list[str] | None = None,
        source: str = "unknown",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        engram_id: str = "",
    ) -> Engram:
        engram = Engram(
            engram_id=engram_id or uuid.uuid4().hex[:16],
            task_id=task_id,
            phase=phase,
            content=content,
            tags=tags or [],
            source=source,
            importance=importance,
            created_at=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )
        self._engrams.append(engram)
        self._append_to_file(engram)
        return engram

    async def query(  # noqa: PLR0913 - memory query exposes independent filters.
        self,
        *,
        phase: str | None = None,
        tags: list[str] | None = None,
        keywords: list[str] | None = None,
        source: str | None = None,
        min_importance: float = _DEFAULT_IMPORTANCE_THRESHOLD,
        limit: int = 10,
    ) -> list[Engram]:
        results = list(self._engrams)
        if phase:
            results = [e for e in results if e.phase == phase]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        if keywords:
            kw_lower = [k.lower() for k in keywords]
            results = [
                e for e in results
                if any(k in e.content.lower() for k in kw_lower)
            ]
        if source:
            results = [e for e in results if e.source == source]
        results = [e for e in results if e.importance >= min_importance]
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    async def get_by_task(self, task_id: str) -> list[Engram]:
        return [e for e in self._engrams if e.task_id == task_id]

    async def get_by_id(self, engram_id: str) -> Engram | None:
        for e in self._engrams:
            if e.engram_id == engram_id:
                return e
        return None

    async def forget(self, engram_id: str) -> bool:
        before = len(self._engrams)
        self._engrams = [e for e in self._engrams if e.engram_id != engram_id]
        removed = len(self._engrams) < before
        if removed:
            self._rewrite_file()
        return removed

    async def clear(self) -> int:
        count = len(self._engrams)
        self._engrams.clear()
        if self._path.exists():
            self._path.unlink()
        return count

    def _all_tags(self) -> set[str]:
        tags: set[str] = set()
        for e in self._engrams:
            tags.update(e.tags)
        return tags

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            self._engrams.append(Engram(**data))
                        except (json.JSONDecodeError, TypeError, ValueError) as exc:
                            log.warning("Skipping invalid engram line: %s", exc)
        except OSError as exc:
            log.warning("Failed to load engrams: %s", exc)

    def _append_to_file(self, engram: Engram) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(engram.model_dump_json() + "\n")
        except OSError as exc:
            log.warning("Failed to append engram: %s", exc)

    def _rewrite_file(self) -> None:
        try:
            tmp = self._path.with_suffix(".jsonl.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                for engram in self._engrams:
                    f.write(engram.model_dump_json() + "\n")
            tmp.rename(self._path)
        except OSError as exc:
            log.warning("Failed to rewrite engrams file: %s", exc)
