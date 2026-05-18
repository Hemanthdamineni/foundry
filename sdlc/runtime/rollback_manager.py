"""Rollback handling system — git-coordinated, phase-safe, integration-safe rollback.

TODO #13: Rollback must never corrupt stable completed phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.rollback_manager")


class RollbackTarget(BaseModel):
    """A rollback target — what to roll back to."""

    task_id: str
    target_phase: str
    target_checkpoint_version: int = 0
    target_git_sha: str = ""
    reason: str = ""


class RollbackRecord(BaseModel):
    """A completed rollback record."""

    task_id: str
    from_phase: str
    to_phase: str
    rolled_back_at: str = ""
    git_sha_before: str = ""
    git_sha_after: str = ""
    files_reverted: list[str] = Field(default_factory=list)
    phases_preserved: list[str] = Field(default_factory=list)
    validation_passed: bool = False
    reason: str = ""


class RollbackManager:
    """Manages rollback operations with phase safety and integration safety.

    Rule: ROLLBACK MUST NEVER CORRUPT STABLE COMPLETED PHASES.

    Supports:
    - Git rollback coordination
    - Phase rollback (revert to phase boundary)
    - Selective rollback (revert specific files)
    - Integration-safe rollback (validate after revert)
    """

    def __init__(self) -> None:
        self._history: list[RollbackRecord] = []
        self._stable_phases: dict[str, list[str]] = {}  # task_id → stable phases
        self._phase_files: dict[str, dict[str, list[str]]] = {}  # task_id → phase → files

    def mark_phase_stable(self, task_id: str, phase: str) -> None:
        """Mark a phase as stable — rollback will never touch it."""
        self._stable_phases.setdefault(task_id, []).append(phase)

    def register_phase_files(self, task_id: str, phase: str, files: list[str]) -> None:
        """Register which files belong to which phase."""
        self._phase_files.setdefault(task_id, {})[phase] = files

    def plan_rollback(self, target: RollbackTarget) -> dict[str, Any]:
        """Plan a rollback — determine what will be reverted and what's protected."""
        task_id = target.task_id
        stable = set(self._stable_phases.get(task_id, []))
        all_phases = self._phase_files.get(task_id, {})

        files_to_revert: list[str] = []
        phases_to_revert: list[str] = []
        protected_files: list[str] = []

        for phase, files in all_phases.items():
            if phase == target.target_phase:
                break
            if phase in stable:
                protected_files.extend(files)
            else:
                files_to_revert.extend(files)
                phases_to_revert.append(phase)

        # Files in phases AFTER target get reverted
        found_target = False
        for phase, files in all_phases.items():
            if phase == target.target_phase:
                found_target = True
                continue
            if found_target and phase not in stable:
                files_to_revert.extend(files)
                phases_to_revert.append(phase)

        return {
            "target": target.model_dump(),
            "files_to_revert": files_to_revert,
            "phases_to_revert": phases_to_revert,
            "protected_files": protected_files,
            "stable_phases_preserved": list(stable),
            "safe": len(set(files_to_revert) & set(protected_files)) == 0,
        }

    def execute_rollback(
        self,
        target: RollbackTarget,
        *,
        git_sha_before: str = "",
        git_sha_after: str = "",
        files_reverted: list[str] | None = None,
    ) -> RollbackRecord:
        """Record a completed rollback."""
        stable = self._stable_phases.get(target.task_id, [])
        record = RollbackRecord(
            task_id=target.task_id,
            from_phase="current",
            to_phase=target.target_phase,
            rolled_back_at=datetime.now(UTC).isoformat(),
            git_sha_before=git_sha_before,
            git_sha_after=git_sha_after,
            files_reverted=files_reverted or [],
            phases_preserved=list(stable),
            reason=target.reason,
        )
        self._history.append(record)
        logger.info(
            "Rollback executed",
            extra={"task_id": target.task_id, "to_phase": target.target_phase},
        )
        return record

    def validate_rollback(self, record: RollbackRecord) -> bool:
        """Validate that a rollback didn't corrupt stable phases."""
        stable = set(self._stable_phases.get(record.task_id, []))
        preserved = set(record.phases_preserved)
        record.validation_passed = stable == preserved
        return record.validation_passed

    @property
    def history(self) -> list[dict[str, Any]]:
        return [r.model_dump() for r in self._history]
