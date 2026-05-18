"""SQLite StoreBackend implementation with WAL mode, busy_timeout, BEGIN IMMEDIATE."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sdlc.runtime.store_backend import StoreBackend


class SqliteStore(StoreBackend):
    """SQLite StoreBackend — WAL mode, busy_timeout=5000, BEGIN IMMEDIATE for writes."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._write_counter = 0
        self._checkpoint_interval = 100

    async def initialize(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS phase_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                phase TEXT NOT NULL,
                output TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                task_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            msg = "Store not initialized"
            raise RuntimeError(msg)
        return self._conn

    async def _execute_write(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        conn = self._connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        self._write_counter += 1
        if self._write_counter >= self._checkpoint_interval:
            await self.checkpoint()
            self._write_counter = 0
        return cur

    async def _execute_read(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        cur = self._connection().execute(sql, params)
        return list(cur.fetchall())

    async def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        await self._execute_write(
            "INSERT INTO tasks (task_id, data) VALUES (?, ?)",
            (task["task_id"], json.dumps(task, default=str)),
        )
        return task

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            "SELECT data FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        if not rows:
            return None
        return cast("dict[str, Any]", json.loads(rows[0]["data"]))

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = await self.get_task(task_id)
        if existing is None:
            msg = f"Task not found: {task_id}"
            raise ValueError(msg)
        existing.update(updates)
        existing["updated_at"] = datetime.now(UTC).isoformat()
        await self._execute_write(
            "UPDATE tasks SET data = ?, updated_at = datetime('now') WHERE task_id = ?",
            (json.dumps(existing, default=str), task_id),
        )
        return existing

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = await self._execute_read("SELECT data FROM tasks ORDER BY created_at DESC")
        tasks = [cast("dict[str, Any]", json.loads(r["data"])) for r in rows]
        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        return tasks

    async def save_phase_output(self, task_id: str, phase: str, output: dict[str, Any]) -> None:
        await self._execute_write(
            "INSERT INTO phase_history (task_id, phase, output) VALUES (?, ?, ?)",
            (task_id, phase, json.dumps(output, default=str)),
        )

    async def get_history(self, task_id: str) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            """
            SELECT phase, output, created_at
            FROM phase_history
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        )
        history: list[dict[str, Any]] = []
        for row in rows:
            payload = cast("dict[str, Any]", json.loads(row["output"]))
            payload.setdefault("phase", row["phase"])
            payload.setdefault("created_at", row["created_at"])
            history.append(payload)
        return history

    async def save_checkpoint(self, task_id: str, checkpoint: dict[str, Any]) -> None:
        await self._execute_write(
            "INSERT OR REPLACE INTO checkpoints (task_id, data) VALUES (?, ?)",
            (task_id, json.dumps(checkpoint, default=str)),
        )

    async def restore_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            "SELECT data FROM checkpoints WHERE task_id = ?",
            (task_id,),
        )
        if not rows:
            return None
        return cast("dict[str, Any]", json.loads(rows[0]["data"]))

    async def checkpoint(self) -> None:
        self._connection().execute("PRAGMA wal_checkpoint(RESTART)")

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
