"""Bandit Python security linting adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.tools.bandit")


class BanditAdapter(ToolAdapter):
    """Runs bandit security linter on Python code."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self._workspace = Path(workspace)

    @property
    def name(self) -> str:
        return "bandit"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.TESTING

    async def validate(self, task: Any) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "bandit", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    async def execute(self, task: Any) -> dict[str, Any]:
        task_dict = task if isinstance(task, dict) else {}
        target = task_dict.get("target", str(self._workspace))
        severity = task_dict.get("min_severity", "low")

        proc = await asyncio.create_subprocess_exec(
            "bandit", "-r", target,
            f"-l" if severity == "low" else "-ll",
            "-f", "json", "--quiet",
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
                    "test_id": result.get("test_id", ""),
                    "severity": result.get("issue_severity", "LOW"),
                    "confidence": result.get("issue_confidence", "LOW"),
                    "text": result.get("issue_text", ""),
                    "filename": result.get("filename", ""),
                    "line": result.get("line_number", 0),
                })
        except json.JSONDecodeError:
            pass

        return {
            "tool": "bandit",
            "returncode": proc.returncode or 0,
            "finding_count": len(findings),
            "findings": findings[:50],
            "passed": len(findings) == 0,
        }

    async def healthcheck(self) -> bool:
        return await self.validate(None)
