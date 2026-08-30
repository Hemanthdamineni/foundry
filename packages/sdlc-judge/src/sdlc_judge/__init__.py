"""sdlc-judge: LLM-as-judge evaluation of SDLC task phase outputs.

Provides the JudgeEngine that runs a three-stage gate before allowing
phase transitions: phase match (caller), deterministic schema checks,
and LLM judge evaluation.
"""

from __future__ import annotations

from sdlc_judge.base import LLMProvider
from sdlc_judge.engine import (
    VERDICT_JSON_SCHEMA,
    JudgeEngine,
)

__all__ = [
    "LLMProvider",
    "JudgeEngine",
    "VERDICT_JSON_SCHEMA",
]
