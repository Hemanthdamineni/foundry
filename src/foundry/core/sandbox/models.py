"""Data models for the sandbox execution subsystem."""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field


class SandboxResult(NamedTuple):
    """Result of a sandboxed command execution.

    Attributes:
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        exit_code: Process exit code (None if timed out before the process
            could be reaped).
        timed_out: True if the command was killed for exceeding the timeout.
    """

    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


class SandboxConfig(BaseModel):
    """Configuration for the sandbox executor.

    Attributes:
        enabled: If False, commands run without any sandbox restrictions
            (useful in development / tests that don't need isolation).
        timeout: Default timeout in seconds for command execution.
        readonly_paths: Filesystem paths the sandboxed process may read from
            but not write to.  Only enforced when a container/provider backend
            is active; the subprocess executor logs a warning when these are
            set without a container provider.
        writable_paths: Filesystem paths the sandboxed process may write to.
            Only enforced when a container/provider backend is active.
    """

    enabled: bool = Field(default=True)
    timeout: int = Field(default=30, ge=1, le=3600)
    readonly_paths: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list)
