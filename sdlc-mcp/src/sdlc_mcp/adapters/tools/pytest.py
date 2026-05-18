"""Pytest adapter — testing capability via pytest."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sdlc_mcp.adapters.base import ToolAdapter, ToolCapability


class PytestAdapter(ToolAdapter):
    """Runs ``pytest`` on a workspace path with JSON report output."""

    name: str = "pytest"
    capability: ToolCapability = ToolCapability.TESTING

    def __init__(self, pytest_path: str = "pytest") -> None:
        self._pytest_path = pytest_path

    async def validate(self, task: Any) -> bool:
        if not isinstance(task, dict):
            return False
        return "path" in task

    async def execute(self, task: Any) -> dict[str, Any]:
        path = task["path"] if isinstance(task, dict) else str(task)
        extra_args = task.get("args", []) if isinstance(task, dict) else []
        cmd = [self._pytest_path, "-p", "no:cacheprovider", *extra_args, path]
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
                "summary": f"Tool not found: {self._pytest_path}",
                "details": {
                    "passed": 0,
                    "failed": 0,
                    "errors": 1,
                    "total": 1,
                    "returncode": 127,
                },
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

        summary_pattern = re.compile(
            r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+errors?", re.MULTILINE,
        )
        passed = 0
        failed = 0
        errors = 0
        for match in summary_pattern.finditer(stdout_str):
            if match.group(1):
                passed += int(match.group(1))
            if match.group(2):
                failed += int(match.group(2))
            if match.group(3):
                errors += int(match.group(3))

        test_passed = returncode == 0 and failed == 0 and errors == 0
        total = passed + failed + errors
        summary = f"{passed}/{total} tests passed"
        if failed:
            summary += f", {failed} failed"
        if errors:
            summary += f", {errors} errors"
        if stderr_str:
            summary += f"; stderr: {stderr_str[:200]}"

        return {
            "adapter": self.name,
            "capability": self.capability.value,
            "passed": test_passed,
            "summary": summary,
            "details": {
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total": total,
                "returncode": returncode,
            },
            "returncode": returncode,
        }

    async def healthcheck(self) -> bool:
        try:
            cmd = [self._pytest_path, "--version"]
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
