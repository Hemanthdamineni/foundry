"""Memory store — semantic retrieval layer over Acervo for long-running autonomy.

Provides structured retrieval by:
- Phase summaries (what happened in each phase)
- Error memory (past failures and their resolutions)
- Decision memory (why decisions were made)
- Pattern memory (recurring patterns and anti-patterns)
- Semantic keyword search across all engrams
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.adapters.memory.acervo import Acervo
from sdlc.log import get_logger
from sdlc.models import Engram

logger = get_logger("runtime.memory_store")


class PhaseSummary(BaseModel):
    """Summary of what happened in a specific phase."""

    task_id: str
    phase: str
    outcome: str = ""  # accepted, rejected, skipped
    key_decisions: list[str] = Field(default_factory=list)
    files_affected: list[str] = Field(default_factory=list)
    errors_encountered: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class ErrorMemory(BaseModel):
    """A stored error with its resolution for future reference."""

    error_type: str
    error_message: str
    phase: str = ""
    task_id: str = ""
    resolution: str = ""
    resolved: bool = False
    recurrence_count: int = 1


class DecisionRecord(BaseModel):
    """A recorded decision with rationale."""

    decision: str
    rationale: str
    phase: str = ""
    task_id: str = ""
    alternatives_considered: list[str] = Field(default_factory=list)
    outcome: str = ""


class MemoryStore:
    """Structured retrieval layer over Acervo for long-running autonomous execution.

    Provides typed retrieval methods that the orchestrator and subagents
    can call to recall past context without full history scanning.
    """

    def __init__(self, acervo: Acervo) -> None:
        self._acervo = acervo

    # ── Store Operations ────────────────────────────────────────

    async def store_phase_summary(self, summary: PhaseSummary) -> Engram:
        """Store a phase summary for later retrieval."""
        content = (
            f"Phase: {summary.phase}\n"
            f"Outcome: {summary.outcome}\n"
            f"Decisions: {'; '.join(summary.key_decisions)}\n"
            f"Files: {', '.join(summary.files_affected)}\n"
        )
        if summary.errors_encountered:
            content += f"Errors: {'; '.join(summary.errors_encountered)}\n"

        return await self._acervo.store(
            content=content,
            task_id=summary.task_id,
            phase=summary.phase,
            tags=["phase_summary", summary.phase, summary.outcome],
            source="phase_summary",
            importance=0.8,
            metadata=summary.model_dump(),
        )

    async def store_error(self, error: ErrorMemory) -> Engram:
        """Store an error for pattern matching against future failures."""
        content = (
            f"Error: {error.error_type}\n"
            f"Message: {error.error_message}\n"
            f"Resolution: {error.resolution}\n"
        )
        return await self._acervo.store(
            content=content,
            task_id=error.task_id,
            phase=error.phase,
            tags=["error", error.error_type, error.phase],
            source="error_memory",
            importance=0.9,
            metadata=error.model_dump(),
        )

    async def store_decision(self, decision: DecisionRecord) -> Engram:
        """Store a decision for future reference."""
        content = (
            f"Decision: {decision.decision}\n"
            f"Rationale: {decision.rationale}\n"
            f"Alternatives: {', '.join(decision.alternatives_considered)}\n"
        )
        return await self._acervo.store(
            content=content,
            task_id=decision.task_id,
            phase=decision.phase,
            tags=["decision", decision.phase],
            source="decision_record",
            importance=0.7,
            metadata=decision.model_dump(),
        )

    # ── Retrieval Operations ────────────────────────────────────

    async def get_phase_summaries(
        self,
        task_id: str,
        limit: int = 10,
    ) -> list[PhaseSummary]:
        """Retrieve phase summaries for a task."""
        engrams = await self._acervo.query(
            tags=["phase_summary"],
            source="phase_summary",
            limit=limit,
        )
        summaries: list[PhaseSummary] = []
        for e in engrams:
            if e.task_id == task_id and e.metadata:
                try:
                    summaries.append(PhaseSummary(**e.metadata))
                except (TypeError, ValueError):
                    continue
        return summaries

    async def get_error_history(
        self,
        *,
        error_type: str | None = None,
        phase: str | None = None,
        limit: int = 20,
    ) -> list[ErrorMemory]:
        """Retrieve past errors for pattern matching."""
        tags = ["error"]
        if error_type:
            tags.append(error_type)
        if phase:
            tags.append(phase)

        engrams = await self._acervo.query(
            tags=tags,
            source="error_memory",
            limit=limit,
        )
        errors: list[ErrorMemory] = []
        for e in engrams:
            if e.metadata:
                try:
                    errors.append(ErrorMemory(**e.metadata))
                except (TypeError, ValueError):
                    continue
        return errors

    async def find_similar_error(self, error_message: str) -> ErrorMemory | None:
        """Find a previously resolved error similar to the given message."""
        keywords = [w for w in error_message.lower().split() if len(w) > 3][:5]
        engrams = await self._acervo.query(
            tags=["error"],
            keywords=keywords,
            source="error_memory",
            limit=5,
        )
        for e in engrams:
            if e.metadata and e.metadata.get("resolved"):
                try:
                    return ErrorMemory(**e.metadata)
                except (TypeError, ValueError):
                    continue
        return None

    async def get_decisions(
        self,
        task_id: str,
        phase: str | None = None,
        limit: int = 10,
    ) -> list[DecisionRecord]:
        """Retrieve decisions for a task."""
        tags = ["decision"]
        if phase:
            tags.append(phase)

        engrams = await self._acervo.query(
            tags=tags,
            source="decision_record",
            limit=limit,
        )
        decisions: list[DecisionRecord] = []
        for e in engrams:
            if e.task_id == task_id and e.metadata:
                try:
                    decisions.append(DecisionRecord(**e.metadata))
                except (TypeError, ValueError):
                    continue
        return decisions

    async def search(
        self,
        keywords: list[str],
        *,
        phase: str | None = None,
        limit: int = 10,
    ) -> list[Engram]:
        """Semantic keyword search across all memory."""
        return await self._acervo.query(
            keywords=keywords,
            phase=phase,
            limit=limit,
        )

    async def get_context_for_phase(
        self,
        task_id: str,
        phase: str,
    ) -> dict[str, Any]:
        """Get all relevant context for a specific phase execution.

        Combines:
        - Phase summaries from earlier phases
        - Relevant error history
        - Past decisions
        """
        summaries = await self.get_phase_summaries(task_id)
        errors = await self.get_error_history(phase=phase, limit=5)
        decisions = await self.get_decisions(task_id, limit=5)

        return {
            "phase_summaries": [s.model_dump() for s in summaries],
            "relevant_errors": [e.model_dump() for e in errors],
            "past_decisions": [d.model_dump() for d in decisions],
            "total_memory_items": len(summaries) + len(errors) + len(decisions),
        }

    # ── Stats ───────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        return self._acervo.stats
