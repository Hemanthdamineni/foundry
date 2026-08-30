"""Tests for AuditTrail — structured audit logging."""

from __future__ import annotations

import pytest

from foundry.core.audit import AuditCategory, AuditEntry, AuditTrail


class TestAuditEntry:
    def test_to_dict(self) -> None:
        entry = AuditEntry(
            entry_id="audit_123",
            category=AuditCategory.USER_ACTION,
            action="create_task",
            actor="user_123",
            target="task_456",
            details={"prompt": "Implement auth"},
        )
        d = entry.to_dict()
        assert d["entry_id"] == "audit_123"
        assert d["category"] == "user_action"
        assert d["action"] == "create_task"
        assert d["actor"] == "user_123"
        assert d["target"] == "task_456"
        assert d["success"] is True


class TestAuditTrail:
    @pytest.mark.asyncio
    async def test_log_action(self) -> None:
        audit = AuditTrail()
        entry = await audit.log_action(
            category=AuditCategory.USER_ACTION,
            action="create_task",
            actor="user_123",
            target="task_456",
            details={"prompt": "Implement auth"},
        )
        assert entry.entry_id.startswith("audit_")
        assert entry.action == "create_task"
        assert entry.actor == "user_123"

    @pytest.mark.asyncio
    async def test_query_by_category(self) -> None:
        audit = AuditTrail()
        await audit.log_action(category=AuditCategory.USER_ACTION, action="create", actor="u1")
        await audit.log_action(category=AuditCategory.SECURITY_EVENT, action="login", actor="u1")

        results = await audit.query(category=AuditCategory.USER_ACTION)
        assert len(results) == 1
        assert results[0].action == "create"

    @pytest.mark.asyncio
    async def test_query_by_actor(self) -> None:
        audit = AuditTrail()
        await audit.log_action(category=AuditCategory.USER_ACTION, action="a1", actor="user1")
        await audit.log_action(category=AuditCategory.USER_ACTION, action="a2", actor="user2")

        results = await audit.query(actor="user1")
        assert len(results) == 1
        assert results[0].action == "a1"

    @pytest.mark.asyncio
    async def test_query_by_task_id(self) -> None:
        audit = AuditTrail()
        await audit.log_action(category=AuditCategory.TASK_LIFECYCLE, action="start", actor="sys", task_id="t1")
        await audit.log_action(category=AuditCategory.TASK_LIFECYCLE, action="start", actor="sys", task_id="t2")

        results = await audit.query(task_id="t1")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_since(self) -> None:
        audit = AuditTrail()
        import time
        t1 = time.time() - 10
        t2 = time.time()

        await audit.log_action(category=AuditCategory.USER_ACTION, action="old", actor="u1")
        # Manually set timestamp
        audit._entries[-1].timestamp = t1

        await audit.log_action(category=AuditCategory.USER_ACTION, action="new", actor="u1")

        results = await audit.query(since=t2 - 1)
        assert len(results) == 1
        assert results[0].action == "new"

    @pytest.mark.asyncio
    async def test_get_task_history(self) -> None:
        audit = AuditTrail()
        await audit.log_action(category=AuditCategory.TASK_LIFECYCLE, action="start", actor="sys", task_id="t1")
        await audit.log_action(category=AuditCategory.TASK_LIFECYCLE, action="complete", actor="sys", task_id="t1")
        await audit.log_action(category=AuditCategory.TASK_LIFECYCLE, action="start", actor="sys", task_id="t2")

        history = await audit.get_task_history("t1")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_max_entries(self) -> None:
        audit = AuditTrail()
        audit.MAX_ENTRIES = 5

        for i in range(10):
            await audit.log_action(category=AuditCategory.USER_ACTION, action=f"action_{i}", actor="u1")

        assert len(audit._entries) == 5
        # Most recent kept
        assert audit._entries[-1].action == "action_9"

    def test_stats(self) -> None:
        audit = AuditTrail()
        assert audit.stats["total_entries"] == 0

    def test_clear(self) -> None:
        audit = AuditTrail()
        audit._entries.append(AuditEntry(
            entry_id="e1",
            category="test",
            action="test",
            actor="u1",
        ))
        count = audit.clear()
        assert count == 1
        assert len(audit._entries) == 0
