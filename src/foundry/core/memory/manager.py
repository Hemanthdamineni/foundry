"""MemoryManager — tiered memory system (hot/warm/cold).

Wraps Acervo (cross-task memory) and ContextGraph (symbol-level repo understanding)
into a unified memory interface with three tiers:

- **Hot**: Current session context (most relevant, actively used)
- **Warm**: Recent task results and learned patterns (within last N tasks)
- **Cold**: Historical engrams and repository knowledge (archived)

Architecture reference:
    L5 Context & Memory — "Memory tiers (hot / warm / cold)"
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger
from foundry.core.models import Engram

log = get_logger("foundry.memory")


# --------------------------------------------------------------------------- #
#  Memory entry
# --------------------------------------------------------------------------- #


class MemoryTier:
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class MemoryEntry:
    """A single memory entry with tier metadata."""

    content: str
    tier: str
    source: str
    tags: tuple[str, ...] = ()
    importance: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tier": self.tier,
            "source": self.source,
            "tags": list(self.tags),
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_engram(cls, engram: Engram, tier: str = MemoryTier.WARM) -> MemoryEntry:
        return cls(
            content=engram.content,
            tier=tier,
            source=engram.source,
            tags=tuple(engram.tags),
            importance=engram.importance,
            metadata={"task_id": engram.task_id, "phase": engram.phase},
        )


# --------------------------------------------------------------------------- #
#  MemoryManager
# --------------------------------------------------------------------------- #


class MemoryManager:
    """Tiered memory system for agents.

    Usage::

        memory = MemoryManager(acervo=acervo, context_graph=graph)

        # Store a memory
        await memory.store(
            "Auth uses JWT tokens with 24h expiry",
            source="task_result",
            tags=["auth", "jwt"],
            tier="hot",
        )

        # Query across all tiers
        results = memory.query("authentication tokens", limit=10)

        # Get hot context for prompt assembly
        hot_context = memory.get_hot_context(max_tokens=2000)
    """

    # Tier size limits
    HOT_LIMIT = 50
    WARM_LIMIT = 200
    COLD_LIMIT = 1000

    # Auto-promotion/demotion thresholds
    ACCESS_THRESHOLD_FOR_WARM = 3  # Access count to promote to warm
    AGE_THRESHOLD_FOR_COLD = 3600  # 1 hour → cold

    def __init__(
        self,
        acervo: Any | None = None,
        context_graph: Any | None = None,
    ) -> None:
        self._acervo = acervo
        self._context_graph = context_graph
        self._hot: list[MemoryEntry] = []
        self._warm: list[MemoryEntry] = []
        self._cold: list[MemoryEntry] = []
        self._all_tags: dict[str, set[str]] = defaultdict(set)

    # -- Store -------------------------------------------------------------- #

    async def store(
        self,
        content: str,
        *,
        source: str = "unknown",
        tags: list[str] | None = None,
        importance: float = 0.5,
        tier: str = MemoryTier.HOT,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Store a memory entry."""
        entry = MemoryEntry(
            content=content,
            tier=tier,
            source=source,
            tags=tuple(tags or []),
            importance=importance,
            metadata=metadata or {},
        )

        # Add to tier
        tier_list = self._get_tier_list(tier)
        tier_list.append(entry)

        # Index tags
        for tag in entry.tags:
            self._all_tags[tag].add(content[:50])

        # Enforce tier limits
        self._enforce_limits()

        # Also store in Acervo if available
        if self._acervo:
            await self._acervo.store(
                content=content,
                tags=list(entry.tags),
                source=source,
                importance=importance,
            )

        log.debug("memory stored: %s (tier=%s, source=%s)", content[:50], tier, source)
        return entry

    # -- Query -------------------------------------------------------------- #

    def query(
        self,
        text: str,
        *,
        limit: int = 10,
        tier: str | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Query memory entries across all tiers.

        Uses tag matching and content search to find relevant memories.
        """
        words = set(text.lower().split())
        results: list[tuple[float, MemoryEntry]] = []

        tiers = [tier] if tier else [MemoryTier.HOT, MemoryTier.WARM, MemoryTier.COLD]

        for t in tiers:
            entries = self._get_tier_list(t)
            for entry in entries:
                score = self._score_entry(entry, words, tags)

                # Boost hot tier entries
                if t == MemoryTier.HOT:
                    score *= 1.5
                elif t == MemoryTier.WARM:
                    score *= 1.2

                if score > 0:
                    results.append((score, entry))

        # Sort by score, return top N
        results.sort(key=lambda x: x[0], reverse=True)

        # Update access metadata
        entries = []
        for _, entry in results[:limit]:
            entry.last_accessed = time.time()
            entry.access_count += 1
            entries.append(entry)

        return entries

    def get_hot_context(self, max_tokens: int = 2000) -> str:
        """Get hot memory as a context string for prompt assembly.

        Returns the most recent hot entries, formatted for inclusion
        in an LLM prompt.
        """
        parts: list[str] = []
        token_count = 0

        # Most recent first
        for entry in reversed(self._hot):
            # Rough token estimate: 1 token ≈ 4 chars
            entry_tokens = len(entry.content) // 4
            if token_count + entry_tokens > max_tokens:
                break
            parts.append(f"[{entry.source}] {entry.content}")
            token_count += entry_tokens

        return "\n".join(reversed(parts))

    # -- Tier management ---------------------------------------------------- #

    def promote(self, content: str) -> bool:
        """Promote a memory to a higher tier (cold→warm, warm→hot)."""
        # Find in cold
        for i, entry in enumerate(self._cold):
            if entry.content == content:
                self._cold.pop(i)
                entry.tier = MemoryTier.WARM
                self._warm.append(entry)
                log.debug("promoted to warm: %s", content[:50])
                return True

        # Find in warm
        for i, entry in enumerate(self._warm):
            if entry.content == content:
                self._warm.pop(i)
                entry.tier = MemoryTier.HOT
                self._hot.append(entry)
                log.debug("promoted to hot: %s", content[:50])
                return True

        return False

    def demote(self, content: str) -> bool:
        """Demote a memory to a lower tier (hot→warm, warm→cold)."""
        # Find in hot
        for i, entry in enumerate(self._hot):
            if entry.content == content:
                self._hot.pop(i)
                entry.tier = MemoryTier.WARM
                self._warm.append(entry)
                log.debug("demoted to warm: %s", content[:50])
                return True

        # Find in warm
        for i, entry in enumerate(self._warm):
            if entry.content == content:
                self._warm.pop(i)
                entry.tier = MemoryTier.COLD
                self._cold.append(entry)
                log.debug("demoted to cold: %s", content[:50])
                return True

        return False

    def auto_demote(self) -> int:
        """Auto-demote entries that haven't been accessed recently.

        Returns the number of entries demoted.
        """
        now = time.time()
        demoted = 0

        # Hot → Warm: entries older than threshold and not recently accessed
        for entry in list(self._hot):
            if (now - entry.created_at) > self.AGE_THRESHOLD_FOR_COLD and entry.access_count < 2:
                self._hot.remove(entry)
                entry.tier = MemoryTier.WARM
                self._warm.append(entry)
                demoted += 1

        # Warm → Cold: entries older than threshold
        for entry in list(self._warm):
            if (now - entry.created_at) > self.AGE_THRESHOLD_FOR_COLD:
                self._warm.remove(entry)
                entry.tier = MemoryTier.COLD
                self._cold.append(entry)
                demoted += 1

        if demoted:
            log.info("auto-demoted %d entries", demoted)

        return demoted

    # -- Stats -------------------------------------------------------------- #

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "hot": len(self._hot),
            "warm": len(self._warm),
            "cold": len(self._cold),
            "total": len(self._hot) + len(self._warm) + len(self._cold),
            "unique_tags": len(self._all_tags),
        }

    def get_all(self, tier: str | None = None) -> list[MemoryEntry]:
        if tier:
            return list(self._get_tier_list(tier))
        return list(self._hot) + list(self._warm) + list(self._cold)

    # -- Internal ----------------------------------------------------------- #

    def _get_tier_list(self, tier: str) -> list[MemoryEntry]:
        if tier == MemoryTier.HOT:
            return self._hot
        elif tier == MemoryTier.WARM:
            return self._warm
        elif tier == MemoryTier.COLD:
            return self._cold
        raise ValueError(f"Unknown tier: {tier}")

    def _enforce_limits(self) -> None:
        """Enforce tier size limits by demoting overflow to lower tiers."""
        # Hot overflow → warm
        while len(self._hot) > self.HOT_LIMIT:
            entry = self._hot.pop(0)
            entry.tier = MemoryTier.WARM
            self._warm.append(entry)

        # Warm overflow → cold
        while len(self._warm) > self.WARM_LIMIT:
            entry = self._warm.pop(0)
            entry.tier = MemoryTier.COLD
            self._cold.append(entry)

        # Cold overflow → discard
        while len(self._cold) > self.COLD_LIMIT:
            self._cold.pop(0)

    def _score_entry(
        self,
        entry: MemoryEntry,
        words: set[str],
        tags: list[str] | None,
    ) -> float:
        """Score a memory entry for relevance."""
        score = 0.0

        # Tag match
        if tags:
            for tag in tags:
                if tag in entry.tags:
                    score += 3.0

        # Content word match
        content_lower = entry.content.lower()
        for word in words:
            if word in content_lower:
                score += 1.0

        # Tag word match
        for word in words:
            for tag in entry.tags:
                if word in tag.lower():
                    score += 0.5

        # Importance boost
        score *= (0.5 + entry.importance)

        return score
