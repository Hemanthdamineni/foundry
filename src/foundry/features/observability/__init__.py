"""Observability — admin dashboard, metric collectors, and system health.

Exposes a FastAPI dashboard app (served via ``foundry dashboard``) and
a set of collectors that poll the core/store, guardrails, event bus,
and approval gate for live system state.

Typical usage::

    from foundry.features.observability.dashboard.app import create_app
    app = create_app(store=store, budget_tracker=tracker)
    # then ``uvicorn(app)`` or ``foundry dashboard``
"""

from foundry.features.observability.collectors.event_collector import EventCollector

__all__ = [
    "EventCollector",
]
