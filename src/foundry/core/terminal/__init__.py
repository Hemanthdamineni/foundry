"""Terminal runtime — subprocess execution environments for agents."""

from foundry.core.terminal.session import (
    ManagedProcess,
    ProcessResult,
    ProcessStatus,
    TerminalSession,
)

__all__ = [
    "ManagedProcess",
    "ProcessResult",
    "ProcessStatus",
    "TerminalSession",
]
