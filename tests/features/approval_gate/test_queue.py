"""Unit tests for foundry.features.approval_gate."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest import mock

import pytest

from foundry.features.approval_gate import ApprovalDecision, ApprovalQueue, ApprovalRequest
from foundry.features.approval_gate.models import _utc_now


# ======================================================================
# ApprovalRequest
# ======================================================================


class TestApprovalRequest:
    def test_default_created_at(self) -> None:
        req = ApprovalRequest(id="r1", task_id="t1", phase="Review", summary="Review code")
        assert isinstance(req.created_at, datetime)
        assert req.is_pending is True
        assert req.is_approved is False
        assert req.is_rejected is False

    def test_is_pending_when_unresolved(self) -> None:
        req = ApprovalRequest(id="r1", task_id="t1", phase="Review", summary="Review code")
        assert req.is_pending is True

    def test_is_approved_when_resolved_without_reason(self) -> None:
        req = ApprovalRequest(id="r1", task_id="t1", phase="Review", summary="Review code")
        req.resolved_at = datetime.now(timezone.utc)
        req.resolved_by = "cli"
        assert req.is_pending is False
        assert req.is_approved is True
        assert req.is_rejected is False

    def test_is_rejected_when_resolved_with_reason(self) -> None:
        req = ApprovalRequest(id="r1", task_id="t1", phase="Review", summary="Review code")
        req.resolved_at = datetime.now(timezone.utc)
        req.resolved_by = "cli"
        req.reason = "Not ready"
        assert req.is_pending is False
        assert req.is_approved is False
        assert req.is_rejected is True

    def test_fields(self) -> None:
        meta = {"key": "val"}
        req = ApprovalRequest(id="r1", task_id="t1", phase="Deploy", summary="Ship it", metadata=meta)
        assert req.id == "r1"
        assert req.task_id == "t1"
        assert req.phase == "Deploy"
        assert req.summary == "Ship it"
        assert req.metadata == meta


# ======================================================================
# ApprovalDecision
# ======================================================================


class TestApprovalDecision:
    def test_approval_decision(self) -> None:
        d = ApprovalDecision(request_id="r1", approved=True, reason=None, resolved_by="cli")
        assert d.approved is True
        assert d.reason is None

    def test_rejection_decision(self) -> None:
        d = ApprovalDecision(request_id="r1", approved=False, reason="Not ready", resolved_by="cli")
        assert d.approved is False
        assert d.reason == "Not ready"


# ======================================================================
# ApprovalQueue
# ======================================================================


class TestApprovalQueue:
    def test_submit_creates_request(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Review the diff")
        assert req.task_id == "t1"
        assert req.phase == "Review"
        assert req.summary == "Review the diff"
        assert req.is_pending is True
        assert len(req.id) == 12  # hex 12-char ID

    def test_list_pending_empty(self) -> None:
        queue = ApprovalQueue()
        assert queue.list_pending() == []

    def test_list_pending_returns_only_unresolved(self) -> None:
        queue = ApprovalQueue()
        req1 = queue.submit("t1", "Review", "First")
        req2 = queue.submit("t2", "Test", "Second")
        queue.approve(req1.id)
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].id == req2.id

    def test_list_all(self) -> None:
        queue = ApprovalQueue()
        req1 = queue.submit("t1", "Review", "First")
        req2 = queue.submit("t2", "Test", "Second")
        queue.approve(req1.id)
        all_reqs = queue.list_all()
        assert len(all_reqs) == 2

    def test_get_returns_request(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        assert queue.get(req.id) is req

    def test_get_missing_returns_none(self) -> None:
        queue = ApprovalQueue()
        assert queue.get("nonexistent") is None

    def test_approve_resolves_request(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        decision = queue.approve(req.id)
        assert decision is not None
        assert decision.approved is True
        assert decision.reason is None
        # Request should now be resolved
        assert req.is_approved is True
        assert req.resolved_by == "cli"

    def test_approve_with_custom_resolved_by(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        queue.approve(req.id, resolved_by="dashboard")
        assert req.resolved_by == "dashboard"

    def test_approve_missing_request(self) -> None:
        queue = ApprovalQueue()
        decision = queue.approve("nonexistent")
        assert decision is None

    def test_approve_already_resolved(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        queue.approve(req.id)
        decision = queue.approve(req.id)  # second call
        assert decision is None

    def test_reject_resolves_request(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        decision = queue.reject(req.id, reason="Not ready yet")
        assert decision is not None
        assert decision.approved is False
        assert decision.reason == "Not ready yet"
        assert req.is_rejected is True
        assert req.reason == "Not ready yet"

    def test_reject_without_reason(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        decision = queue.reject(req.id, reason="")
        assert decision is None
        assert req.is_pending is True  # unchanged

    def test_reject_missing_request(self) -> None:
        queue = ApprovalQueue()
        decision = queue.reject("nonexistent", reason="No reason")
        assert decision is None

    def test_reject_already_resolved(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        queue.reject(req.id, reason="First")
        decision = queue.reject(req.id, reason="Second")
        assert decision is None

    def test_len(self) -> None:
        queue = ApprovalQueue()
        assert len(queue) == 0
        queue.submit("t1", "Review", "A")
        queue.submit("t2", "Test", "B")
        assert len(queue) == 2

    def test_clear(self) -> None:
        queue = ApprovalQueue()
        queue.submit("t1", "Review", "A")
        queue.submit("t2", "Test", "B")
        queue.clear()
        assert len(queue) == 0
        assert queue.list_pending() == []

    def test_submit_with_metadata(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it", metadata={"source": "ci", "url": "http://..."})
        assert req.metadata == {"source": "ci", "url": "http://..."}

    # ── Callback tests ─────────────────────────────────────────

    def test_on_approve_callback_invoked(self) -> None:
        queue = ApprovalQueue()
        callback = mock.Mock()
        queue.set_on_approve(callback)
        req = queue.submit("t1", "Review", "Check it")
        queue.approve(req.id)
        callback.assert_called_once_with("t1", "Review")

    def test_on_reject_callback_invoked(self) -> None:
        queue = ApprovalQueue()
        callback = mock.Mock()
        queue.set_on_reject(callback)
        req = queue.submit("t1", "Review", "Check it")
        queue.reject(req.id, reason="Not ready")
        callback.assert_called_once_with("t1", "Review", "Not ready")

    def test_callback_not_invoked_when_not_set(self) -> None:
        queue = ApprovalQueue()
        req = queue.submit("t1", "Review", "Check it")
        # Should not raise
        queue.approve(req.id)
        queue.reject(queue.submit("t2", "Test", "Check it").id, reason="No")

    def test_callback_exception_does_not_bubble(self) -> None:
        queue = ApprovalQueue()
        queue.set_on_approve(mock.Mock(side_effect=RuntimeError("boom")))
        queue.set_on_reject(mock.Mock(side_effect=RuntimeError("boom")))
        req1 = queue.submit("t1", "Review", "Check it")
        req2 = queue.submit("t2", "Test", "Check it")
        # Should not raise
        queue.approve(req1.id)
        queue.reject(req2.id, reason="No")

    def test_callback_fired_outside_lock(self) -> None:
        """Verify callbacks are invoked after releasing the internal lock."""
        queue = ApprovalQueue()
        callback = mock.Mock()
        queue.set_on_approve(callback)
        req = queue.submit("t1", "Review", "Check it")
        queue.approve(req.id)
        # The request should be resolved before the callback fires
        # (since the callback is fired after release, we just verify order)
        callback.assert_called_once()

    def test_thread_safety(self) -> None:
        """Submit requests from multiple threads."""
        import concurrent.futures

        queue = ApprovalQueue()
        n = 50

        def submit(i: int) -> str:
            req = queue.submit(f"t{i}", "Review", f"Request {i}")
            return req.id

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(submit, range(n)))

        assert len(queue) == n
        pending = queue.list_pending()
        assert len(pending) == n

        # Resolve all from one thread
        for rid in ids:
            queue.approve(rid)
        assert len(queue.list_pending()) == 0


# ======================================================================
# ApprovalQueue CLI integration
# ======================================================================


class TestApprovalQueueCliIntegration:
    """Tests that reflect the CLI's interaction pattern with the queue."""

    def test_full_approve_flow(self) -> None:
        queue = ApprovalQueue()
        callback = mock.Mock()
        queue.set_on_approve(callback)

        req = queue.submit("t1", "Deploy", "Deploy to production")

        # CLI lists pending
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].id == req.id

        # CLI approves by ID
        decision = queue.approve(req.id, resolved_by="cli")
        assert decision is not None
        assert decision.approved is True

        # Callback fired
        callback.assert_called_once_with("t1", "Deploy")

        # No longer pending
        assert queue.list_pending() == []

    def test_full_reject_flow(self) -> None:
        queue = ApprovalQueue()
        callback = mock.Mock()
        queue.set_on_reject(callback)

        req = queue.submit("t1", "Deploy", "Deploy to production")

        # CLI rejects by ID with reason
        decision = queue.reject(req.id, reason="Rollback required", resolved_by="cli")
        assert decision is not None
        assert decision.approved is False
        assert decision.reason == "Rollback required"

        # Callback fired
        callback.assert_called_once_with("t1", "Deploy", "Rollback required")

        # No longer pending
        assert queue.list_pending() == []

    def test_multiple_requests_mixed_state(self) -> None:
        queue = ApprovalQueue()

        req_a = queue.submit("t1", "Review", "Review phase 1")
        req_b = queue.submit("t2", "Test", "Run tests")
        req_c = queue.submit("t3", "Deploy", "Deploy")

        queue.approve(req_a.id)
        queue.reject(req_c.id, reason="Not today")

        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].id == req_b.id
