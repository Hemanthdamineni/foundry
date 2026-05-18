"""Ruff adapter — lint capability via ruff check."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sdlc_mcp.adapters.base import ToolAdapter, ToolCapability


class RuffAdapter(ToolAdapter):
    """Runs ``ruff check`` on a workspace path."""

    name: str = "ruff"
    capability: ToolCapability = ToolCapability.LINT

    def __init__(self, ruff_path: str = "ruff") -> None:
        self._ruff_path = ruff_path

    async def validate(self, task: Any) -> bool:
        if not isinstance(task, dict):
            return False
        return "path" in task

    async def execute(self, task: Any) -> dict[str, Any]:
        path = task["path"] if isinstance(task, dict) else str(task)
        cmd = [self._ruff_path, "check", "--output-format", "json", path]
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
                "summary": f"Tool not found: {self._ruff_path}",
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

        issues: list[dict[str, Any]] = []
        if stdout_str.strip():
            try:
                raw = json.loads(stdout_str)
                if isinstance(raw, list):
                    issues = raw
            except json.JSONDecodeError:
                pass

        passed = returncode == 0 or len(issues) == 0
        summary = f"Found {len(issues)} lint issues" if issues else "No lint issues found"
        if stderr_str:
            summary += f"; stderr: {stderr_str[:200]}"

        return {
            "adapter": self.name,
            "capability": self.capability.value,
            "passed": passed,
            "summary": summary,
            "details": issues,
            "returncode": returncode,
        }

    async def healthcheck(self) -> bool:
        try:
            cmd = [self._ruff_path, "--version"]
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
