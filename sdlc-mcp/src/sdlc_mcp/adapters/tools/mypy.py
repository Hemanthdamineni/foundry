"""Mypy adapter — typing capability via mypy."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sdlc_mcp.adapters.base import ToolAdapter, ToolCapability


class MypyAdapter(ToolAdapter):
    """Runs ``mypy`` on a workspace path."""

    name: str = "mypy"
    capability: ToolCapability = ToolCapability.TYPING

    def __init__(self, mypy_path: str = "mypy") -> None:
        self._mypy_path = mypy_path

    async def validate(self, task: Any) -> bool:
        if not isinstance(task, dict):
            return False
        return "path" in task

    async def execute(self, task: Any) -> dict[str, Any]:
        path = task["path"] if isinstance(task, dict) else str(task)
        cmd = [self._mypy_path, "--show-error-codes", path]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": f"Tool not found: {self._mypy_path}",
                "details": [],
                "returncode": 127,
            }
        timeout_s = float(task.get("timeout_s", 30)) if isinstance(task, dict) else 30.0
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            stderr = (stderr or b"") + f"\nTimed out after {timeout_s:.0f}s".encode()
        returncode = proc.returncode or 0
        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        error_pattern = re.compile(
            r"^(.+?):(\d+):(?:(\d+):)?\s*(error|note|warning):\s*(.+)$", re.MULTILINE,
        )
        errors: list[dict[str, Any]] = [
            {
                "file": match.group(1),
                "line": int(match.group(2)),
                "severity": match.group(4),
                "message": match.group(5),
            }
            for match in error_pattern.finditer(stdout_str)
        ]

        passed = returncode == 0
        error_count = len(errors)
        summary = f"Found {error_count} type errors" if errors else "No type errors found"
        if stderr_str:
            summary += f"; stderr: {stderr_str[:200]}"

        return {
            "adapter": self.name,
            "capability": self.capability.value,
            "passed": passed,
            "summary": summary,
            "details": errors,
            "returncode": returncode,
        }

    async def healthcheck(self) -> bool:
        try:
            cmd = [self._mypy_path, "--version"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            await proc.wait()
            if proc.returncode != 0:
                return False
            return bool(stdout and stdout.decode("utf-8", errors="replace").strip())
        except FileNotFoundError:
            return False
