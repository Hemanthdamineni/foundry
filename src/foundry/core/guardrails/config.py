"""Guardrail configuration model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GuardrailConfig(BaseModel):
    """Configuration limits for budget and step enforcement.

    Attributes
    ----------
    max_tokens:
        Maximum total tokens allowed across all dispatches in a budget
        period.  ``0`` (default) means unlimited.
    max_steps:
        Maximum number of LLM dispatch calls allowed in a budget period.
        ``0`` (default) means unlimited.
    max_cost:
        Maximum total monetary cost (in arbitrary units) allowed in a
        budget period.  ``0.0`` (default) means unlimited.
    """

    max_tokens: int = Field(default=0, ge=0)
    max_steps: int = Field(default=0, ge=0)
    max_cost: float = Field(default=0.0, ge=0.0)
