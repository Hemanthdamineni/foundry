from __future__ import annotations

import pytest

from sdlc.adapters.memory import Acervo, MemoryAdapter
from sdlc.models import Engram


class TestEngramModel:
    def test_engram_defaults(self) -> None:
        e = Engram(engram_id="e1", task_id="t1", phase="Coding", content="test memory")
        assert e.tags == []
        assert e.source == "unknown"
        assert e.importance == 0.5
        assert e.created_at == ""

    def test_engram_full(self) -> None:
        e = Engram(
            engram_id="e1",
            task_id="t1",
            phase="Coding",
            content="Important insight",
            tags={"performance", "security"},
            source="judge",
            importance=0.9,
            created_at="2024-01-01T00:00:00",
        )
        assert "performance" in e.tags
        assert e.importance == 0.9

    def test_engram_roundtrip(self) -> None:
        e = Engram(
            engram_id="e1",
            task_id="t1",
            phase="Coding",
            content="test",
            tags=["bug"],
            source="user",
            importance=0.8,
        )
        data = e.model_dump(mode="json")
        restored = Engram(**data)
        assert restored.engram_id == "e1"
        assert restored.importance == 0.8


class TestAcervo:
    @pytest.mark.asyncio
    async def test_initialize_empty(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        assert acervo.stats["engram_count"] == 0

    @pytest.mark.asyncio
    async def test_store_and_query(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()

        e1 = await acervo.store(
            content="Use async/await for I/O",
            task_id="t1",
            phase="Coding",
            tags=["async", "best-practice"],
            source="review",
            importance=0.8,
        )
        await acervo.store(
            content="Add input validation",
            task_id="t2",
            phase="Review",
            tags=["security"],
            source="judge",
            importance=0.6,
        )

        assert e1.engram_id != ""
        assert acervo.stats["engram_count"] == 2

        results = await acervo.query(tags=["async"])
        assert len(results) == 1
        assert results[0].engram_id == e1.engram_id

    @pytest.mark.asyncio
    async def test_query_by_phase(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="c1", task_id="t1", phase="Coding")
        await acervo.store(content="c2", task_id="t2", phase="Review")
        await acervo.store(content="c3", task_id="t3", phase="Coding")

        results = await acervo.query(phase="Coding")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_by_keywords(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="Fix memory leak in cache")
        await acervo.store(content="Add unit tests for utils")

        results = await acervo.query(keywords=["memory", "leak"])
        assert len(results) == 1
        assert "memory leak" in results[0].content

    @pytest.mark.asyncio
    async def test_query_by_source(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="c1", source="judge")
        await acervo.store(content="c2", source="user")
        await acervo.store(content="c3", source="judge")

        results = await acervo.query(source="user")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_min_importance(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="low", importance=0.2)
        await acervo.store(content="high", importance=0.9)

        results = await acervo.query(min_importance=0.5)
        assert len(results) == 1
        assert "high" in results[0].content

    @pytest.mark.asyncio
    async def test_query_limit(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        for i in range(20):
            await acervo.store(content=f"item {i}")
        results = await acervo.query(limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_get_by_task(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="a", task_id="t1")
        await acervo.store(content="b", task_id="t2")
        await acervo.store(content="c", task_id="t1")

        results = await acervo.get_by_task("t1")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_by_id(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        e = await acervo.store(content="unique")
        found = await acervo.get_by_id(e.engram_id)
        assert found is not None
        assert found.engram_id == e.engram_id

        missing = await acervo.get_by_id("nonexistent")
        assert missing is None

    @pytest.mark.asyncio
    async def test_forget(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        e = await acervo.store(content="to forget")
        assert acervo.stats["engram_count"] == 1

        removed = await acervo.forget(e.engram_id)
        assert removed
        assert acervo.stats["engram_count"] == 0

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        removed = await acervo.forget("nonexistent")
        assert not removed

    @pytest.mark.asyncio
    async def test_clear(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="a")
        await acervo.store(content="b")
        count = await acervo.clear()
        assert count == 2
        assert acervo.stats["engram_count"] == 0

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path) -> None:
        store_dir = tmp_path / "memory"
        acervo1 = Acervo(store_dir)
        await acervo1.initialize()
        await acervo1.store(content="persistent", tags=["test"])
        assert acervo1.stats["engram_count"] == 1

        acervo2 = Acervo(store_dir)
        await acervo2.initialize()
        assert acervo2.stats["engram_count"] == 1
        results = await acervo2.query(tags=["test"])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_store_with_metadata(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        e = await acervo.store(
            content="with metadata",
            metadata={"model": "qwen3:8b", "tokens": 150},
        )
        assert e.metadata["model"] == "qwen3:8b"


class TestMemoryAdapter:
    @pytest.mark.asyncio
    async def test_healthcheck_no_acervo(self) -> None:
        adapter = MemoryAdapter()
        assert await adapter.healthcheck() is False

    @pytest.mark.asyncio
    async def test_healthcheck_with_acervo(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        adapter = MemoryAdapter(acervo=acervo)
        assert await adapter.healthcheck() is True

    @pytest.mark.asyncio
    async def test_validate_with_content(self) -> None:
        adapter = MemoryAdapter()
        assert await adapter.validate({"content": "test"}) is True

    @pytest.mark.asyncio
    async def test_validate_with_query(self) -> None:
        adapter = MemoryAdapter()
        assert await adapter.validate({"query": "test"}) is True

    @pytest.mark.asyncio
    async def test_validate_no_acervo(self) -> None:
        adapter = MemoryAdapter()
        assert await adapter.validate({}) is False

    @pytest.mark.asyncio
    async def test_execute_store(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        adapter = MemoryAdapter(acervo=acervo)

        result = await adapter.execute({
            "content": "Store this",
            "task_id": "t1",
            "tags": ["test"],
        })
        assert result["passed"]
        assert "engram_id" in result["details"]

    @pytest.mark.asyncio
    async def test_execute_query(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        await acervo.store(content="Find me", tags=["searchable"])
        adapter = MemoryAdapter(acervo=acervo)

        result = await adapter.execute({
            "query": True,
            "tags": ["searchable"],
        })
        assert result["passed"]
        assert result["details"]["count"] == 1

    @pytest.mark.asyncio
    async def test_execute_no_acervo(self) -> None:
        adapter = MemoryAdapter()
        result = await adapter.execute({"content": "test"})
        assert result["passed"] is False
        assert "not initialized" in result["summary"]

    @pytest.mark.asyncio
    async def test_execute_no_content_or_query(self, tmp_path) -> None:
        acervo = Acervo(tmp_path / "memory")
        await acervo.initialize()
        adapter = MemoryAdapter(acervo=acervo)
        result = await adapter.execute({})
        assert result["passed"] is False
