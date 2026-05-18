"""Progress tracker — structured convergence metrics for TODO #10.

Tracks:
- Tests fixed / new failures / coverage delta
- Retry effectiveness / regression count
- Benchmark trends / integration stability
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.progress_tracker")


class PhaseMetrics(BaseModel):
    """Metrics for a single phase execution."""

    phase: str
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    iteration: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_new_failures: int = 0
    coverage_before: float = 0.0
    coverage_after: float = 0.0
    lint_errors_before: int = 0
    lint_errors_after: int = 0
    type_errors_before: int = 0
    type_errors_after: int = 0


class ConvergenceMetrics(BaseModel):
    """Rolling convergence metrics across the task lifecycle."""

    task_id: str
    phase_metrics: list[PhaseMetrics] = Field(default_factory=list)
    retry_count: int = 0
    retry_success_count: int = 0
    regression_count: int = 0
    benchmark_trend: list[float] = Field(default_factory=list)
    integration_stability: float = 1.0  # 0.0 = unstable, 1.0 = stable
    total_iterations: int = 0
    coverage_delta: float = 0.0

    @property
    def retry_effectiveness(self) -> float:
        if self.retry_count == 0:
            return 1.0
        return self.retry_success_count / self.retry_count

    @property
    def progress_summary(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "total_iterations": self.total_iterations,
            "retry_effectiveness": round(self.retry_effectiveness, 3),
            "regression_count": self.regression_count,
            "integration_stability": round(self.integration_stability, 3),
            "coverage_delta": round(self.coverage_delta, 2),
            "benchmark_trend": self.benchmark_trend[-5:],  # Last 5 datapoints
            "phases_completed": len(self.phase_metrics),
        }


class ProgressTracker:
    """Tracks convergence and progress metrics across the task lifecycle."""

    def __init__(self) -> None:
        self._tasks: dict[str, ConvergenceMetrics] = {}

    def get_or_create(self, task_id: str) -> ConvergenceMetrics:
        if task_id not in self._tasks:
            self._tasks[task_id] = ConvergenceMetrics(task_id=task_id)
        return self._tasks[task_id]

    def start_phase(self, task_id: str, phase: str) -> PhaseMetrics:
        """Record phase start."""
        metrics = PhaseMetrics(
            phase=phase,
            started_at=datetime.now(UTC).isoformat(),
        )
        convergence = self.get_or_create(task_id)
        convergence.phase_metrics.append(metrics)
        return metrics

    def complete_phase(
        self,
        task_id: str,
        phase: str,
        *,
        tests_passed: int = 0,
        tests_failed: int = 0,
        coverage: float = 0.0,
        lint_errors: int = 0,
        type_errors: int = 0,
    ) -> None:
        """Record phase completion with metrics."""
        convergence = self.get_or_create(task_id)
        convergence.total_iterations += 1

        # Find the current phase metrics
        current = None
        for m in reversed(convergence.phase_metrics):
            if m.phase == phase and not m.completed_at:
                current = m
                break

        if current is None:
            current = self.start_phase(task_id, phase)

        current.completed_at = datetime.now(UTC).isoformat()
        current.tests_passed = tests_passed
        current.tests_failed = tests_failed
        current.coverage_after = coverage
        current.lint_errors_after = lint_errors
        current.type_errors_after = type_errors

        # Detect regressions
        prev_same_phase = [
            m for m in convergence.phase_metrics
            if m.phase == phase and m.completed_at and m is not current
        ]
        if prev_same_phase:
            prev = prev_same_phase[-1]
            if current.tests_failed > prev.tests_failed:
                convergence.regression_count += 1
                current.tests_new_failures = current.tests_failed - prev.tests_failed
            current.coverage_before = prev.coverage_after
            current.lint_errors_before = prev.lint_errors_after
            current.type_errors_before = prev.type_errors_after

        # Update coverage delta
        if convergence.phase_metrics:
            first_coverage = next(
                (m.coverage_after for m in convergence.phase_metrics if m.coverage_after > 0),
                0.0,
            )
            convergence.coverage_delta = coverage - first_coverage

    def record_retry(self, task_id: str, *, success: bool) -> None:
        """Record a retry attempt and its outcome."""
        convergence = self.get_or_create(task_id)
        convergence.retry_count += 1
        if success:
            convergence.retry_success_count += 1

    def record_benchmark(self, task_id: str, elapsed_ms: float) -> None:
        """Add a benchmark datapoint."""
        convergence = self.get_or_create(task_id)
        convergence.benchmark_trend.append(elapsed_ms)

    def update_integration_stability(self, task_id: str, stability: float) -> None:
        """Update integration stability score (0.0–1.0)."""
        convergence = self.get_or_create(task_id)
        convergence.integration_stability = max(0.0, min(1.0, stability))

    def get_progress(self, task_id: str) -> dict[str, Any]:
        """Get the full progress summary for a task."""
        convergence = self.get_or_create(task_id)
        return convergence.progress_summary

    def get_all_progress(self) -> dict[str, dict[str, Any]]:
        """Get progress for all tracked tasks."""
        return {tid: m.progress_summary for tid, m in self._tasks.items()}
