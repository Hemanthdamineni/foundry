"""Deterministic replay — replay phase/execution/debate from stored traces and checkpoints.

TODO #20: Full deterministic replay for debugging and regression testing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.replay")


class ReplayStep(BaseModel):
    """A single step in a replay sequence."""

    step_index: int
    phase: str
    tool: str = ""
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""
    duration_ms: int = 0


class ReplaySession(BaseModel):
    """A complete replay session from trace data."""

    session_id: str
    task_id: str
    steps: list[ReplayStep] = Field(default_factory=list)
    source: str = ""  # trace file or checkpoint
    status: str = "pending"  # pending, replaying, completed, failed


class ReplayEngine:
    """Replays execution from stored traces for debugging and regression testing."""

    def __init__(self, trace_dir: str | Path = "data/traces") -> None:
        self._trace_dir = Path(trace_dir)
        self._sessions: dict[str, ReplaySession] = {}

    def load_from_trace(self, trace_id: str) -> ReplaySession | None:
        """Load a replay session from a trace file."""
        trace_path = self._trace_dir / f"{trace_id}.jsonl"
        if not trace_path.exists():
            return None

        steps: list[ReplayStep] = []
        for i, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                step = ReplayStep(
                    step_index=i,
                    phase=data.get("phase", ""),
                    tool=data.get("tool", ""),
                    input_data=data.get("input", {}),
                    output_data=data.get("output", {}),
                    timestamp=data.get("timestamp", ""),
                    duration_ms=data.get("duration_ms", 0),
                )
                steps.append(step)
            except json.JSONDecodeError:
                continue

        task_id = steps[0].input_data.get("task_id", "") if steps else ""
        session = ReplaySession(
            session_id=trace_id,
            task_id=task_id,
            steps=steps,
            source=str(trace_path),
        )
        self._sessions[trace_id] = session
        return session

    def load_from_checkpoint(
        self,
        checkpoint_dir: str | Path,
        task_id: str,
    ) -> ReplaySession | None:
        """Load replay data from checkpoint files."""
        cdir = Path(checkpoint_dir)
        checkpoint_files = sorted(cdir.glob(f"{task_id}_*.json"))
        if not checkpoint_files:
            return None

        steps: list[ReplayStep] = []
        for i, f in enumerate(checkpoint_files):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                step = ReplayStep(
                    step_index=i,
                    phase=data.get("phase", ""),
                    tool="checkpoint",
                    input_data=data,
                    timestamp=data.get("created_at", ""),
                )
                steps.append(step)
            except (json.JSONDecodeError, OSError):
                continue

        session = ReplaySession(
            session_id=f"checkpoint_{task_id}",
            task_id=task_id,
            steps=steps,
            source=str(cdir),
        )
        self._sessions[session.session_id] = session
        return session

    def get_phase_replay(
        self,
        session_id: str,
        phase: str,
    ) -> list[ReplayStep]:
        """Get all steps for a specific phase in a replay session."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return [s for s in session.steps if s.phase == phase]

    def compare_runs(
        self,
        session_a: str,
        session_b: str,
    ) -> dict[str, Any]:
        """Compare two replay sessions for regression detection."""
        a = self._sessions.get(session_a)
        b = self._sessions.get(session_b)
        if not a or not b:
            return {"error": "Session not found"}

        return {
            "session_a": session_a,
            "session_b": session_b,
            "steps_a": len(a.steps),
            "steps_b": len(b.steps),
            "phases_a": list({s.phase for s in a.steps}),
            "phases_b": list({s.phase for s in b.steps}),
            "phase_diff": list(
                {s.phase for s in a.steps} ^ {s.phase for s in b.steps},
            ),
        }
