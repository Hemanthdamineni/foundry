"""Live observability dashboard — reads from JSONL traces + task state.

Outputs structured dashboard data for monitoring autonomous execution:
- Execution timeline with phase durations
- Model utilization and confidence trends
- Validator health and queue state
- Benchmark regression detection
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.dashboard")


class PhaseTimeline(BaseModel):
    """Timeline entry for a single phase execution."""

    phase: str
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    status: str = "pending"
    iteration: int = 0
    model_used: str = ""


class ValidatorHealth(BaseModel):
    """Health status of validation tools."""

    name: str
    available: bool = True
    last_run_at: str = ""
    last_result: str = "unknown"  # pass, fail, error, unknown
    avg_duration_ms: float = 0.0


class DashboardSnapshot(BaseModel):
    """Complete dashboard state at a point in time."""

    timestamp: str = ""
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    phase_timeline: list[PhaseTimeline] = Field(default_factory=list)
    validator_health: list[ValidatorHealth] = Field(default_factory=list)
    model_utilization: dict[str, int] = Field(default_factory=dict)
    confidence_trend: list[float] = Field(default_factory=list)
    benchmark_trend: list[float] = Field(default_factory=list)
    queue_depth: int = 0
    retry_rate: float = 0.0
    regression_count: int = 0
    coverage_current: float = 0.0
    uptime_seconds: float = 0.0


class Dashboard:
    """Aggregates execution data into dashboard snapshots."""

    def __init__(self, trace_dir: str | Path = "data/traces") -> None:
        self._trace_dir = Path(trace_dir)
        self._started_at = datetime.now(UTC)
        self._model_usage: dict[str, int] = {}
        self._confidence_history: list[float] = []
        self._benchmark_history: list[float] = []
        self._phase_history: list[PhaseTimeline] = []
        self._validator_health: dict[str, ValidatorHealth] = {}
        self._task_counts = {"active": 0, "completed": 0, "failed": 0}

    def record_phase(
        self,
        phase: str,
        *,
        status: str = "completed",
        duration_ms: int = 0,
        iteration: int = 0,
        model_used: str = "",
    ) -> None:
        """Record a phase execution for the timeline."""
        entry = PhaseTimeline(
            phase=phase,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=duration_ms,
            status=status,
            iteration=iteration,
            model_used=model_used,
        )
        self._phase_history.append(entry)
        if model_used:
            self._model_usage[model_used] = self._model_usage.get(model_used, 0) + 1

    def record_confidence(self, confidence: float) -> None:
        self._confidence_history.append(confidence)

    def record_benchmark(self, elapsed_ms: float) -> None:
        self._benchmark_history.append(elapsed_ms)

    def record_validator(
        self,
        name: str,
        *,
        available: bool = True,
        result: str = "pass",
        duration_ms: float = 0.0,
    ) -> None:
        """Update validator health status."""
        existing = self._validator_health.get(name)
        if existing:
            existing.available = available
            existing.last_result = result
            existing.last_run_at = datetime.now(UTC).isoformat()
            # Rolling average
            existing.avg_duration_ms = (existing.avg_duration_ms + duration_ms) / 2
        else:
            self._validator_health[name] = ValidatorHealth(
                name=name,
                available=available,
                last_result=result,
                last_run_at=datetime.now(UTC).isoformat(),
                avg_duration_ms=duration_ms,
            )

    def update_task_counts(
        self,
        active: int = 0,
        completed: int = 0,
        failed: int = 0,
    ) -> None:
        self._task_counts = {
            "active": active,
            "completed": completed,
            "failed": failed,
        }

    def snapshot(self) -> DashboardSnapshot:
        """Generate a complete dashboard snapshot."""
        uptime = (datetime.now(UTC) - self._started_at).total_seconds()
        return DashboardSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            active_tasks=self._task_counts["active"],
            completed_tasks=self._task_counts["completed"],
            failed_tasks=self._task_counts["failed"],
            phase_timeline=self._phase_history[-50:],  # Last 50 entries
            validator_health=list(self._validator_health.values()),
            model_utilization=dict(self._model_usage),
            confidence_trend=self._confidence_history[-20:],
            benchmark_trend=self._benchmark_history[-20:],
            retry_rate=0.0,
            uptime_seconds=uptime,
        )

    def to_json(self) -> str:
        """Export dashboard as JSON."""
        return self.snapshot().model_dump_json(indent=2)

    def save(self, path: str | Path | None = None) -> None:
        """Save dashboard snapshot to disk."""
        if path is None:
            path = self._trace_dir / "live_dashboard.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
