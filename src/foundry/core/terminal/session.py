"""TerminalSession — subprocess execution environments for agents.

Provides a managed subprocess execution layer that agents can use to
run commands, read output, and manage process lifecycle.

Architecture reference:
    L4 Repository Execution — "How are agents executed?"
    L7 Engineering Environment — "PTY / terminal integration"
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.terminal")


# --------------------------------------------------------------------------- #
#  Process state
# --------------------------------------------------------------------------- #


class ProcessStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass
class ProcessResult:
    """Result of a subprocess execution."""

    process_id: str
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    status: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and self.status == ProcessStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": self.duration_s,
            "status": self.status,
            "timed_out": self.timed_out,
        }


@dataclass
class ManagedProcess:
    """A managed subprocess with lifecycle tracking."""

    process_id: str
    command: str
    process: asyncio.subprocess.Process | None = None
    status: str = ProcessStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    stdout_buffer: list[str] = field(default_factory=list)
    stderr_buffer: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  TerminalSession
# --------------------------------------------------------------------------- #


class TerminalSession:
    """Manages subprocess execution for agents.

    Usage::

        terminal = TerminalSession(cwd="/path/to/repo")
        result = await terminal.run("python -m pytest tests/", timeout=60)
        if result.success:
            print(f"Tests passed in {result.duration_s:.1f}s")
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes
    MAX_OUTPUT = 100_000  # 100KB max output

    def __init__(
        self,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._env = {**os.environ, **(env or {})}
        self._processes: dict[str, ManagedProcess] = {}

    async def run(
        self,
        command: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        input_data: str | None = None,
    ) -> ProcessResult:
        """Run a command and wait for completion.

        Parameters
        ----------
        command:
            Shell command to execute.
        timeout:
            Maximum seconds to wait. Raises on timeout.
        cwd:
            Working directory (defaults to session cwd).
        env:
            Additional environment variables.
        input_data:
            Data to write to stdin.
        """
        process_id = f"proc_{uuid.uuid4().hex[:8]}"
        effective_cwd = cwd or self._cwd
        effective_env = {**self._env, **(env or {})}

        managed = ManagedProcess(
            process_id=process_id,
            command=command,
        )

        self._processes[process_id] = managed
        managed.status = ProcessStatus.RUNNING
        managed.started_at = time.time()

        log.info("process started: %s — %s", process_id, command)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                cwd=effective_cwd,
                env=effective_env,
            )
            managed.process = proc

            # Wait with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(
                        input=input_data.encode("utf-8") if input_data else None,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                managed.timed_out = True  # type: ignore[attr-defined]
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass

                managed.status = ProcessStatus.TIMEOUT
                managed.completed_at = time.time()

                log.warning("process timed out: %s after %.1fs", process_id, timeout)

                return ProcessResult(
                    process_id=process_id,
                    command=command,
                    exit_code=None,
                    stdout="",
                    stderr=f"Process timed out after {timeout}s",
                    duration_s=time.time() - managed.started_at,
                    status=ProcessStatus.TIMEOUT,
                    timed_out=True,
                )

            # Decode output
            stdout = stdout_bytes.decode("utf-8", errors="replace")[:self.MAX_OUTPUT]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[:self.MAX_OUTPUT]

            managed.stdout_buffer = [stdout]
            managed.stderr_buffer = [stderr]

            duration = time.time() - managed.started_at
            exit_code = proc.returncode

            managed.status = ProcessStatus.COMPLETED if exit_code == 0 else ProcessStatus.FAILED
            managed.completed_at = time.time()

            log.info(
                "process completed: %s (exit=%d, duration=%.1fs)",
                process_id,
                exit_code or -1,
                duration,
            )

            return ProcessResult(
                process_id=process_id,
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_s=duration,
                status=managed.status,
            )

        except Exception as exc:
            managed.status = ProcessStatus.FAILED
            managed.completed_at = time.time()
            duration = time.time() - managed.started_at

            log.error("process failed: %s — %s", process_id, exc)

            return ProcessResult(
                process_id=process_id,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_s=duration,
                status=ProcessStatus.FAILED,
            )

    async def run_background(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        """Start a command in the background. Returns process_id."""
        process_id = f"proc_{uuid.uuid4().hex[:8]}"
        effective_cwd = cwd or self._cwd
        effective_env = {**self._env, **(env or {})}

        managed = ManagedProcess(
            process_id=process_id,
            command=command,
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd,
                env=effective_env,
            )
            managed.process = proc
            managed.status = ProcessStatus.RUNNING
            managed.started_at = time.time()
            self._processes[process_id] = managed

            # Start background reader tasks
            asyncio.create_task(self._read_output(process_id, proc))

            log.info("background process started: %s — %s", process_id, command)
            return process_id

        except Exception as exc:
            log.error("failed to start background process: %s", exc)
            raise

    async def _read_output(self, process_id: str, proc: asyncio.subprocess.Process) -> None:
        """Read output from a background process."""
        managed = self._processes.get(process_id)
        if managed is None:
            return

        try:
            if proc.stdout:
                async for line in proc.stdout:
                    managed.stdout_buffer.append(line.decode("utf-8", errors="replace"))
            if proc.stderr:
                async for line in proc.stderr:
                    managed.stderr_buffer.append(line.decode("utf-8", errors="replace"))
        except Exception:
            pass
        finally:
            managed.status = ProcessStatus.COMPLETED
            managed.completed_at = time.time()

    def get_process(self, process_id: str) -> ManagedProcess | None:
        return self._processes.get(process_id)

    def list_processes(self, *, status: str | None = None) -> list[ManagedProcess]:
        results = list(self._processes.values())
        if status:
            results = [p for p in results if p.status == status]
        return results

    def kill(self, process_id: str) -> bool:
        """Kill a running process."""
        managed = self._processes.get(process_id)
        if managed is None or managed.process is None:
            return False

        try:
            managed.process.kill()
            managed.status = ProcessStatus.KILLED
            managed.completed_at = time.time()
            return True
        except ProcessLookupError:
            return False
