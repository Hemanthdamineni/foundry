"""Autonomous failure recovery — LOCALIZE FAILURES FIRST, avoid full system replans.

Recovery layers:
1. Local retry — same phase, same task, retry with feedback
2. Local replan — same phase, modified approach
3. Structural replan — rewrite the plan for this component
4. Full recovery — rollback to last stable checkpoint + replan downstream
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger
from sdlc.models import FailureType

logger = get_logger("engine.recovery_engine")


class RecoveryLevel(StrEnum):
    LOCAL_RETRY = "local_retry"
    LOCAL_REPLAN = "local_replan"
    STRUCTURAL_REPLAN = "structural_replan"
    FULL_RECOVERY = "full_recovery"


class RecoveryAction(BaseModel):
    """A recovery action to take after failure."""

    level: RecoveryLevel
    reason: str
    target_phase: str = ""
    rollback_to: str | None = None
    modified_plan: str = ""
    preserve_stable: bool = True
    retry_count: int = 0
    max_retries: int = 3


class FailureRecord(BaseModel):
    """Track failure history for pattern detection."""

    phase: str
    error: str
    failure_type: FailureType
    timestamp: str = ""
    recovery_attempted: RecoveryLevel | None = None
    resolved: bool = False


class RecoveryEngine:
    """Autonomous failure recovery with layered escalation.

    Rule: LOCALIZE FAILURES FIRST.
    Never do a full system replan when a local retry would suffice.
    """

    def __init__(
        self,
        max_local_retries: int = 3,
        max_replan_attempts: int = 2,
    ) -> None:
        self._max_local_retries = max_local_retries
        self._max_replan_attempts = max_replan_attempts
        self._failure_history: list[FailureRecord] = []
        self._retry_counts: dict[str, int] = {}  # phase → retry count
        self._replan_counts: dict[str, int] = {}  # phase → replan count

    def classify_recovery(
        self,
        phase: str,
        error: str,
        failure_type: FailureType,
    ) -> RecoveryAction:
        """Determine the appropriate recovery level for a failure."""
        self._failure_history.append(FailureRecord(
            phase=phase,
            error=error,
            failure_type=failure_type,
        ))

        retries = self._retry_counts.get(phase, 0)
        replans = self._replan_counts.get(phase, 0)

        # Level 1: Local retry — transient failures
        if failure_type in {
            FailureType.RETRYABLE_MODEL,
            FailureType.RETRYABLE_INFRA,
            FailureType.RETRYABLE_DEBATE,
        } and retries < self._max_local_retries:
            self._retry_counts[phase] = retries + 1
            return RecoveryAction(
                level=RecoveryLevel.LOCAL_RETRY,
                reason=f"Transient failure ({failure_type}), retry {retries + 1}/{self._max_local_retries}",
                target_phase=phase,
                retry_count=retries + 1,
                max_retries=self._max_local_retries,
            )

        # Level 2: Local replan — validation or phase failures after retries exhausted
        if failure_type in {
            FailureType.TERMINAL_VALIDATION,
            FailureType.TERMINAL_PHASE,
        } and replans < self._max_replan_attempts:
            self._replan_counts[phase] = replans + 1
            return RecoveryAction(
                level=RecoveryLevel.LOCAL_REPLAN,
                reason=f"Validation failure after {retries} retries, replan attempt {replans + 1}",
                target_phase=phase,
                preserve_stable=True,
            )

        # Level 3: Structural replan — repeated failures or consensus stalemate
        if failure_type in {
            FailureType.TERMINAL_CONSENSUS,
            FailureType.TERMINAL_DEPENDENCY,
        } or (retries >= self._max_local_retries and replans >= self._max_replan_attempts):
            return RecoveryAction(
                level=RecoveryLevel.STRUCTURAL_REPLAN,
                reason=f"Exhausted local recovery for {phase}, structural replan needed",
                target_phase="Planning",
                preserve_stable=True,
            )

        # Level 4: Full recovery — sandbox violations, cancelled, or gate blocks
        return RecoveryAction(
            level=RecoveryLevel.FULL_RECOVERY,
            reason=f"Unrecoverable failure in {phase}: {failure_type}",
            target_phase="Chatting",
            rollback_to="last_stable_checkpoint",
            preserve_stable=False,
        )

    def reset_phase(self, phase: str) -> None:
        """Reset retry/replan counters for a phase (e.g., after successful recovery)."""
        self._retry_counts.pop(phase, None)
        self._replan_counts.pop(phase, None)

    def reset_all(self) -> None:
        """Reset all recovery state."""
        self._retry_counts.clear()
        self._replan_counts.clear()
        self._failure_history.clear()

    @property
    def failure_history(self) -> list[FailureRecord]:
        return list(self._failure_history)

    def get_stats(self) -> dict[str, Any]:
        """Recovery statistics for observability."""
        total = len(self._failure_history)
        resolved = sum(1 for f in self._failure_history if f.resolved)
        by_level: dict[str, int] = {}
        for f in self._failure_history:
            if f.recovery_attempted:
                by_level[f.recovery_attempted] = by_level.get(f.recovery_attempted, 0) + 1
        return {
            "total_failures": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "by_recovery_level": by_level,
            "retry_counts": dict(self._retry_counts),
            "replan_counts": dict(self._replan_counts),
        }
