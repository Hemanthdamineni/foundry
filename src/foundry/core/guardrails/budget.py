"""BudgetTracker -- cost/token budget and step-limit enforcement.

API flow::

    tracker = BudgetTracker(config=guardrail_config, store=store_backend)

    # MUST call BEFORE every LLM dispatch:
    if not tracker.check_before_dispatch(estimated_cost):
        raise GuardrailError("budget exceeded -- refusing dispatch")

    # AFTER the LLM returns, record actual usage:
    tracker.record_dispatch(actual_tokens_used, monetary_cost=...)

    # Reset for a new budget period:
    tracker.reset()
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from foundry.core.exceptions import GuardrailError
from foundry.core.guardrails.config import GuardrailConfig
from foundry.core.store.ensure_initialized import ensure_initialized

if TYPE_CHECKING:
    import sqlite3

    from foundry.core.store.ensure_initialized import StoreBackend


class BudgetTracker:
    """Enforces token, step, and cost budgets for LLM dispatch calls.

    The tracker persists running totals to the core/store SQLite database
    so totals survive process restarts within a budget period.

    .. important::

       ``check_before_dispatch()`` MUST be called **before** every LLM
       dispatch call (not after).  If it returns ``False`` the caller
       must refuse the dispatch -- the budget is exhausted.
    """

    def __init__(
        self,
        config: GuardrailConfig | None = None,
        store: StoreBackend | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        """Initialise the tracker.

        Parameters
        ----------
        config:
            Budget limits.  Uses sensible defaults when ``None``.
        store:
            An already-initialised ``StoreBackend`` from
            ``foundry.core.store``.  When provided the tracker reuses
            the shared SQLite connection and automatically creates (if
            missing) a ``budget_state`` table for persistence.
        db_path:
            Fallback path to a SQLite database file.  Ignored when
            *store* is also provided.  If neither *store* nor *db_path*
            is given the tracker operates purely in-memory.
        """
        self._config = config or GuardrailConfig()
        self._store = store
        self._conn: sqlite3.Connection | None = None

        if store is not None:
            self._conn = store.conn
        elif db_path is not None:
            _store = ensure_initialized(db_path)
            self._conn = _store.conn
            _ensure_budget_table(self._conn)

        self._init_memory_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_memory_state(self) -> None:
        """Reset in-memory counters, then overlay any persisted state."""
        self._tokens_used: int = 0
        self._steps_used: int = 0
        self._cost_incurred: float = 0.0
        self._period_start: float = time.time()
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Restore counters from the database, if available."""
        if self._conn is None:
            return
        _ensure_budget_table(self._conn)
        row = self._conn.execute(
            "SELECT tokens_used, steps_used, cost_incurred, period_start "
            "FROM budget_state WHERE id = 1"
        ).fetchone()
        if row:
            self._tokens_used = row["tokens_used"]
            self._steps_used = row["steps_used"]
            self._cost_incurred = row["cost_incurred"]
            self._period_start = row["period_start"]

    def _persist(self) -> None:
        """Write current counters to the database."""
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO budget_state "
            "(id, tokens_used, steps_used, cost_incurred, period_start) "
            "VALUES (1, ?, ?, ?, ?)",
            (self._tokens_used, self._steps_used, self._cost_incurred, self._period_start),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_before_dispatch(self, cost_estimate: int = 0) -> bool:
        """Check whether the next LLM dispatch would exceed any budget limit.

        **Must be called before the LLM call.**  If this returns ``False``
        the caller **must not** make the dispatch.

        Parameters
        ----------
        cost_estimate:
            Expected token count for the upcoming dispatch (``0`` if
            unknown).  A rough estimate helps catch overruns early.

        Returns
        -------
        ``True`` if the dispatch is within all budget limits, ``False`` if
        any limit would be exceeded.
        """
        if self._config.max_tokens > 0 and self._tokens_used + cost_estimate > self._config.max_tokens:
            return False
        if self._config.max_steps > 0 and self._steps_used >= self._config.max_steps:
            return False
        if self._config.max_cost > 0 and self._cost_incurred >= self._config.max_cost:
            return False
        return True

    def record_dispatch(self, actual_cost: int = 0, monetary_cost: float = 0.0) -> None:
        """Record a completed LLM dispatch and update running totals.

        Call this **after** the LLM call returns, passing the actual token
        count and/or monetary cost that was consumed.

        Parameters
        ----------
        actual_cost:
            Number of tokens consumed by the dispatch.
        monetary_cost:
            Monetary cost incurred (in arbitrary units, e.g. USD cents).
        """
        self._tokens_used += actual_cost
        self._steps_used += 1
        self._cost_incurred += monetary_cost
        self._persist()

    def reset(self) -> None:
        """Reset all counters to begin a new budget period.

        This clears both in-memory totals and the persisted row in the
        database, so subsequent dispatches start with a fresh budget.
        """
        self._init_memory_state()
        if self._conn is not None:
            _ensure_budget_table(self._conn)
            self._conn.execute("DELETE FROM budget_state WHERE id = 1")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def tokens_used(self) -> int:
        """Total tokens consumed in the current budget period."""
        return self._tokens_used

    @property
    def steps_used(self) -> int:
        """Total LLM dispatches performed in the current budget period."""
        return self._steps_used

    @property
    def cost_incurred(self) -> float:
        """Total monetary cost incurred in the current budget period."""
        return self._cost_incurred

    @property
    def period_start(self) -> float:
        """Unix timestamp marking the start of the current budget period."""
        return self._period_start

    @property
    def config(self) -> GuardrailConfig:
        """The active guardrail configuration."""
        return self._config

    @property
    def budget_exhausted(self) -> bool:
        """``True`` when any budget limit has been reached (alias for convenience)."""
        return not self.check_before_dispatch(0)


def _ensure_budget_table(conn: sqlite3.Connection) -> None:
    """Create the ``budget_state`` table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS budget_state (
            id INTEGER PRIMARY KEY,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            steps_used INTEGER NOT NULL DEFAULT 0,
            cost_incurred REAL NOT NULL DEFAULT 0.0,
            period_start REAL NOT NULL
        )"""
    )
