"""Semgrep security scanning adapter — static analysis for security vulnerabilities."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.tools.semgrep")


class SemgrepAdapter(ToolAdapter):
    """Runs semgrep with security rulesets and returns structured findings."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self._workspace = Path(workspace)

    @property
    def name(self) -> str:
        return "semgrep"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.TESTING

    async def validate(self, task: Any) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "semgrep", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def execute(self, task: Any) -> dict[str, Any]:
        """Run semgrep security scan and return findings."""
        task_dict = task if isinstance(task, dict) else {}
        target = task_dict.get("target", str(self._workspace))
        config = task_dict.get("config", "auto")

        proc = await asyncio.create_subprocess_exec(
            "semgrep", "--config", config,
            "--json", "--quiet",
            target,
            cwd=str(self._workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")

        findings: list[dict[str, Any]] = []
        try:
            data = json.loads(output)
            for result in data.get("results", []):
                findings.append({
                    "rule_id": result.get("check_id", "unknown"),
                    "severity": result.get("extra", {}).get("severity", "WARNING"),
                    "message": result.get("extra", {}).get("message", ""),
                    "path": result.get("path", ""),
                    "line": result.get("start", {}).get("line", 0),
                })
        except json.JSONDecodeError:
            pass

        return {
            "tool": "semgrep",
            "returncode": proc.returncode or 0,
            "finding_count": len(findings),
            "findings": findings[:50],  # Cap at 50
            "passed": len(findings) == 0,
            "errors": stderr.decode("utf-8", errors="replace")[-500:],
        }

    async def healthcheck(self) -> bool:
        return await self.validate(None)
