"""Coverage tracking adapter — wraps pytest-cov for line/branch coverage analysis."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.tools.coverage")


class CoverageAdapter(ToolAdapter):
    """Runs pytest with coverage and parses results."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self._workspace = Path(workspace)

    @property
    def name(self) -> str:
        return "coverage"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.TESTING

    async def validate(self, task: Any) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def execute(self, task: Any) -> dict[str, Any]:
        """Run pytest with coverage and return parsed results."""
        task_dict = task if isinstance(task, dict) else {}
        target = task_dict.get("target", "tests/")
        source = task_dict.get("source", ".")

        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest", target,
            f"--cov={source}",
            "--cov-report=term-missing",
            "--cov-report=json:.coverage.json",
            "-q", "--tb=short",
            cwd=str(self._workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        errors = stderr.decode("utf-8", errors="replace")

        # Parse coverage percentage from output
        coverage_pct = self._parse_coverage(output)

        return {
            "tool": "coverage",
            "returncode": proc.returncode or 0,
            "coverage_percent": coverage_pct,
            "output": output[-2000:],  # Last 2000 chars
            "errors": errors[-500:] if errors else "",
            "passed": proc.returncode == 0,
        }

    async def healthcheck(self) -> bool:
        return await self.validate(None)

    def _parse_coverage(self, output: str) -> float:
        """Extract total coverage percentage from pytest-cov output."""
        for line in reversed(output.splitlines()):
            if "TOTAL" in line:
                parts = line.split()
                for part in reversed(parts):
                    cleaned = part.rstrip("%")
                    try:
                        return float(cleaned)
                    except ValueError:
                        continue
        return 0.0
