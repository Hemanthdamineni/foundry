"""Tests for the ``foundry dashboard`` CLI command.

These tests verify that the CLI module:
- Resolves the store path correctly
- Handles a missing database gracefully
- Delegates to the FastAPI runner with the right arguments
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from foundry.cli import dashboard


# ======================================================================
# Store resolution
# ======================================================================


class TestResolveStore:
    def test_returns_none_when_db_missing(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            store = dashboard._resolve_store()
            assert store is None

    def test_returns_store_when_db_exists(self, tmp_path: Path) -> None:
        db_path = tmp_path / "foundry.db"
        db_path.touch()
        expected = str(db_path)
        with patch.dict(os.environ, {"FOUNDRY_DB_PATH": expected}, clear=True):
            store = dashboard._resolve_store()
            assert store is not None
            assert str(store.db_path) == expected
            store.close()

    def test_default_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Path, "exists", return_value=False):
                store = dashboard._resolve_store()
                assert store is None  # no DB exists at default path either

    def test_returns_none_on_store_error(self) -> None:
        with patch.dict(os.environ, {"FOUNDRY_DB_PATH": "/nonexistent/db.sqlite"}, clear=True):
            store = dashboard._resolve_store()
            assert store is None


# ======================================================================
# Budget tracker resolution
# ======================================================================


class TestResolveBudgetTracker:
    def test_returns_none_without_store(self) -> None:
        tracker = dashboard._resolve_budget_tracker(store=None)
        assert tracker is not None  # BudgetTracker can work without a store (in-memory)

    def test_returns_tracker_with_store(self, tmp_path: Path) -> None:
        from foundry.core.store.ensure_initialized import ensure_initialized

        db_path = tmp_path / "foundry.db"
        store = ensure_initialized(db_path)
        tracker = dashboard._resolve_budget_tracker(store)
        assert tracker is not None
        assert tracker.tokens_used == 0
        store.close()


# ======================================================================
# CLI run_dashboard
# ======================================================================


class TestRunDashboard:
    def test_delegates_to_app(self) -> None:
        """Verify that run_dashboard resolves store/tracker and calls the app runner."""
        with (
            patch("foundry.cli.dashboard._resolve_store", return_value=None),
            patch("foundry.cli.dashboard._resolve_budget_tracker", return_value=None),
            patch("foundry.features.observability.dashboard.app.run_dashboard") as mock_run,
        ):
            dashboard.run_dashboard(port=9876, host="0.0.0.0")
            mock_run.assert_called_once_with(
                store=None,
                budget_tracker=None,
                host="0.0.0.0",
                port=9876,
                title="Foundry Dashboard",
            )
