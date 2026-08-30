"""Migration utilities for converting Ai-Agent epoch-INT timestamps to ISO 8601 TEXT."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def migrate_epoch_to_iso(db_path: str | Path) -> dict[str, int]:
    """Convert all INTEGER epoch timestamps to ISO 8601 TEXT in the store.

    Scans every table in the database, discovers columns whose name ends in
    ``_at`` (or matches known timestamp column names) and whose type is
    INTEGER, then converts their values from Unix epoch seconds to ISO 8601
    TEXT strings in UTC.

    Columns that already store TEXT are left untouched.  Columns whose data
    type does not match a known timestamp naming pattern are left untouched.

    Returns a summary dict with keys ``tables_affected`` and ``rows_converted``.
    """

    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    TIMESTAMP_SUFFIXES = ("_at", "_for")
    KNOWN_TS = {"not_before", "scheduled_for"}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tables_affected: set[str] = set()
    total_rows = 0

    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        for (table_name,) in tables:
            columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            ts_columns: list[str] = []

            for col in columns:
                col_name: str = col["name"]
                col_type: str = col["type"].upper() if col["type"] else ""

                if col_type != "INTEGER":
                    continue

                # Match by suffix or known name
                if any(col_name.endswith(suf) for suf in TIMESTAMP_SUFFIXES):
                    ts_columns.append(col_name)
                elif col_name in KNOWN_TS:
                    ts_columns.append(col_name)

            if not ts_columns:
                continue

            # Check if there are any non-NULL INTEGER values that need conversion
            sample = conn.execute(
                f"SELECT {', '.join(ts_columns)} FROM {table_name} LIMIT 1"
            ).fetchone()
            if sample is None:
                continue  # empty table

            needs_conversion = False
            for col_name in ts_columns:
                val = sample[col_name]
                if val is not None and isinstance(val, int):
                    needs_conversion = True
                    break

            if not needs_conversion:
                continue

            tables_affected.add(table_name)

            # Build a per-column UPDATE expression
            set_clauses: list[str] = []
            for col_name in ts_columns:
                set_clauses.append(
                    f"{col_name} = CASE"
                    f"  WHEN {col_name} IS NULL THEN NULL"
                    f"  WHEN typeof({col_name}) = 'text' THEN {col_name}"
                    f"  ELSE datetime({col_name}, 'unixepoch')"
                    f" END"
                )

            set_expr = ", ".join(set_clauses)
            conn.execute(f"UPDATE {table_name} SET {set_expr}")
            changes = conn.total_changes - total_rows
            total_rows = conn.total_changes

        conn.commit()

    finally:
        conn.close()

    return {
        "tables_affected": len(tables_affected),
        "rows_converted": total_rows,
        "tables": sorted(tables_affected),
    }


def validate_iso_format(db_path: str | Path) -> dict[str, list[str]]:
    """Scan all timestamp columns and report any that are still INTEGER.

    Returns a dict mapping table names to lists of column names that still
    contain INTEGER (epoch) values rather than ISO 8601 TEXT.
    """
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    TIMESTAMP_SUFFIXES = ("_at", "_for")
    KNOWN_TS = {"not_before", "scheduled_for"}

    remaining: dict[str, list[str]] = {}

    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        for (table_name,) in tables:
            columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            for col in columns:
                col_name: str = col["name"]
                col_type: str = col["type"].upper() if col["type"] else ""

                if col_type != "INTEGER":
                    continue
                if not any(col_name.endswith(suf) for suf in TIMESTAMP_SUFFIXES) and col_name not in KNOWN_TS:
                    continue

                rows = conn.execute(
                    f"SELECT {col_name} FROM {table_name} WHERE typeof({col_name}) = 'integer' AND {col_name} IS NOT NULL LIMIT 1"
                ).fetchall()
                if rows:
                    remaining.setdefault(table_name, []).append(col_name)

    finally:
        conn.close()

    return remaining
