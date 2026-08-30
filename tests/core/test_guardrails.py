"""Unit tests for foundry.core.guardrails.

Tests cover:
- GuardrailConfig defaults and custom values
- BudgetTracker in-memory mode (no store / no db_path)
- check_before_dispatch with all three limit types
- record_dispatch and accumulator updates
- reset behaviour
- Persistence via a SQLite-backed connection
- The budget_exhausted convenience property
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from foundry.core.guardrails.budget import BudgetTracker
from foundry.core.guardrails.config import GuardrailConfig


# ======================================================================
# GuardrailConfig
# ======================================================================


class TestGuardrailConfig:
    def test_defaults(self) -> None:
        cfg = GuardrailConfig()
        assert cfg.max_tokens == 0
        assert cfg.max_steps == 0
        assert cfg.max_cost == 0.0

    def test_custom_values(self) -> None:
        cfg = GuardrailConfig(max_tokens=50_000, max_steps=10, max_cost=5.0)
        assert cfg.max_tokens == 50_000
        assert cfg.max_steps == 10
        assert cfg.max_cost == 5.0

    def test_zero_means_unlimited(self) -> None:
        """Zero in any field means that dimension is not enforced."""
        cfg = GuardrailConfig(max_tokens=0, max_steps=0, max_cost=0.0)
        # All checks should pass regardless of actual usage
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(10_000_000)  # huge token count
        assert tracker.check_before_dispatch() is True

    def test_non_negative_validation(self) -> None:
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            GuardrailConfig(max_tokens=-1)
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            GuardrailConfig(max_steps=-5)
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            GuardrailConfig(max_cost=-0.01)


# ======================================================================
# BudgetTracker -- in-memory (no store, no db_path)
# ======================================================================


class TestBudgetTrackerInMemory:
    """Tests that exercise the pure in-memory code path."""

    def test_construction_defaults(self) -> None:
        tracker = BudgetTracker()
        assert tracker.tokens_used == 0
        assert tracker.steps_used == 0
        assert tracker.cost_incurred == 0.0
        assert tracker.config.max_tokens == 0
        assert tracker.budget_exhausted is False

    def test_check_before_dispatch_passes_within_limits(self) -> None:
        cfg = GuardrailConfig(max_tokens=1000, max_steps=5, max_cost=10.0)
        tracker = BudgetTracker(config=cfg)
        assert tracker.check_before_dispatch(cost_estimate=500) is True

    def test_check_before_dispatch_fails_when_tokens_exceeded(self) -> None:
        cfg = GuardrailConfig(max_tokens=1000, max_steps=100, max_cost=100.0)
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(800)
        # Remaining: 200 tokens; estimate 300 -> exceeds
        assert tracker.check_before_dispatch(cost_estimate=300) is False

    def test_check_before_dispatch_fails_when_steps_exceeded(self) -> None:
        cfg = GuardrailConfig(max_tokens=0, max_steps=3, max_cost=0.0)
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(10)
        tracker.record_dispatch(10)
        tracker.record_dispatch(10)
        assert tracker.check_before_dispatch() is False

    def test_check_before_dispatch_fails_when_cost_exceeded(self) -> None:
        cfg = GuardrailConfig(max_tokens=0, max_steps=0, max_cost=5.0)
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(100, monetary_cost=5.0)
        assert tracker.check_before_dispatch() is False

    def test_check_before_dispatch_exact_hit_not_exceeded(self) -> None:
        """Hitting a limit exactly should still allow the dispatch that *causes* it."""
        cfg = GuardrailConfig(max_tokens=100, max_steps=1, max_cost=0.0)
        tracker = BudgetTracker(config=cfg)
        # 100 tokens used, but this dispatch brought us to 100 — the
        # check BEFORE that dispatch (with estimate 100) should still pass.
        assert tracker.check_before_dispatch(cost_estimate=100) is True
        tracker.record_dispatch(100)
        # Now we are *at* the limit; the NEXT dispatch should be refused.
        assert tracker.check_before_dispatch(cost_estimate=1) is False

    def test_record_dispatch_increments_all_counters(self) -> None:
        tracker = BudgetTracker()
        tracker.record_dispatch(actual_cost=250, monetary_cost=0.02)
        assert tracker.tokens_used == 250
        assert tracker.steps_used == 1
        assert tracker.cost_incurred == 0.02

    def test_record_dispatch_defaults(self) -> None:
        tracker = BudgetTracker()
        tracker.record_dispatch()
        assert tracker.tokens_used == 0
        assert tracker.steps_used == 1
        assert tracker.cost_incurred == 0.0

    def test_reset_clears_counters(self) -> None:
        cfg = GuardrailConfig(max_tokens=10_000, max_steps=10, max_cost=10.0)
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(500, monetary_cost=0.5)
        tracker.record_dispatch(300, monetary_cost=0.3)
        assert tracker.steps_used == 2
        tracker.reset()
        assert tracker.tokens_used == 0
        assert tracker.steps_used == 0
        assert tracker.cost_incurred == 0.0
        assert tracker.check_before_dispatch(500) is True

    def test_budget_exhausted_property(self) -> None:
        cfg = GuardrailConfig(max_tokens=50, max_steps=0, max_cost=0.0)
        tracker = BudgetTracker(config=cfg)
        assert tracker.budget_exhausted is False
        tracker.record_dispatch(50)
        # At exactly the limit, an estimate-0 dispatch is still allowed
        assert tracker.budget_exhausted is False
        # But exceeding the limit makes it exhausted
        tracker.record_dispatch(1)
        assert tracker.budget_exhausted is True

    def test_period_start_is_set(self) -> None:
        tracker = BudgetTracker()
        assert tracker.period_start > 0
        # Should be close to current time
        assert abs(tracker.period_start - time.time()) < 5.0

    def test_reset_updates_period_start(self) -> None:
        tracker = BudgetTracker()
        old_start = tracker.period_start
        time.sleep(0.01)
        tracker.reset()
        assert tracker.period_start > old_start


# ======================================================================
# BudgetTracker -- SQLite-backed persistence
# ======================================================================


class TestBudgetTrackerPersistence:
    """Tests that the tracker correctly persists and recovers state via SQLite."""

    def test_persistence_between_instances(self, tmp_path: Path) -> None:
        db = tmp_path / "test_budget.db"
        # First instance -- write some state
        cfg = GuardrailConfig(max_tokens=5000, max_steps=10, max_cost=5.0)
        t1 = BudgetTracker(config=cfg, db_path=db)
        t1.record_dispatch(1000, monetary_cost=0.5)
        t1.record_dispatch(2000, monetary_cost=1.0)
        assert t1.tokens_used == 3000
        assert t1.steps_used == 2
        assert t1.cost_incurred == 1.5
        # Let t1 go out of scope; connection stays open but we make a new one

        # Second instance -- should reload from DB
        t2 = BudgetTracker(config=cfg, db_path=db)
        assert t2.tokens_used == 3000
        assert t2.steps_used == 2
        assert t2.cost_incurred == 1.5
        # check_before_dispatch should account for persisted state
        assert t2.check_before_dispatch(cost_estimate=1000) is True  # 3000+1000=4000 < 5000
        assert t2.check_before_dispatch(cost_estimate=2001) is False  # 3000+2001=5001 > 5000

    def test_reset_clears_persisted_state(self, tmp_path: Path) -> None:
        db = tmp_path / "reset_test.db"
        cfg = GuardrailConfig(max_tokens=5000, max_steps=5, max_cost=10.0)
        t1 = BudgetTracker(config=cfg, db_path=db)
        t1.record_dispatch(1000)
        t1.reset()

        # New instance reading from same DB should see zeroed state
        t2 = BudgetTracker(config=cfg, db_path=db)
        assert t2.tokens_used == 0
        assert t2.steps_used == 0
        assert t2.cost_incurred == 0.0

    def test_no_interference_between_trackers(self, tmp_path: Path) -> None:
        """Two trackers with different DB paths should not share state."""
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        cfg = GuardrailConfig(max_tokens=1000, max_steps=10, max_cost=10.0)
        ta = BudgetTracker(config=cfg, db_path=db_a)
        tb = BudgetTracker(config=cfg, db_path=db_b)
        ta.record_dispatch(900)
        tb.record_dispatch(200)
        assert ta.tokens_used == 900
        assert tb.tokens_used == 200
        # ta should reject another large dispatch; tb still has room
        assert ta.check_before_dispatch(cost_estimate=200) is False
        assert tb.check_before_dispatch(cost_estimate=200) is True

    def test_missing_table_is_created_automatically(self, tmp_path: Path) -> None:
        """Construction should create the budget_state table if absent."""
        db = tmp_path / "fresh.db"
        cfg = GuardrailConfig(max_tokens=1000, max_steps=5, max_cost=10.0)
        tracker = BudgetTracker(config=cfg, db_path=db)
        tracker.record_dispatch(500)
        # Verify the table exists by querying directly
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT * FROM budget_state").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 500  # tokens_used
        conn.close()

    def test_store_backend_integration(self, tmp_path: Path) -> None:
        """When passed a real StoreBackend, the tracker reuses its connection."""
        from foundry.core.store.ensure_initialized import ensure_initialized

        db = tmp_path / "store_backend.db"
        store = ensure_initialized(db)
        cfg = GuardrailConfig(max_tokens=1000, max_steps=5, max_cost=5.0)
        tracker = BudgetTracker(config=cfg, store=store)
        tracker.record_dispatch(300, monetary_cost=0.3)
        assert tracker.tokens_used == 300
        assert tracker.steps_used == 1
        assert tracker.cost_incurred == 0.3
        store.close()

    def test_check_before_dispatch_zero_cost_estimate_within_limit(self) -> None:
        """Passing cost_estimate=0 (unknown) should not cause false rejections."""
        cfg = GuardrailConfig(max_tokens=100, max_steps=0, max_cost=0.0)
        tracker = BudgetTracker(config=cfg)
        tracker.record_dispatch(50)
        assert tracker.check_before_dispatch(cost_estimate=0) is True

    def test_config_property(self) -> None:
        cfg = GuardrailConfig(max_tokens=999)
        tracker = BudgetTracker(config=cfg)
        assert tracker.config is cfg
        assert tracker.config.max_tokens == 999
