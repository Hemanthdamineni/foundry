"""CLI interactive prompt for human-in-the-loop approval in headless/CI mode.

Provides a blocking ``wait_for_decision(request)`` function that prints the
pending request details to stdout and waits for the operator's input.

Designed so that a CI pipeline can tee stdout and a human operator can
respond via a companion script or manually.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from foundry.features.approval_gate.models import ApprovalRequest
from foundry.features.approval_gate.queue import ApprovalQueue


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def display_pending(request: ApprovalRequest) -> None:
    """Pretty-print an approval request to the terminal."""
    print()
    print(_bold("=" * 60))
    print(_bold(f"  APPROVAL REQUIRED  —  {request.id}"))
    print(_bold("=" * 60))
    print(f"  Task:   {_yellow(request.task_id)}")
    print(f"  Phase:  {_yellow(request.phase)}")
    print(f"  Summary: {request.summary}")
    print(f"  Created: {request.created_at.isoformat()}")
    print(_bold("-" * 60))


def prompt_for_input() -> str:
    """Read a single-line decision from stdin."""
    try:
        return input(_bold("  [a]pprove / [r]eject / [s]kip > ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "skip"


def prompt_for_reason() -> str:
    """Prompt the operator for a rejection reason."""
    try:
        return input(_bold("  Reason for rejection > ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "interrupted"


def wait_for_decision(
    request: ApprovalRequest,
    queue: ApprovalQueue,
) -> None:
    """Block until the operator makes a decision on the given request.

    This is a simple interactive prompt. For non-interactive environments,
    the operator can directly call ``queue.approve()`` or ``queue.reject()``
    from another process.
    """
    while True:
        display_pending(request)
        choice = prompt_for_input()

        if choice in ("a", "approve", "y", "yes"):
            queue.approve(request.id, resolved_by="operator")
            print(_green(f"  Request {request.id} approved."))
            return

        if choice in ("r", "reject", "n", "no"):
            reason = prompt_for_reason()
            if not reason:
                print(_red("  Rejection reason cannot be empty. Try again."))
                continue
            queue.reject(request.id, reason, resolved_by="operator")
            print(_red(f"  Request {request.id} rejected."))
            return

        if choice in ("s", "skip", "q", "quit"):
            print(_yellow(f"  Request {request.id} skipped (left pending)."))
            return

        print(_red('  Invalid choice. Enter "a" to approve, "r" to reject, or "s" to skip.'))
