"""Approval gate — human-in-the-loop checkpoint approvals.

Provides the ApprovalQueue, data models, and a CLI interactive prompt
for approving or rejecting phase transitions that require human oversight.

Usage (SDLC runtime integration):
    from foundry.features.approval_gate import ApprovalQueue, ApprovalRequest

    queue = ApprovalQueue()
    queue.set_on_approve(on_approve_callback)
    queue.set_on_reject(on_reject_callback)

    # When a gated checkpoint is hit:
    request = queue.submit(task_id, phase, summary)

Usage (CLI / dashboard):
    from foundry.features.approval_gate import ApprovalQueue

    pending = queue.list_pending()
    queue.approve(request_id)
    queue.reject(request_id, reason="...")
"""

from foundry.features.approval_gate.models import ApprovalDecision, ApprovalRequest
from foundry.features.approval_gate.queue import ApprovalQueue

__all__ = [
    "ApprovalDecision",
    "ApprovalQueue",
    "ApprovalRequest",
]
