"""Checkpoint system — snapshot/restore for crash recovery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sdlc.models import Checkpoint


class CheckpointError(Exception):
    """Checkpoint save/restore error."""


class CheckpointManager:
    """Manages checkpoint snapshots to disk as JSON."""

    def __init__(self, checkpoint_dir: str | Path) -> None:
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    def save(self, checkpoint: Checkpoint) -> Path:
        path = self._path_for(checkpoint.task_id)
        tmp = path.with_suffix(".json.tmp")
        data = checkpoint.model_dump(mode="json")
        data["_schema_version"] = 1
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.rename(path)
        return path

    def restore(self, task_id: str) -> Checkpoint | None:
        path = self._path_for(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            data.pop("_schema_version", None)
            created_at = data.get("created_at")
            if isinstance(created_at, str):
                data["created_at"] = datetime.fromisoformat(created_at)
            history = data.get("history", [])
            for rec in history:
                for field in ("started_at", "completed_at"):
                    val = rec.get(field)
                    if isinstance(val, str):
                        rec[field] = datetime.fromisoformat(val)
            return Checkpoint(**data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            msg = f"Failed to restore checkpoint for {task_id}: {e}"
            raise CheckpointError(msg) from e

    def delete(self, task_id: str) -> None:
        path = self._path_for(task_id)
        if path.exists():
            path.unlink()

    def list_task_ids(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json") if not p.name.endswith(".tmp")]

    def latest_modification(self, task_id: str) -> datetime | None:
        path = self._path_for(task_id)
        if path.exists():
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime, tz=UTC)
        return None
