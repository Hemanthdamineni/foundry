"""Persistent execution state manager — crash recovery via point-in-time state files.

State files:
- state.json — global runtime state
- task_state.json — per-task state with retries, validators, unresolved risks
- phase_state.json — current phase details with integration state

Resume rule: RESUME EXACTLY FROM LAST STABLE CHECKPOINT.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.state_manager")


def _utc_now_str() -> str:
    return datetime.now(UTC).isoformat()


class GlobalState(BaseModel):
    """Global runtime state."""

    version: int = 1
    active_tasks: list[str] = Field(default_factory=list)
    server_started_at: str = ""
    last_checkpoint_at: str = ""
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0


class TaskState(BaseModel):
    """Per-task persistent state for crash recovery."""

    task_id: str
    status: str = "active"
    current_phase: str = "Chatting"
    mode: str = "feature"
    iteration_count: int = 0
    retry_counts: dict[str, int] = Field(default_factory=dict)
    phase_outputs: dict[str, str] = Field(default_factory=dict)
    validator_results: dict[str, Any] = Field(default_factory=dict)
    unresolved_risks: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    last_stable_checkpoint: str | None = None
    git_branch: str | None = None
    last_commit_sha: str | None = None
    created_at: str = ""
    updated_at: str = ""


class PhaseState(BaseModel):
    """Current phase execution state."""

    task_id: str
    phase: str
    sub_phase: str = ""
    started_at: str = ""
    integration_state: dict[str, Any] = Field(default_factory=dict)
    micro_task_index: int = 0
    total_micro_tasks: int = 0
    validation_tier: str = "microtask"  # microtask, phase, milestone


class StateManager:
    """Manages persistent execution state files with atomic writes."""

    def __init__(self, state_dir: str | Path) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._global_state = GlobalState()

    # ── Atomic I/O ──────────────────────────────────────────────

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON atomically via tmp+rename."""
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.rename(path)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read state file", extra={"path": str(path)})
            return None

    # ── Global State ────────────────────────────────────────────

    def load_global(self) -> GlobalState:
        data = self._read_json(self._state_dir / "state.json")
        if data:
            self._global_state = GlobalState(**data)
        return self._global_state

    def save_global(self) -> None:
        self._global_state.last_checkpoint_at = _utc_now_str()
        self._atomic_write(
            self._state_dir / "state.json",
            self._global_state.model_dump(mode="json"),
        )

    # ── Task State ──────────────────────────────────────────────

    def load_task(self, task_id: str) -> TaskState | None:
        path = self._state_dir / f"task_{task_id}.json"
        data = self._read_json(path)
        if data:
            return TaskState(**data)
        return None

    def save_task(self, state: TaskState) -> None:
        state.updated_at = _utc_now_str()
        path = self._state_dir / f"task_{state.task_id}.json"
        self._atomic_write(path, state.model_dump(mode="json"))

    def create_task(self, task_id: str, mode: str = "feature") -> TaskState:
        state = TaskState(
            task_id=task_id,
            mode=mode,
            created_at=_utc_now_str(),
            updated_at=_utc_now_str(),
        )
        self.save_task(state)
        if task_id not in self._global_state.active_tasks:
            self._global_state.active_tasks.append(task_id)
            self.save_global()
        return state

    def complete_task(self, task_id: str) -> None:
        state = self.load_task(task_id)
        if state:
            state.status = "done"
            self.save_task(state)
        if task_id in self._global_state.active_tasks:
            self._global_state.active_tasks.remove(task_id)
            self._global_state.total_tasks_completed += 1
            self.save_global()

    # ── Phase State ─────────────────────────────────────────────

    def load_phase(self, task_id: str) -> PhaseState | None:
        path = self._state_dir / f"phase_{task_id}.json"
        data = self._read_json(path)
        if data:
            return PhaseState(**data)
        return None

    def save_phase(self, state: PhaseState) -> None:
        path = self._state_dir / f"phase_{state.task_id}.json"
        self._atomic_write(path, state.model_dump(mode="json"))

    def transition_phase(
        self,
        task_id: str,
        new_phase: str,
        *,
        sub_phase: str = "",
    ) -> PhaseState:
        phase_state = PhaseState(
            task_id=task_id,
            phase=new_phase,
            sub_phase=sub_phase,
            started_at=_utc_now_str(),
        )
        self.save_phase(phase_state)
        task_state = self.load_task(task_id)
        if task_state:
            task_state.current_phase = new_phase
            self.save_task(task_state)
        return phase_state

    # ── Recovery ────────────────────────────────────────────────

    def get_resumable_tasks(self) -> list[TaskState]:
        """Find all tasks that can be resumed after a crash."""
        tasks: list[TaskState] = []
        for path in self._state_dir.glob("task_*.json"):
            data = self._read_json(path)
            if data:
                state = TaskState(**data)
                if state.status == "active":
                    tasks.append(state)
        return tasks

    def record_checkpoint(self, task_id: str, checkpoint_id: str) -> None:
        """Record a stable checkpoint for recovery."""
        state = self.load_task(task_id)
        if state:
            state.last_stable_checkpoint = checkpoint_id
            self.save_task(state)
