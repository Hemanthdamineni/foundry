"""ExecutionPolicy — budget, retry, and failure classification. FSM never sees policy logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sdlc_mcp.models import BudgetPolicy, Decision, DecisionAction, FailureType, Task

MAX_RETRY_ATTEMPTS = 3
ESCALATION_THRESHOLD = 3


class ExecutionPolicy:
    """Policy decisions: should we proceed, retry, or abort?

    FSM calls Policy; Policy never calls FSM.
    """  # noqa: D400

    def __init__(self, default_budget: BudgetPolicy | None = None) -> None:
        self._default_budget = default_budget or BudgetPolicy()

    async def check_budget(self, task: Task, budget: BudgetPolicy | None = None) -> Decision:
        b = budget or self._default_budget
        if task.iteration_count >= b.max_review_cycles:
            return Decision(
                action=DecisionAction.ABORT,
                reason=f"max_review_cycles ({b.max_review_cycles}) exceeded",
                failure_type=FailureType.ORCHESTRATION_LIMIT,
            )
        if task.created_at:
            elapsed = (datetime.now(UTC) - task.created_at).total_seconds() / 60
            if elapsed > b.max_runtime_minutes:
                return Decision(
                    action=DecisionAction.ABORT,
                    reason=f"max_runtime_minutes ({b.max_runtime_minutes}) exceeded",
                    failure_type=FailureType.ORCHESTRATION_LIMIT,
                )
        return Decision(action=DecisionAction.PROCEED, reason="budget OK")

    async def classify_failure(self, error: str) -> FailureType:  # noqa: PLR0911
        error_lower = error.lower()
        if any(kw in error_lower for kw in ["timeout", "timed out", "connection reset"]):
            return FailureType.RETRYABLE_MODEL
        if any(kw in error_lower for kw in ["locked", "database", "disk"]):
            return FailureType.RETRYABLE_INFRA
        if any(kw in error_lower for kw in ["phase mismatch", "phase", "transition"]):
            return FailureType.TERMINAL_PHASE
        if any(kw in error_lower for kw in ["sandbox", "permission denied", "bwrap"]):
            return FailureType.TERMINAL_SANDBOX
        if any(kw in error_lower for kw in ["validation", "schema", "missing section"]):
            return FailureType.TERMINAL_VALIDATION
        if "model not found" in error_lower or "not pulled" in error_lower:
            return FailureType.TERMINAL_DEPENDENCY
        return FailureType.RETRYABLE_INFRA

    async def decide_retry(self, failure: FailureType, attempt: int) -> Decision:
        if failure in (FailureType.RETRYABLE_MODEL, FailureType.RETRYABLE_INFRA):
            if attempt < MAX_RETRY_ATTEMPTS:
                return Decision(
                    action=DecisionAction.RETRY,
                    reason=f"retryable {failure.value}, attempt {attempt + 1}",
                    retry_after_s=2 ** attempt,
                )
            return Decision(
                action=DecisionAction.ABORT,
                reason=f"max retries exceeded for {failure.value}",
                failure_type=failure,
            )
        if failure in (
            FailureType.TERMINAL_VALIDATION,
            FailureType.TERMINAL_PHASE,
            FailureType.TERMINAL_SANDBOX,
            FailureType.TERMINAL_CONSENSUS,
        ):
            return Decision(
                action=DecisionAction.ABORT,
                reason=f"terminal failure: {failure.value}",
                failure_type=failure,
            )
        return Decision(
            action=DecisionAction.ABORT,
            reason=f"unhandled failure: {failure.value}",
            failure_type=failure,
        )

    async def should_escalate(self, _task: Task, error_count: int) -> bool:
        return error_count >= ESCALATION_THRESHOLD
