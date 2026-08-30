"""Tests for Chronicle — append-only immutable event log."""

from __future__ import annotations

import json

import pytest

from foundry.core.chronicle import Chronicle, ChronicleEntry, _compute_hash
from foundry.core.store import SqliteStore


@pytest.fixture
async def in_memory_store() -> SqliteStore:
    store = SqliteStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


class TestComputeHash:
    def test_deterministic(self) -> None:
        h1 = _compute_hash(1, 1000.0, "test", {"key": "val"}, "prev")
        h2 = _compute_hash(1, 1000.0, "test", {"key": "val"}, "prev")
        assert h1 == h2

    def test_different_inputs_different_hashes(self) -> None:
        h1 = _compute_hash(1, 1000.0, "test", {"key": "val"}, "prev")
        h2 = _compute_hash(2, 1000.0, "test", {"key": "val"}, "prev")
        assert h1 != h2

    def test_hash_length(self) -> None:
        h = _compute_hash(1, 1000.0, "test", {}, "")
        assert len(h) == 16


class TestChronicleAppend:
    @pytest.mark.asyncio
    async def test_append_creates_entry(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        entry = await chronicle.append("task.created", {"prompt": "hello"})

        assert entry.sequence == 1
        assert entry.event_type == "task.created"
        assert entry.data["prompt"] == "hello"
        assert entry.previous_hash == "genesis"
        assert len(entry.entry_hash) == 16

    @pytest.mark.asyncio
    async def test_append_increments_sequence(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        e1 = await chronicle.append("event.a", {})
        e2 = await chronicle.append("event.b", {})

        assert e1.sequence == 1
        assert e2.sequence == 2
        assert e2.previous_hash == e1.entry_hash

    @pytest.mark.asyncio
    async def test_append_records_workspace_and_task(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        entry = await chronicle.append(
            "tool.executed",
            {"tool": "read_file"},
            workspace_id="ws_abc",
            task_id="task_123",
        )

        assert entry.workspace_id == "ws_abc"
        assert entry.task_id == "task_123"


class TestChronicleQuery:
    @pytest.mark.asyncio
    async def test_query_returns_entries(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        await chronicle.append("task.created", {"a": 1})
        await chronicle.append("phase.start", {"b": 2})

        entries = await chronicle.query()
        assert len(entries) == 2
        assert entries[0].sequence < entries[1].sequence

    @pytest.mark.asyncio
    async def test_query_filter_by_type(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        await chronicle.append("task.created", {})
        await chronicle.append("phase.start", {})
        await chronicle.append("task.completed", {})

        task_entries = await chronicle.query(event_type="task.created")
        assert len(task_entries) == 1

    @pytest.mark.asyncio
    async def test_query_filter_by_workspace(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        await chronicle.append("event.a", {}, workspace_id="ws_1")
        await chronicle.append("event.b", {}, workspace_id="ws_2")

        ws1_entries = await chronicle.query(workspace_id="ws_1")
        assert len(ws1_entries) == 1
        assert ws1_entries[0].workspace_id == "ws_1"


class TestChronicleVerify:
    @pytest.mark.asyncio
    async def test_verify_clean_chain(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        for i in range(5):
            await chronicle.append(f"event.{i}", {"i": i})

        is_valid, last_seq = await chronicle.verify_chain()
        assert is_valid is True
        assert last_seq == 5

    @pytest.mark.asyncio
    async def test_verify_empty_chain(self, in_memory_store: SqliteStore) -> None:
        chronicle = Chronicle(in_memory_store)
        is_valid, last_seq = await chronicle.verify_chain()
        assert is_valid is True
        assert last_seq == 0
