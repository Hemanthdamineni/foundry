"""Guardrails -- budget and step-limit enforcement for LLM dispatch.

Exposes:
    - GuardrailConfig -- configurable max_tokens, max_steps, max_cost
    - BudgetTracker   -- pre-dispatch check + post-dispatch recording with
                         persistence via the core/store SQLite backend
"""

from foundry.core.guardrails.budget import BudgetTracker
from foundry.core.guardrails.config import GuardrailConfig

__all__ = [
    "BudgetTracker",
    "GuardrailConfig",
]
