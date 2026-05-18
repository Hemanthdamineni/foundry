"""Execution budget controller — concrete enforcement of token, runtime, retry, and resource limits.

Responsibilities:
- Token budget tracking per phase and total
- Runtime budget with watchdog enforcement
- Retry budget per phase with backoff
- Resource limits (concurrent tasks, queue depth)
- Timeout enforcement per phase
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger
from sdlc.models import BudgetPolicy

logger = get_logger("runtime.budget_controller")


class PhaseBudget(BaseModel):
    """Budget tracking for a single phase."""

    phase: str
    tokens_used: int = 0
    tokens_limit: int = 0
    retries_used: int = 0
    retries_limit: int = 3
    time_started: float = 0.0
    timeout_s: float = 600.0  # 10 min default
    completed: bool = False


class BudgetSnapshot(BaseModel):
    """Point-in-time snapshot of all budget metrics."""

    task_id: str
    total_tokens_used: int = 0
    total_tokens_limit: int = 100_000
    total_runtime_s: float = 0.0
    max_runtime_s: float = 3600.0
    phase_budgets: dict[str, PhaseBudget] = Field(default_factory=dict)
    concurrent_tasks: int = 0
    max_concurrent_tasks: int = 3
    queue_depth: int = 0
    max_queue_depth: int = 10
    exhausted: bool = False
    exhaustion_reason: str = ""


class BudgetViolation(BaseModel):
    """A detected budget violation."""

    violation_type: str  # token, runtime, retry, resource, timeout
    severity: str = "warning"  # warning, error, critical
    message: str = ""
    current_value: float = 0.0
    limit_value: float = 0.0


class BudgetController:
    """Concrete budget enforcement for unattended autonomous execution.

    Unlike ExecutionPolicy (which answers should-we-proceed), this
    actively tracks consumption and enforces hard limits.
    """

    def __init__(
        self,
        policy: BudgetPolicy | None = None,
        max_concurrent_tasks: int = 3,
        max_queue_depth: int = 10,
    ) -> None:
        self._policy = policy or BudgetPolicy()
        self._max_concurrent = max_concurrent_tasks
        self._max_queue = max_queue_depth
        self._task_budgets: dict[str, BudgetSnapshot] = {}
        self._global_start = time.monotonic()
        self._active_task_count = 0
        self._queue_depth = 0

    # ── Task Budget ─────────────────────────────────────────────

    def init_task_budget(self, task_id: str, policy: BudgetPolicy | None = None) -> BudgetSnapshot:
        """Initialize budget tracking for a new task."""
        p = policy or self._policy
        snapshot = BudgetSnapshot(
            task_id=task_id,
            total_tokens_limit=p.max_total_tokens,
            max_runtime_s=p.max_runtime_minutes * 60,
            max_concurrent_tasks=self._max_concurrent,
            max_queue_depth=self._max_queue,
        )
        self._task_budgets[task_id] = snapshot
        return snapshot

    def get_budget(self, task_id: str) -> BudgetSnapshot | None:
        return self._task_budgets.get(task_id)

    # ── Token Tracking ──────────────────────────────────────────

    def consume_tokens(self, task_id: str, phase: str, tokens: int) -> list[BudgetViolation]:
        """Record token consumption and check limits."""
        snapshot = self._task_budgets.get(task_id)
        if snapshot is None:
            snapshot = self.init_task_budget(task_id)

        snapshot.total_tokens_used += tokens
        pb = snapshot.phase_budgets.setdefault(
            phase,
            PhaseBudget(phase=phase, tokens_limit=snapshot.total_tokens_limit // 6),
        )
        pb.tokens_used += tokens

        violations: list[BudgetViolation] = []
        if snapshot.total_tokens_used >= snapshot.total_tokens_limit:
            violations.append(BudgetViolation(
                violation_type="token",
                severity="critical",
                message=f"Total token budget exhausted: {snapshot.total_tokens_used}/{snapshot.total_tokens_limit}",
                current_value=snapshot.total_tokens_used,
                limit_value=snapshot.total_tokens_limit,
            ))
            snapshot.exhausted = True
            snapshot.exhaustion_reason = "token_budget_exceeded"

        # Warn at 80%
        if snapshot.total_tokens_used >= snapshot.total_tokens_limit * 0.8 and not snapshot.exhausted:
            violations.append(BudgetViolation(
                violation_type="token",
                severity="warning",
                message=f"Token budget at {snapshot.total_tokens_used}/{snapshot.total_tokens_limit} (80%+)",
                current_value=snapshot.total_tokens_used,
                limit_value=snapshot.total_tokens_limit,
            ))

        return violations

    # ── Runtime Tracking ────────────────────────────────────────

    def check_runtime(self, task_id: str) -> list[BudgetViolation]:
        """Check runtime budget for a task."""
        snapshot = self._task_budgets.get(task_id)
        if snapshot is None:
            return []

        elapsed = time.monotonic() - self._global_start
        snapshot.total_runtime_s = elapsed

        violations: list[BudgetViolation] = []
        if elapsed >= snapshot.max_runtime_s:
            violations.append(BudgetViolation(
                violation_type="runtime",
                severity="critical",
                message=f"Runtime budget exhausted: {elapsed:.0f}s / {snapshot.max_runtime_s:.0f}s",
                current_value=elapsed,
                limit_value=snapshot.max_runtime_s,
            ))
            snapshot.exhausted = True
            snapshot.exhaustion_reason = "runtime_exceeded"

        return violations

    # ── Retry Tracking ──────────────────────────────────────────

    def consume_retry(self, task_id: str, phase: str) -> list[BudgetViolation]:
        """Record a retry and check retry limits."""
        snapshot = self._task_budgets.get(task_id)
        if snapshot is None:
            snapshot = self.init_task_budget(task_id)

        pb = snapshot.phase_budgets.setdefault(
            phase,
            PhaseBudget(phase=phase, retries_limit=3),
        )
        pb.retries_used += 1

        violations: list[BudgetViolation] = []
        if pb.retries_used >= pb.retries_limit:
            violations.append(BudgetViolation(
                violation_type="retry",
                severity="error",
                message=f"Retry budget for phase '{phase}' exhausted: {pb.retries_used}/{pb.retries_limit}",
                current_value=pb.retries_used,
                limit_value=pb.retries_limit,
            ))

        return violations

    # ── Phase Timeout ───────────────────────────────────────────

    def start_phase_timer(self, task_id: str, phase: str, timeout_s: float = 600.0) -> None:
        """Start the timeout timer for a phase."""
        snapshot = self._task_budgets.get(task_id)
        if snapshot is None:
            snapshot = self.init_task_budget(task_id)

        pb = snapshot.phase_budgets.setdefault(phase, PhaseBudget(phase=phase))
        pb.time_started = time.monotonic()
        pb.timeout_s = timeout_s

    def check_phase_timeout(self, task_id: str, phase: str) -> BudgetViolation | None:
        """Check if a phase has exceeded its timeout."""
        snapshot = self._task_budgets.get(task_id)
        if snapshot is None:
            return None

        pb = snapshot.phase_budgets.get(phase)
        if pb is None or pb.time_started == 0:
            return None

        elapsed = time.monotonic() - pb.time_started
        if elapsed >= pb.timeout_s:
            return BudgetViolation(
                violation_type="timeout",
                severity="error",
                message=f"Phase '{phase}' timed out: {elapsed:.0f}s / {pb.timeout_s:.0f}s",
                current_value=elapsed,
                limit_value=pb.timeout_s,
            )
        return None

    # ── Resource Limits ─────────────────────────────────────────

    def acquire_task_slot(self) -> bool:
        """Try to acquire a concurrent task slot."""
        if self._active_task_count >= self._max_concurrent:
            return False
        self._active_task_count += 1
        return True

    def release_task_slot(self) -> None:
        """Release a concurrent task slot."""
        self._active_task_count = max(0, self._active_task_count - 1)

    def check_queue_capacity(self) -> bool:
        """Check if the task queue has capacity."""
        return self._queue_depth < self._max_queue

    def update_queue_depth(self, depth: int) -> None:
        self._queue_depth = depth

    # ── Comprehensive Check ─────────────────────────────────────

    def full_check(self, task_id: str, phase: str) -> list[BudgetViolation]:
        """Run all budget checks for a task+phase."""
        violations: list[BudgetViolation] = []
        violations.extend(self.check_runtime(task_id))

        timeout = self.check_phase_timeout(task_id, phase)
        if timeout:
            violations.append(timeout)

        snapshot = self._task_budgets.get(task_id)
        if snapshot and snapshot.exhausted:
            violations.append(BudgetViolation(
                violation_type="exhausted",
                severity="critical",
                message=f"Budget exhausted: {snapshot.exhaustion_reason}",
            ))

        return violations

    def should_continue(self, task_id: str, phase: str) -> tuple[bool, str]:
        """Simple continue/stop check. Returns (should_continue, reason)."""
        violations = self.full_check(task_id, phase)
        critical = [v for v in violations if v.severity == "critical"]
        if critical:
            return False, critical[0].message
        return True, "budget OK"

    # ── Stats ───────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get budget controller statistics."""
        return {
            "active_tasks": self._active_task_count,
            "max_concurrent": self._max_concurrent,
            "queue_depth": self._queue_depth,
            "max_queue": self._max_queue,
            "uptime_s": round(time.monotonic() - self._global_start, 1),
            "task_budgets": {
                tid: {
                    "tokens": f"{s.total_tokens_used}/{s.total_tokens_limit}",
                    "runtime": f"{s.total_runtime_s:.0f}s/{s.max_runtime_s:.0f}s",
                    "exhausted": s.exhausted,
                }
                for tid, s in self._task_budgets.items()
            },
        }
