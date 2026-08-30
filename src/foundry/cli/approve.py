"""``foundry approve`` — manage pending approval requests.

Usage:
    foundry approve --list
    foundry approve --approve <id>
    foundry approve --reject <id> --reason "..."
"""

from __future__ import annotations

import argparse
import sys

from foundry.features.approval_gate import ApprovalQueue


def build_parser(sub: object | None = None) -> argparse.ArgumentParser:
    """Build the argument parser for the approve subcommand."""
    if sub is not None:
        # Hooked into main CLI's subparsers.
        p = sub.add_parser("approve", help="Manage pending approval requests")
    else:
        p = argparse.ArgumentParser(
            prog="foundry approve",
            description="Manage pending approval requests",
        )

    p.add_argument(
        "--list",
        action="store_true",
        help="List all pending approval requests",
    )
    p.add_argument(
        "--approve",
        metavar="ID",
        help="Approve a pending request by ID",
    )
    p.add_argument(
        "--reject",
        metavar="ID",
        help="Reject a pending request by ID",
    )
    p.add_argument(
        "--reason",
        metavar="TEXT",
        default="",
        help="Rejection reason (required with --reject)",
    )
    return p


def run_approve(args: argparse.Namespace) -> int:
    """Execute the approve subcommand."""
    queue = _get_global_queue()

    if args.list:
        return _cmd_list(queue)

    if args.approve:
        return _cmd_approve(queue, args.approve)

    if args.reject:
        return _cmd_reject(queue, args.reject, args.reason)

    print("foundry approve: specify --list, --approve, or --reject", file=sys.stderr)
    return 1


def _cmd_list(queue: ApprovalQueue) -> int:
    pending = queue.list_pending()
    if not pending:
        print("No pending approval requests.")
        return 0

    print(f"Pending approval requests ({len(pending)}):")
    print()
    for req in pending:
        status_icon = "\U0001f6a8"  # warning emoji fallback
        print(
            f"  {status_icon}  [{req.id}]  task={req.task_id}  "
            f"phase={req.phase}  created={req.created_at.isoformat()}"
        )
        print(f"       Summary: {req.summary}")
        print()
    return 0


def _cmd_approve(queue: ApprovalQueue, request_id: str) -> int:
    decision = queue.approve(request_id, resolved_by="cli")
    if decision is None:
        print(f"Request '{request_id}' not found or already resolved.", file=sys.stderr)
        return 1
    print(f"Request {request_id} approved.")
    return 0


def _cmd_reject(queue: ApprovalQueue, request_id: str, reason: str) -> int:
    if not reason:
        print("--reason is required when using --reject", file=sys.stderr)
        return 1
    decision = queue.reject(request_id, reason, resolved_by="cli")
    if decision is None:
        print(f"Request '{request_id}' not found or already resolved.", file=sys.stderr)
        return 1
    print(f"Request {request_id} rejected: {reason}")
    return 0


# ── Global queue (lazy singleton) ──────────────────────────────

_queue: ApprovalQueue | None = None


def _get_global_queue() -> ApprovalQueue:
    global _queue
    if _queue is None:
        _queue = ApprovalQueue()
    return _queue


if __name__ == "__main__":
    parser = build_parser()
    ns = parser.parse_args()
    sys.exit(run_approve(ns))
