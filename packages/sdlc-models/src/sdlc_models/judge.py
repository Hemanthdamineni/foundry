"""Judge / review evaluation models for the SDLC pipeline.

Merges from:
- Helix/foundry/sdlc/models.py  (JudgeVerdict)
- Ai-Agent-Server/latest/src/schemas.py  (ReviewDecision)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReviewDecision(StrEnum):
    """Binary decision from a code review gate.

    From Ai-Agent-Server schemas.py.
    """

    APPROVED = "APPROVED"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"


class JudgeVerdict(BaseModel):
    """Structured verdict from the JudgeEngine evaluation.

    From Helix models.py.
    """

    passed: bool
    reason: str
    issues: list[str] = Field(default_factory=list)
    severity: str = "info"  # "info", "warning", "error", "critical"


__all__ = [
    "ReviewDecision",
    "JudgeVerdict",
]
