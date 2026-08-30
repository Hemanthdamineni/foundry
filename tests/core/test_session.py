"""Tests for SessionManager — persistent session state."""

from __future__ import annotations

import pytest

from foundry.core.session.manager import (
    SessionManager,
    SessionMessage,
    SessionState,
    SessionStatus,
)
from foundry.core.store import SqliteStore


@pytest.fixture
async def session_store() -> SqliteStore:
    store = SqliteStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def session_mgr(session_store: SqliteStore) -> SessionManager:
    return SessionManager(session_store)


class TestSessionMessage:
    def test_to_dict_roundtrip(self) -> None:
        msg = SessionMessage(
            role="user",
            content="Hello, world!",
            tool_calls=[{"name": "read_file", "args": {"path": "foo.py"}}],
        )
        d = msg.to_dict()
        restored = SessionMessage.from_dict(d)
        assert restored.role == "user"
        assert restored.content == "Hello, world!"
        assert restored.tool_calls == [{"name": "read_file", "args": {"path": "foo.py"}}]


class TestSessionState:
    def test_to_dict_roundtrip(self) -> None:
        state = SessionState(
            session_id="sess_test",
            workspace_id="ws_abc",
            messages=[
                SessionMessage(role="user", content="Hello"),
                SessionMessage(role="assistant", content="Hi there!"),
            ],
            current_phase="planning",
            active_tasks=["task_1", "task_2"],
        )
        d = state.to_dict()
        restored = SessionState.from_dict(d)
        assert restored.session_id == "sess_test"
        assert restored.workspace_id == "ws_abc"
        assert len(restored.messages) == 2
        assert restored.current_phase == "planning"
        assert restored.active_tasks == ["task_1", "task_2"]


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_session(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create(workspace_id="ws_abc")
        assert session.session_id.startswith("sess_")
        assert session.workspace_id == "ws_abc"
        assert session.status == SessionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_session(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        retrieved = await session_mgr.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_pause_resume(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        paused = await session_mgr.pause(session.session_id)
        assert paused.status == SessionStatus.PAUSED

        resumed = await session_mgr.resume(session.session_id)
        assert resumed.status == SessionStatus.RESUMED

    @pytest.mark.asyncio
    async def test_archive(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        archived = await session_mgr.archive(session.session_id)
        assert archived.status == SessionStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_add_message(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        msg = SessionMessage(role="user", content="Test message")
        updated = await session_mgr.add_message(session.session_id, msg)
        assert len(updated.messages) == 1
        assert updated.messages[0].content == "Test message"

    @pytest.mark.asyncio
    async def test_update_phase(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        updated = await session_mgr.update_phase(session.session_id, "executor")
        assert updated.current_phase == "executor"

    @pytest.mark.asyncio
    async def test_add_remove_task(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        updated = await session_mgr.add_task(session.session_id, "task_1")
        assert "task_1" in updated.active_tasks

        updated = await session_mgr.remove_task(session.session_id, "task_1")
        assert "task_1" not in updated.active_tasks

    @pytest.mark.asyncio
    async def test_update_context(self, session_mgr: SessionManager) -> None:
        session = await session_mgr.create()
        updated = await session_mgr.update_context(
            session.session_id,
            {"current_file": "auth.py", "open_files": ["auth.py", "api.py"]},
        )
        assert updated.context_window["current_file"] == "auth.py"
        assert len(updated.context_window["open_files"]) == 2

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_mgr: SessionManager) -> None:
        await session_mgr.create(workspace_id="ws_1")
        await session_mgr.create(workspace_id="ws_2")
        await session_mgr.create(workspace_id="ws_1")

        all_sessions = await session_mgr.list_sessions()
        assert len(all_sessions) == 3

        ws1_sessions = await session_mgr.list_sessions(workspace_id="ws_1")
        assert len(ws1_sessions) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, session_mgr: SessionManager) -> None:
        result = await session_mgr.get("nonexistent")
        assert result is None
