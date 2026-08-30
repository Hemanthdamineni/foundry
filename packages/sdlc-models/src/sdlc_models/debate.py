"""Debate / multi-agent consensus models for the SDLC pipeline.

From Helix/foundry/sdlc/models.py.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DebateAgentRole(StrEnum):
    """Role a debate agent plays in the multi-agent consensus protocol."""

    SPECS = "specs"
    PLANNING = "planning"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    CONSENSUS = "consensus"


class DebateAgentConfig(BaseModel):
    """Configuration for a single debate agent."""

    role: DebateAgentRole
    model: str = "qwen3:8b"
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024


class MinorityReport(BaseModel):
    """A dissenting opinion filed by one agent during consensus."""

    agent_role: str
    objection: str
    round_number: int
    severity: str = "info"


class CollapseSignal(BaseModel):
    """Signal detected when debate is collapsing toward a single view."""

    detected: bool = False
    confidence: float = 0.0
    reason: str = ""


class DebateRound(BaseModel):
    """One round of a multi-agent debate."""

    round_number: int
    responses: dict[str, str] = Field(default_factory=dict)
    previous_responses: dict[str, str] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""


class ConsensusResult(BaseModel):
    """Outcome of a full consensus process."""

    reached: bool = False
    passed: bool = False
    reason: str = ""
    disagreement_areas: list[str] = Field(default_factory=list)
    round_count: int = 0
    agent_verdicts: dict[str, bool] = Field(default_factory=dict)
    minority_reports: list[MinorityReport] = Field(default_factory=list)
    collapse_signal: CollapseSignal = Field(default_factory=CollapseSignal)
    residual_objections: list[str] = Field(default_factory=list)


class DebateTranscript(BaseModel):
    """Full transcript of a debate session for a task phase."""

    task_id: str
    phase: str
    output_preview: str = ""
    rounds: list[DebateRound] = Field(default_factory=list)
    consensus: ConsensusResult | None = None
    total_tokens_estimate: int = 0


class Engram(BaseModel):
    """A memorised knowledge fragment extracted during execution.

    Engrams form the basis of cross-task memory (the engram graph).
    """

    engram_id: str
    task_id: str
    phase: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str = "unknown"
    importance: float = 0.5
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "DebateAgentRole",
    "DebateAgentConfig",
    "MinorityReport",
    "CollapseSignal",
    "DebateRound",
    "ConsensusResult",
    "DebateTranscript",
    "Engram",
]
