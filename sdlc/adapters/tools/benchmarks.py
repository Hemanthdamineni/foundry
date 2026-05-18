"""Performance benchmark adapter — tracks execution time and resource usage."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.tools.benchmarks")


class BenchmarkAdapter(ToolAdapter):
    """Runs benchmark scripts and tracks performance metrics."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self._workspace = Path(workspace)
        self._history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "benchmarks"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.TESTING

    async def validate(self, task: Any) -> bool:
        return True  # Benchmarks always available

    async def execute(self, task: Any) -> dict[str, Any]:
        """Run a benchmark command and track timing."""
        task_dict = task if isinstance(task, dict) else {}
        command = task_dict.get("command", "python -m pytest tests/ -q --tb=no")
        label = task_dict.get("label", "benchmark")
        threshold_ms = task_dict.get("threshold_ms", 0)

        parts = command.split()
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *parts,
            cwd=str(self._workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed_ms = (time.monotonic() - start) * 1000

        result = {
            "tool": "benchmarks",
            "label": label,
            "elapsed_ms": round(elapsed_ms, 2),
            "returncode": proc.returncode or 0,
            "passed": proc.returncode == 0,
            "output": stdout.decode("utf-8", errors="replace")[-1000:],
        }

        if threshold_ms > 0:
            result["threshold_ms"] = threshold_ms
            result["within_threshold"] = elapsed_ms <= threshold_ms
            if elapsed_ms > threshold_ms:
                result["regression"] = True
                result["regression_pct"] = round(
                    ((elapsed_ms - threshold_ms) / threshold_ms) * 100, 1,
                )

        self._history.append(result)
        return result

    async def healthcheck(self) -> bool:
        return True

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def trend(self, label: str) -> list[float]:
        """Get timing trend for a specific benchmark label."""
        return [
            r["elapsed_ms"] for r in self._history if r.get("label") == label
        ]
