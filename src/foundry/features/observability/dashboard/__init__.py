"""Dashboard — FastAPI admin app for Foundry observability.

Routes::

    GET  /                  Main dashboard HTML page
    GET  /api/transitions   Phase transition history (from core/store)
    GET  /api/debates       Live debate status (from event bus)
    GET  /api/approvals     Pending approvals (from approval gate)
    GET  /api/guardrails    Budget/limit status (from core/guardrails)
"""

from foundry.features.observability.dashboard.app import create_app

__all__ = [
    "create_app",
]
