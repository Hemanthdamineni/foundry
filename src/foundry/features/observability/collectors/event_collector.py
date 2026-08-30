"""EventCollector — polls multiple subsystems for live observability data.

Each method returns plain dicts/lists that serialise cleanly to JSON.
Errors are caught and logged rather than propagated; the dashboard never
crashes because one data source is unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiosqlite

from foundry.core.logging import get_logger

if True:  # deferred imports for optional dependencies
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from foundry.core.guardrails import BudgetTracker
        from foundry.core.store.ensure_initialized import StoreBackend

logger = get_logger("observability.collectors")


class EventCollector:
    """Aggregate state from store, guardrails, event bus, and approval gate.

    Parameters
    ----------
    store:
        Initialised ``StoreBackend`` from ``foundry.core.store``.  May be
        ``None``; the collector returns empty data for store-backed endpoints.
    budget_tracker:
        Initialised ``BudgetTracker`` from ``foundry.core.guardrails``.  May
        be ``None``; the collector returns placeholder budget data.
    """

    def __init__(
        self,
        store: StoreBackend | None = None,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self._store = store
        self._budget_tracker = budget_tracker

    # ------------------------------------------------------------------
    # Store-backed polls
    # ------------------------------------------------------------------

    def poll_transitions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent phase-transition records from the store.

        Queries the ``phase_history`` table joined with ``tasks`` for a
        human-readable task description.
        """
        if self._store is None:
            return []
        try:
            conn = self._store.conn
            rows = conn.execute(
                """
                SELECT ph.id           AS transition_id,
                       ph.task_id,
                       t.data          AS task_data,
                       ph.phase,
                       ph.output,
                       ph.created_at   AS transitioned_at
                FROM phase_history ph
                LEFT JOIN tasks t ON t.task_id = ph.task_id
                ORDER BY ph.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except aiosqlite.Error:
            logger.exception("poll_transitions: store query failed")
            return []

    def poll_checkpoints(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent checkpoints from the store."""
        if self._store is None:
            return []
        try:
            conn = self._store.conn
            rows = conn.execute(
                """
                SELECT task_id, data, created_at
                FROM checkpoints
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except aiosqlite.Error:
            logger.exception("poll_checkpoints: store query failed")
            return []

    def poll_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent tasks from the store."""
        if self._store is None:
            return []
        try:
            conn = self._store.conn
            rows = conn.execute(
                """
                SELECT task_id, data, created_at, updated_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except aiosqlite.Error:
            logger.exception("poll_tasks: store query failed")
            return []

    def poll_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent trace records from the store."""
        if self._store is None:
            return []
        try:
            conn = self._store.conn
            rows = conn.execute(
                """
                SELECT id, task_id, phase, action, status, verdict,
                       trace_data, created_at, updated_at
                FROM traces
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except aiosqlite.Error:
            logger.exception("poll_traces: store query failed")
            return []

    def poll_debate_logs(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return recent debate-log entries from the store."""
        if self._store is None:
            return []
        try:
            conn = self._store.conn
            rows = conn.execute(
                """
                SELECT id, task_id, round_num, agent_role, content,
                       verdict, created_at
                FROM debate_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except aiosqlite.Error:
            logger.exception("poll_debate_logs: store query failed")
            return []

    # ------------------------------------------------------------------
    # Event-bus poll
    # ------------------------------------------------------------------

    def poll_event_bus(self) -> list[dict[str, Any]]:
        """Read live events from the API server's event bus, if available.

        The event bus module is an optional dependency.  If it is not
        installed or cannot be imported the collector returns an empty
        list and logs a debug message.
        """
        try:
            from projects.ai_agent_server.src.event_bus import (  # type: ignore[import-untyped]  # noqa: PLC0415
                _task_scheduler,
            )
        except ImportError:
            logger.debug("poll_event_bus: event_bus module not available")
            return []

        live_events: list[dict[str, Any]] = []
        try:
            if _task_scheduler is not None:
                # The reference event_bus uses an in-memory scheduler;
                # expose whatever introspection the scheduler provides.
                scheduled = getattr(_task_scheduler, "scheduled_tasks", None)
                if scheduled is not None:
                    now = time.time()
                    for task in scheduled:
                        live_events.append(
                            {
                                "task_name": getattr(task, "name", "unknown"),
                                "next_run": str(getattr(task, "next_run", "")),
                                "trigger_count": getattr(task, "trigger_counter", 0),
                                "trigger_type": getattr(task, "trigger_type", "event"),
                            }
                        )
            return live_events
        except Exception:
            logger.exception("poll_event_bus: unexpected error")
            return []

    # ------------------------------------------------------------------
    # Approval-gate poll
    # ------------------------------------------------------------------

    def poll_approvals(self) -> list[dict[str, Any]]:
        """Read pending approval requests from the approval gate.

        The approval gate is an optional dependency.  If it is not
        installed the collector returns an empty list.
        """
        try:
            from hermes_cli.tools.approval import (  # type: ignore[import-untyped]  # noqa: PLC0415
                _pending,
                _gateway_queues,
            )
        except ImportError:
            logger.debug("poll_approvals: approval module not available")
            return []

        pending: list[dict[str, Any]] = []
        try:
            for session_key, data in _pending.items():
                pending.append(
                    {
                        "session_key": session_key,
                        "command": data.get("command", ""),
                        "description": data.get("description", ""),
                        "pattern_key": data.get("pattern_key", ""),
                        "status": "pending",
                    }
                )
            for session_key, entries in _gateway_queues.items():
                for entry in entries:
                    data = getattr(entry, "data", {})
                    pending.append(
                        {
                            "session_key": session_key,
                            "command": data.get("command", ""),
                            "description": data.get("description", ""),
                            "pattern_key": data.get("pattern_key", ""),
                            "status": "gateway_blocked",
                        }
                    )
            return pending
        except Exception:
            logger.exception("poll_approvals: unexpected error")
            return []

    # ------------------------------------------------------------------
    # Guardrails poll
    # ------------------------------------------------------------------

    def poll_guardrails(self) -> dict[str, Any]:
        """Return current budget/limit status from the guardrails module.

        Returns a dict with budget statistics or a placeholder when no
        tracker is configured.
        """
        if self._budget_tracker is None:
            return {
                "configured": False,
                "tokens_used": 0,
                "steps_used": 0,
                "cost_incurred": 0.0,
                "budget_exhausted": False,
                "limits": {},
            }
        try:
            cfg = self._budget_tracker.config
            return {
                "configured": True,
                "tokens_used": self._budget_tracker.tokens_used,
                "steps_used": self._budget_tracker.steps_used,
                "cost_incurred": self._budget_tracker.cost_incurred,
                "budget_exhausted": self._budget_tracker.budget_exhausted,
                "period_start": self._budget_tracker.period_start,
                "limits": {
                    "max_tokens": cfg.max_tokens,
                    "max_steps": cfg.max_steps,
                    "max_cost": cfg.max_cost,
                },
            }
        except Exception:
            logger.exception("poll_guardrails: unexpected error")
            return {
                "configured": True,
                "error": "failed to read budget state",
            }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert a ``sqlite3.Row`` to a plain dict."""
    return dict(row)
