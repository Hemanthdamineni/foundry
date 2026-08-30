"""ApprovalQueue — human-in-the-loop gate for SDLC phase transitions.

Maintains a queue of pending ApprovalRequest instances. When the SDLC runtime
encounters a checkpoint gated by human approval, it submits a request here.
The CLI or dashboard calls approve/reject to signal the checkpoint to proceed
or roll back.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from foundry.core.logging import get_logger
from foundry.features.approval_gate.models import ApprovalDecision, ApprovalRequest

logger = get_logger("approval_gate.queue")

# Callback signatures — the SDLC runtime registers these.
OnApprove = Callable[[str, str], None]  # (task_id, phase) -> None
OnReject = Callable[[str, str, str], None]  # (task_id, phase, reason) -> None


class ApprovalQueue:
    """Thread-safe queue of pending approval requests.

    The SDLC runtime integrates by:
    1. Calling submit() when a gated checkpoint is hit.
    2. Registering approve/reject callbacks via set_on_approve / set_on_reject.

    The CLI / dashboard calls list_pending(), approve(), reject().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[str, ApprovalRequest] = {}
        self._on_approve: OnApprove | None = None
        self._on_reject: OnReject | None = None

    # ── Registration ───────────────────────────────────────────

    def set_on_approve(self, callback: OnApprove) -> None:
        """Register the callback invoked when a request is approved.

        The callback receives ``(task_id, phase)``.
        """
        self._on_approve = callback

    def set_on_reject(self, callback: OnReject) -> None:
        """Register the callback invoked when a request is rejected.

        The callback receives ``(task_id, phase, reason)``.
        """
        self._on_reject = callback

    # ── SDLC runtime API (submit) ───────────────────────────────

    def submit(
        self,
        task_id: str,
        phase: str,
        summary: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Submit a new approval request to the queue.

        Returns the created ApprovalRequest.
        """
        request = ApprovalRequest(
            id=_new_id(),
            task_id=task_id,
            phase=phase,
            summary=summary,
            metadata=metadata or {},
        )
        with self._lock:
            self._requests[request.id] = request
        logger.info(
            "Approval request submitted",
            extra={
                "request_id": request.id,
                "task_id": task_id,
                "phase": phase,
            },
        )
        return request

    # ── CLI / dashboard API ─────────────────────────────────────

    def list_pending(self) -> list[ApprovalRequest]:
        """Return all pending (unresolved) approval requests."""
        with self._lock:
            return [r for r in self._requests.values() if r.is_pending]

    def list_all(self) -> list[ApprovalRequest]:
        """Return every request (pending and resolved)."""
        with self._lock:
            return list(self._requests.values())

    def get(self, request_id: str) -> ApprovalRequest | None:
        """Look up a single request by ID."""
        with self._lock:
            return self._requests.get(request_id)

    def approve(
        self,
        request_id: str,
        *,
        resolved_by: str = "cli",
    ) -> ApprovalDecision | None:
        """Approve a pending request and fire the on_approve callback.

        Returns the ApprovalDecision, or None if the request was not found
        or is already resolved.
        """
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                logger.warning("Approve failed: unknown request", extra={"request_id": request_id})
                return None
            if not request.is_pending:
                logger.warning(
                    "Approve failed: request already resolved",
                    extra={"request_id": request_id},
                )
                return None

            request.resolved_at = datetime.now(UTC)
            request.resolved_by = resolved_by
            # reason stays None to indicate approval (vs rejection)

            decision = ApprovalDecision(
                request_id=request_id,
                approved=True,
                reason=None,
                resolved_by=resolved_by,
                resolved_at=request.resolved_at,
            )

            task_id = request.task_id
            phase = request.phase

        # Fire callback outside the lock to avoid deadlocks.
        self._fire_approve(task_id, phase)

        logger.info(
            "Approval granted",
            extra={
                "request_id": request_id,
                "task_id": task_id,
                "phase": phase,
                "resolved_by": resolved_by,
            },
        )
        return decision

    def reject(
        self,
        request_id: str,
        reason: str,
        *,
        resolved_by: str = "cli",
    ) -> ApprovalDecision | None:
        """Reject a pending request and fire the on_reject callback.

        Returns the ApprovalDecision, or None if the request was not found
        or is already resolved.
        """
        if not reason:
            logger.warning("Reject failed: reason is required")
            return None

        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                logger.warning("Reject failed: unknown request", extra={"request_id": request_id})
                return None
            if not request.is_pending:
                logger.warning(
                    "Reject failed: request already resolved",
                    extra={"request_id": request_id},
                )
                return None

            request.resolved_at = datetime.now(UTC)
            request.resolved_by = resolved_by
            request.reason = reason

            decision = ApprovalDecision(
                request_id=request_id,
                approved=False,
                reason=reason,
                resolved_by=resolved_by,
                resolved_at=request.resolved_at,
            )

            task_id = request.task_id
            phase = request.phase

        # Fire callback outside the lock.
        self._fire_reject(task_id, phase, reason)

        logger.info(
            "Approval rejected",
            extra={
                "request_id": request_id,
                "task_id": task_id,
                "phase": phase,
                "reason": reason,
                "resolved_by": resolved_by,
            },
        )
        return decision

    # ── Internal ────────────────────────────────────────────────

    def _fire_approve(self, task_id: str, phase: str) -> None:
        cb = self._on_approve
        if cb is not None:
            try:
                cb(task_id, phase)
            except Exception:
                logger.exception(
                    "on_approve callback failed",
                    extra={"task_id": task_id, "phase": phase},
                )

    def _fire_reject(self, task_id: str, phase: str, reason: str) -> None:
        cb = self._on_reject
        if cb is not None:
            try:
                cb(task_id, phase, reason)
            except Exception:
                logger.exception(
                    "on_reject callback failed",
                    extra={"task_id": task_id, "phase": phase},
                )

    def __len__(self) -> int:
        with self._lock:
            return len(self._requests)

    def clear(self) -> None:
        """Remove all requests (for testing)."""
        with self._lock:
            self._requests.clear()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]
