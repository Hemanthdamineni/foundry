"""Retry policy engine — structured retry classification and escalation.

TODO #10: Without structured retries, infinite loops appear and retries become random.
Extends execution_policy.py with failure-type routing, adaptive budgets, and effectiveness scoring.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.retry_policy")


class RetryLevel:
    LOCAL_RETRY = "local_retry"
    LOCAL_REPLAN = "local_replan"
    PHASE_RETRY = "phase_retry"
    STRUCTURAL_REPLAN = "structural_replan"
    FULL_RECOVERY = "full_recovery"


class FailureClassification(BaseModel):
    """Classified failure with recommended retry strategy."""

    failure_type: str  # syntax, test, lint, timeout, crash, logic, integration
    severity: str = "medium"  # low, medium, high, critical
    recommended_level: str = RetryLevel.LOCAL_RETRY
    transient: bool = True
    message: str = ""


class RetryAttempt(BaseModel):
    """A recorded retry attempt."""

    phase: str
    level: str
    attempt: int
    max_attempts: int
    succeeded: bool = False
    failure_type: str = ""
    duration_ms: float = 0.0


class RetryPolicy:
    """Structured retry classification with escalation and effectiveness scoring."""

    def __init__(
        self,
        max_local_retries: int = 3,
        max_phase_retries: int = 2,
        max_structural_replans: int = 1,
    ) -> None:
        self._max = {
            RetryLevel.LOCAL_RETRY: max_local_retries,
            RetryLevel.LOCAL_REPLAN: 2,
            RetryLevel.PHASE_RETRY: max_phase_retries,
            RetryLevel.STRUCTURAL_REPLAN: max_structural_replans,
            RetryLevel.FULL_RECOVERY: 1,
        }
        self._counts: dict[str, dict[str, int]] = {}  # phase → level → count
        self._attempts: list[RetryAttempt] = []

    def classify_failure(self, error: str, phase: str = "") -> FailureClassification:
        """Classify a failure and recommend a retry strategy."""
        error_lower = error.lower()

        if any(kw in error_lower for kw in ["syntax", "indent", "parse"]):
            return FailureClassification(
                failure_type="syntax", severity="low",
                recommended_level=RetryLevel.LOCAL_RETRY,
                transient=True, message=error[:200],
            )
        if any(kw in error_lower for kw in ["test", "assert", "expect"]):
            return FailureClassification(
                failure_type="test", severity="medium",
                recommended_level=RetryLevel.LOCAL_RETRY,
                transient=True, message=error[:200],
            )
        if any(kw in error_lower for kw in ["lint", "ruff", "style"]):
            return FailureClassification(
                failure_type="lint", severity="low",
                recommended_level=RetryLevel.LOCAL_RETRY,
                transient=True, message=error[:200],
            )
        if any(kw in error_lower for kw in ["timeout", "timed out"]):
            return FailureClassification(
                failure_type="timeout", severity="medium",
                recommended_level=RetryLevel.PHASE_RETRY,
                transient=True, message=error[:200],
            )
        if any(kw in error_lower for kw in ["import", "module", "dependency"]):
            return FailureClassification(
                failure_type="integration", severity="high",
                recommended_level=RetryLevel.STRUCTURAL_REPLAN,
                transient=False, message=error[:200],
            )
        if any(kw in error_lower for kw in ["crash", "segfault", "killed"]):
            return FailureClassification(
                failure_type="crash", severity="critical",
                recommended_level=RetryLevel.FULL_RECOVERY,
                transient=False, message=error[:200],
            )
        return FailureClassification(
            failure_type="unknown", severity="medium",
            recommended_level=RetryLevel.LOCAL_RETRY,
            transient=True, message=error[:200],
        )

    def can_retry(self, phase: str, level: str) -> bool:
        """Check if a retry at the given level is allowed."""
        current = self._counts.get(phase, {}).get(level, 0)
        max_allowed = self._max.get(level, 0)
        return current < max_allowed

    def consume_retry(self, phase: str, level: str) -> RetryAttempt:
        """Consume a retry and return the attempt record."""
        phase_counts = self._counts.setdefault(phase, {})
        count = phase_counts.get(level, 0) + 1
        phase_counts[level] = count

        attempt = RetryAttempt(
            phase=phase, level=level,
            attempt=count, max_attempts=self._max.get(level, 0),
        )
        self._attempts.append(attempt)
        return attempt

    def escalate(self, phase: str, current_level: str) -> str | None:
        """Escalate to the next retry level if current is exhausted."""
        levels = [
            RetryLevel.LOCAL_RETRY,
            RetryLevel.LOCAL_REPLAN,
            RetryLevel.PHASE_RETRY,
            RetryLevel.STRUCTURAL_REPLAN,
            RetryLevel.FULL_RECOVERY,
        ]
        try:
            idx = levels.index(current_level)
        except ValueError:
            return None
        for next_level in levels[idx + 1:]:
            if self.can_retry(phase, next_level):
                return next_level
        return None

    def effectiveness_score(self, phase: str) -> float:
        """Score retry effectiveness — ratio of successful retries."""
        phase_attempts = [a for a in self._attempts if a.phase == phase]
        if not phase_attempts:
            return 1.0
        succeeded = sum(1 for a in phase_attempts if a.succeeded)
        return succeeded / len(phase_attempts)

    def no_progress_detected(self, phase: str, window: int = 3) -> bool:
        """Detect if recent retries show no progress."""
        phase_attempts = [a for a in self._attempts if a.phase == phase]
        if len(phase_attempts) < window:
            return False
        recent = phase_attempts[-window:]
        return all(not a.succeeded for a in recent)

    def reset(self, phase: str) -> None:
        self._counts.pop(phase, None)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_attempts": len(self._attempts),
            "by_phase": {
                phase: dict(levels)
                for phase, levels in self._counts.items()
            },
        }
