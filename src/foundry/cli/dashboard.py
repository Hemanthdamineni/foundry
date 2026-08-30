"""``foundry dashboard`` — launch the Foundry observability dashboard.

Resolves the store database path from the CLI environment, creates a
``BudgetTracker`` and ``StoreBackend``, and starts the FastAPI dashboard
server.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from foundry.core.guardrails import BudgetTracker, GuardrailConfig
from foundry.core.store.ensure_initialized import StoreBackend, ensure_initialized

logger = logging.getLogger("foundry.cli.dashboard")

# Default database path (relative to the Foundry data directory).
# The user can override via the FOUNDRY_DB_PATH environment variable.
_DEFAULT_DB_DIR = Path.home() / ".foundry"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "foundry.db"


def _resolve_store() -> StoreBackend | None:
    """Resolve and initialise the store database.

    Returns ``None`` when the database file does not exist (the dashboard
    will still start but display empty/placeholder data).
    """
    db_path_str = os.environ.get("FOUNDRY_DB_PATH")
    if db_path_str:
        db_path = Path(db_path_str)
    else:
        db_path = _DEFAULT_DB_PATH

    if not db_path.exists():
        logger.warning("Database not found at %s — dashboard will show limited data", db_path)
        return None

    try:
        store = ensure_initialized(db_path)
        logger.info("Connected to store at %s", db_path)
        return store
    except Exception:
        logger.exception("Failed to initialise store at %s", db_path)
        return None


def _resolve_budget_tracker(store: StoreBackend | None) -> BudgetTracker | None:
    """Build a ``BudgetTracker`` from the store if available."""
    cfg = GuardrailConfig()
    try:
        return BudgetTracker(config=cfg, store=store)
    except Exception:
        logger.exception("Failed to create BudgetTracker")
        return None


def run_dashboard(
    port: int = 3000,
    host: str = "127.0.0.1",
) -> None:
    """Start the Foundry observability dashboard server (blocking).

    Parameters
    ----------
    port:
        HTTP port to bind (default ``3000``).
    host:
        Bind address (default ``127.0.0.1``).
    """
    store = _resolve_store()
    budget_tracker = _resolve_budget_tracker(store)

    from foundry.features.observability.dashboard.app import run_dashboard as _run  # noqa: PLC0415

    _run(
        store=store,
        budget_tracker=budget_tracker,
        host=host,
        port=port,
        title="Foundry Dashboard",
    )
