"""Synchronous bootstrap store -- minimal, CLI-friendly.

The canonical production store is the async ``SqliteStore`` in
``foundry.core.store.sqlite``. This module provides a minimal *synchronous*
store for CLI bootstrapping and early initialization only.

Usage::

    store = ensure_initialized("/path/to/foundry.db")
    # store is a ready-to-use synchronous BootstrapStore
    ...
    store.close()

Everything here uses synchronous ``sqlite3``, not ``aiosqlite``.  There is
only one caller -- the ``foundry`` CLI.  Once the async runtime is up, every
component should use ``SqliteStore`` directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Pull the full merged DDL from the canonical async store so the schema
# never drifts between bootstrap and production.
from foundry.core.store.sqlite import _SCHEMA_SQL


class BootstrapStore:
    """Minimal synchronous SQLite store for CLI / bootstrap use only.

    This is **not** the ``StoreBackend`` ABC and **not** the production
    ``SqliteStore`` -- it exists solely so CLI commands can open the same
    database without depending on ``aiosqlite`` or an event loop.

    Schema is identical to the canonical store (16 tables).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    #  Properties
    # ------------------------------------------------------------------ #

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(
                "BootstrapStore not initialized -- call ensure_initialized() first"
            )
        return self._conn

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """Open connection, enable WAL, create all tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()
        self._conn.commit()

    def _create_tables(self) -> None:
        """Create all tables using the canonical schema DDL."""
        self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ------------------------------------------------------------------ #
#  Module-level helpers
# ------------------------------------------------------------------ #


def db_exists(db_path: str | Path) -> bool:
    """Return True if a SQLite database already exists at *db_path*."""
    p = Path(db_path)
    if not p.exists():
        return False
    if p.stat().st_size == 0:
        return False
    return True


def ensure_initialized(db_path: str | Path) -> BootstrapStore:
    """Return a fully-initialized ``BootstrapStore``, creating the DB if needed.

    This is the **only** code path that creates the database before the
    async runtime is available.  Callers should hold on to the returned
    instance and call ``.close()`` when done.
    """
    store = BootstrapStore(db_path)
    store.initialize()
    return store


# Backward-compat alias — old code imports StoreBackend from this module
StoreBackend = BootstrapStore
