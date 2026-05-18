"""SandboxAdapter — isolated subprocess execution with timeout and output limits."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from typing import Any

from sdlc_mcp.adapters.base import ToolAdapter, ToolCapability
from sdlc_mcp.config import SandboxConfig
from sdlc_mcp.log import get_logger

log = get_logger("sandbox")

_MAX_OUTPUT_BYTES = 1_048_576
_DEFAULT_TIMEOUT_S = 60


class SandboxAdapter(ToolAdapter):
    """Executes shell commands with isolation, timeout, and output limits."""

    name: str = "sandbox"
    capability: ToolCapability = ToolCapability.SANDBOX

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()
        self._bwrap_available = shutil.which("bwrap") is not None

    async def validate(self, task: Any) -> bool:
        if isinstance(task, dict):
            return "command" in task
        return False

    async def execute(self, task: Any) -> dict[str, Any]:
        if not isinstance(task, dict) or "command" not in task:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": "No command provided",
                "details": {},
            }

        command: str = task["command"]
        timeout_s: int = int(task.get("timeout", _DEFAULT_TIMEOUT_S))
        cwd: str | None = task.get("cwd")

        if self._config.enabled and self._bwrap_available:
            command = self._wrap_bwrap(command)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                cwd=cwd,
                timeout=timeout_s,
                check=False,
            )

            stdout_str = proc.stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]
            stderr_str = proc.stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]

            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": proc.returncode == 0,
                "summary": f"Exit code {proc.returncode}",
                "details": {
                    "command": command[:200],
                    "exit_code": proc.returncode,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "timeout": False,
                    "sandboxed": self._config.enabled and self._bwrap_available,
                },
            }

        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or b""
            stderr = e.stderr or b""
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": f"Command timed out after {timeout_s}s",
                "details": {
                    "command": command[:200],
                    "exit_code": -1,
                    "stdout": stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES],
                    "stderr": stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES],
                    "timeout": True,
                    "sandboxed": self._config.enabled and self._bwrap_available,
                },
            }
        except (OSError, ValueError) as e:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": str(e),
                "details": {"command": command[:200], "error": str(e)},
            }

    async def healthcheck(self) -> bool:
        if self._config.enabled:
            return self._bwrap_available
        return True

    def _wrap_bwrap(self, command: str) -> str:
        ro_binds = " ".join(f"--ro-bind {p} {p}" for p in self._config.readonly_paths)
        rw_binds = " ".join(f"--bind {p} {p}" for p in self._config.writable_paths)

        return (
            f"bwrap"
            f" --unshare-net"
            f" --proc /proc"
            f" --dev /dev"
            f" {ro_binds}"
            f" {rw_binds}"
            f" --unshare-uts"
            f" --unshare-ipc"
            f" --unshare-pid"
            f" --die-with-parent"
            f" bash -c {shlex.quote(command)}"
        )
