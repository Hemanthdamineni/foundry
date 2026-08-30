"""Tests for MemoryManager — tiered memory system."""

from __future__ import annotations

import pytest

from foundry.core.memory.manager import MemoryManager, MemoryEntry, MemoryTier


class TestMemoryEntry:
    def test_to_dict(self) -> None:
        entry = MemoryEntry(
            content="Auth uses JWT",
            tier=MemoryTier.HOT,
            source="task_result",
            tags=("auth", "jwt"),
            importance=0.8,
        )
        d = entry.to_dict()
        assert d["content"] == "Auth uses JWT"
        assert d["tier"] == "hot"
        assert d["tags"] == ["auth", "jwt"]


class TestMemoryManager:
    @pytest.mark.asyncio
    async def test_store_and_query(self) -> None:
        memory = MemoryManager()
        await memory.store(
            "Auth uses JWT tokens with 24h expiry",
            source="task_result",
            tags=["auth", "jwt"],
        )
        results = memory.query("authentication tokens")
        assert len(results) == 1
        assert "JWT" in results[0].content

    @pytest.mark.asyncio
    async def test_store_hot_tier(self) -> None:
        memory = MemoryManager()
        await memory.store("Test content", tier=MemoryTier.HOT)
        assert len(memory._hot) == 1

    @pytest.mark.asyncio
    async def test_store_warm_tier(self) -> None:
        memory = MemoryManager()
        await memory.store("Test content", tier=MemoryTier.WARM)
        assert len(memory._warm) == 1

    @pytest.mark.asyncio
    async def test_store_cold_tier(self) -> None:
        memory = MemoryManager()
        await memory.store("Test content", tier=MemoryTier.COLD)
        assert len(memory._cold) == 1

    @pytest.mark.asyncio
    async def test_query_by_tags(self) -> None:
        memory = MemoryManager()
        await memory.store("Auth login", tags=["auth", "login"])
        await memory.store("Database query", tags=["db", "query"])

        results = memory.query("auth", tags=["auth"])
        assert len(results) == 1
        assert "Auth" in results[0].content

    @pytest.mark.asyncio
    async def test_query_cross_tier(self) -> None:
        memory = MemoryManager()
        await memory.store("Hot memory", tier=MemoryTier.HOT)
        await memory.store("Warm memory", tier=MemoryTier.WARM)
        await memory.store("Cold memory", tier=MemoryTier.COLD)

        results = memory.query("memory")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_hot_tier_boosted(self) -> None:
        memory = MemoryManager()
        await memory.store("Auth hot", tier=MemoryTier.HOT, tags=["auth"])
        await memory.store("Auth warm", tier=MemoryTier.WARM, tags=["auth"])

        results = memory.query("auth")
        assert len(results) == 2
        # Hot should rank higher
        assert results[0].tier == MemoryTier.HOT

    @pytest.mark.asyncio
    async def test_promote(self) -> None:
        memory = MemoryManager()
        await memory.store("Test", tier=MemoryTier.COLD)
        assert memory.promote("Test") is True
        assert len(memory._warm) == 1

    @pytest.mark.asyncio
    async def test_demote(self) -> None:
        memory = MemoryManager()
        await memory.store("Test", tier=MemoryTier.HOT)
        assert memory.demote("Test") is True
        assert len(memory._warm) == 1

    @pytest.mark.asyncio
    async def test_tier_limits(self) -> None:
        memory = MemoryManager()
        memory.HOT_LIMIT = 3
        memory.WARM_LIMIT = 3

        # Store 5 hot entries — should overflow to warm
        for i in range(5):
            await memory.store(f"Entry {i}", tier=MemoryTier.HOT)

        assert len(memory._hot) == 3
        assert len(memory._warm) == 2

    def test_get_hot_context(self) -> None:
        memory = MemoryManager()
        memory._hot = [
            MemoryEntry(content="Line 1", tier="hot", source="test"),
            MemoryEntry(content="Line 2", tier="hot", source="test"),
        ]
        ctx = memory.get_hot_context()
        assert "Line 1" in ctx
        assert "Line 2" in ctx

    def test_stats(self) -> None:
        memory = MemoryManager()
        assert memory.stats["total"] == 0
        memory._hot.append(MemoryEntry(content="a", tier="hot", source="test"))
        assert memory.stats["hot"] == 1
        assert memory.stats["total"] == 1
