"""Enhanced checkpoint manager — versioned snapshots, rollback chains, replay points.

Extends the base CheckpointManager with:
- Versioned checkpoint history per task (not just latest)
- Named restore points for rollback chains
- Replay checkpoint extraction
- Atomic snapshot with git integration hooks
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger
from sdlc.models import Checkpoint

logger = get_logger("runtime.checkpoint_manager")


class CheckpointVersion(BaseModel):
    """A single versioned checkpoint in the history chain."""

    version: int
    phase: str
    created_at: str = ""
    sha: str = ""
    tag: str = ""
    is_stable: bool = False
    label: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RestorePoint(BaseModel):
    """A named restore point for deterministic rollback."""

    name: str
    task_id: str
    version: int
    phase: str
    created_at: str = ""
    reason: str = ""


class CheckpointChain(BaseModel):
    """Full checkpoint chain for a task — ordered from oldest to newest."""

    task_id: str
    versions: list[CheckpointVersion] = Field(default_factory=list)
    restore_points: list[RestorePoint] = Field(default_factory=list)
    current_version: int = 0
    last_stable_version: int = 0

    @property
    def latest(self) -> CheckpointVersion | None:
        return self.versions[-1] if self.versions else None

    @property
    def last_stable(self) -> CheckpointVersion | None:
        for v in reversed(self.versions):
            if v.is_stable:
                return v
        return None


class EnhancedCheckpointManager:
    """Versioned checkpoint management with rollback chains and replay support.

    Unlike the base CheckpointManager (single latest snapshot),
    this maintains the full version history per task.
    """

    def __init__(self, checkpoint_dir: str | Path) -> None:
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._chains: dict[str, CheckpointChain] = {}

    def _chain_path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}_chain.json"

    def _checkpoint_path(self, task_id: str, version: int) -> Path:
        return self._dir / f"{task_id}_v{version}.json"

    # ── Core Operations ─────────────────────────────────────────

    def save_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        label: str = "",
        is_stable: bool = False,
        git_sha: str = "",
        git_tag: str = "",
    ) -> CheckpointVersion:
        """Save a new versioned checkpoint."""
        chain = self._get_or_create_chain(checkpoint.task_id)
        version = chain.current_version + 1

        # Save checkpoint data
        data = checkpoint.model_dump(mode="json")
        data["_version"] = version
        data["_schema_version"] = 2
        self._atomic_write(
            self._checkpoint_path(checkpoint.task_id, version),
            data,
        )

        # Add to chain
        cv = CheckpointVersion(
            version=version,
            phase=checkpoint.phase,
            created_at=datetime.now(UTC).isoformat(),
            sha=git_sha,
            tag=git_tag,
            is_stable=is_stable,
            label=label or f"{checkpoint.phase} v{version}",
        )
        chain.versions.append(cv)
        chain.current_version = version
        if is_stable:
            chain.last_stable_version = version

        self._save_chain(chain)
        logger.info(
            "Checkpoint saved",
            extra={
                "task_id": checkpoint.task_id,
                "version": version,
                "phase": checkpoint.phase,
                "stable": is_stable,
            },
        )
        return cv

    def restore_checkpoint(
        self,
        task_id: str,
        version: int | None = None,
    ) -> Checkpoint | None:
        """Restore a checkpoint by version (defaults to latest)."""
        chain = self._chains.get(task_id)
        if chain is None:
            chain = self._load_chain(task_id)
        if chain is None:
            return None

        target_version = version or chain.current_version
        path = self._checkpoint_path(task_id, target_version)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("_version", None)
            data.pop("_schema_version", None)
            # Fix datetime fields
            created_at = data.get("created_at")
            if isinstance(created_at, str):
                data["created_at"] = datetime.fromisoformat(created_at)
            for rec in data.get("history", []):
                for field in ("started_at", "completed_at"):
                    val = rec.get(field)
                    if isinstance(val, str) and val:
                        rec[field] = datetime.fromisoformat(val)
            return Checkpoint(**data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to restore checkpoint", extra={"error": str(e)})
            return None

    def restore_to_stable(self, task_id: str) -> Checkpoint | None:
        """Restore to the last known stable checkpoint."""
        chain = self._get_or_create_chain(task_id)
        if chain.last_stable_version == 0:
            return None
        return self.restore_checkpoint(task_id, chain.last_stable_version)

    # ── Restore Points ──────────────────────────────────────────

    def create_restore_point(
        self,
        task_id: str,
        name: str,
        reason: str = "",
    ) -> RestorePoint | None:
        """Create a named restore point at the current version."""
        chain = self._get_or_create_chain(task_id)
        if chain.current_version == 0:
            return None

        latest = chain.latest
        rp = RestorePoint(
            name=name,
            task_id=task_id,
            version=chain.current_version,
            phase=latest.phase if latest else "",
            created_at=datetime.now(UTC).isoformat(),
            reason=reason,
        )
        chain.restore_points.append(rp)
        self._save_chain(chain)
        return rp

    def rollback_to_restore_point(
        self,
        task_id: str,
        name: str,
    ) -> Checkpoint | None:
        """Rollback to a named restore point."""
        chain = self._get_or_create_chain(task_id)
        for rp in chain.restore_points:
            if rp.name == name:
                return self.restore_checkpoint(task_id, rp.version)
        return None

    # ── Replay Support ──────────────────────────────────────────

    def get_replay_sequence(self, task_id: str) -> list[dict[str, Any]]:
        """Get the full ordered checkpoint sequence for replay."""
        chain = self._get_or_create_chain(task_id)
        sequence: list[dict[str, Any]] = []
        for cv in chain.versions:
            sequence.append({
                "version": cv.version,
                "phase": cv.phase,
                "created_at": cv.created_at,
                "stable": cv.is_stable,
                "label": cv.label,
                "sha": cv.sha,
            })
        return sequence

    def get_diff_between(
        self,
        task_id: str,
        version_a: int,
        version_b: int,
    ) -> dict[str, Any]:
        """Get the diff between two checkpoint versions."""
        cp_a = self.restore_checkpoint(task_id, version_a)
        cp_b = self.restore_checkpoint(task_id, version_b)
        if cp_a is None or cp_b is None:
            return {"error": "One or both checkpoints not found"}

        return {
            "version_a": version_a,
            "version_b": version_b,
            "phase_a": cp_a.phase,
            "phase_b": cp_b.phase,
            "history_diff": len(cp_b.history) - len(cp_a.history),
            "iteration_diff": cp_b.iteration_count - cp_a.iteration_count,
        }

    # ── Chain Info ───────────────────────────────────────────────

    def get_chain_info(self, task_id: str) -> dict[str, Any]:
        """Get chain metadata without loading full checkpoints."""
        chain = self._get_or_create_chain(task_id)
        return {
            "task_id": task_id,
            "current_version": chain.current_version,
            "last_stable_version": chain.last_stable_version,
            "total_versions": len(chain.versions),
            "restore_points": [rp.name for rp in chain.restore_points],
            "versions": [
                {"v": cv.version, "phase": cv.phase, "stable": cv.is_stable}
                for cv in chain.versions
            ],
        }

    def list_tasks(self) -> list[str]:
        """List all tasks with checkpoint chains."""
        return [p.stem.replace("_chain", "") for p in self._dir.glob("*_chain.json")]

    # ── Internal ────────────────────────────────────────────────

    def _get_or_create_chain(self, task_id: str) -> CheckpointChain:
        if task_id not in self._chains:
            loaded = self._load_chain(task_id)
            self._chains[task_id] = loaded or CheckpointChain(task_id=task_id)
        return self._chains[task_id]

    def _load_chain(self, task_id: str) -> CheckpointChain | None:
        path = self._chain_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CheckpointChain(**data)
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_chain(self, chain: CheckpointChain) -> None:
        self._atomic_write(
            self._chain_path(chain.task_id),
            chain.model_dump(mode="json"),
        )

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.rename(path)
