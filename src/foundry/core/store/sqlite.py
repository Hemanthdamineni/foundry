"""SQLite StoreBackend implementation — canonical merged store.

WAL mode + busy_timeout + BEGIN IMMEDIATE for writes.
ISO 8601 TEXT timestamps throughout.
Single canonical schema covering all tables from both Foundry and Ai-Agent patterns.

This is the production async store. For synchronous bootstrap/CLI access,
see ``foundry.core.store.ensure_initialized``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import aiosqlite

from foundry.core.store.backend import StoreBackend

# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #

TOOL_REQUEST_PENDING = "PENDING"
TOOL_REQUEST_CLAIMED = "CLAIMED"
TOOL_REQUEST_COMPLETED = "COMPLETED"
TOOL_REQUEST_FAILED = "FAILED"

_CHECKPOINT_INTERVAL = 100


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _utc_now() -> str:
    """Return current UTC time as ISO 8601 TEXT."""
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(raw: str | None) -> Any:
    if raw is None:
        return None
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _db_path_from_url(db_url: str) -> str:
    normalized = db_url.strip()
    if normalized.startswith("sqlite:///"):
        return normalized[len("sqlite:///") :]
    return normalized


# --------------------------------------------------------------------------- #
#  Schema DDL  —  16 tables
# --------------------------------------------------------------------------- #

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    data            TEXT,
    prompt          TEXT,
    repo_path       TEXT,
    priority        TEXT,
    mode            TEXT,
    status          TEXT,
    current_phase   TEXT,
    branch_name     TEXT,
    chat_only       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(task_id),
    phase       TEXT NOT NULL,
    output      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    task_id     TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase_runs (
    run_id          TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    phase           TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_json      TEXT NOT NULL,
    output_json     TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transitions (
    transition_id   TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    from_phase      TEXT NOT NULL,
    to_phase        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    failure_class   TEXT NOT NULL,
    confidence      REAL NOT NULL,
    validated       INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_requests (
    request_id      TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    phase           TEXT NOT NULL,
    kind            TEXT NOT NULL,
    tool_name       TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    claimed_at      TEXT,
    claimed_by      TEXT,
    claim_token     TEXT,
    resume_token    TEXT NOT NULL DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    attempt         INTEGER NOT NULL DEFAULT 1,
    not_before      TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'
);

CREATE TABLE IF NOT EXISTS tool_results (
    result_id       TEXT PRIMARY KEY,
    request_id      TEXT NOT NULL REFERENCES tool_requests(request_id) ON DELETE CASCADE,
    task_id         TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    status          TEXT NOT NULL,
    output_json     TEXT NOT NULL,
    logs            TEXT NOT NULL,
    exit_code       INTEGER,
    error_message   TEXT,
    failure_class   TEXT,
    created_at      TEXT NOT NULL,
    consumed        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bridge_workers (
    worker_id           TEXT PRIMARY KEY,
    metadata_json       TEXT NOT NULL,
    last_heartbeat_at   TEXT NOT NULL,
    status              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    budget_id           TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    phase               TEXT NOT NULL,
    model_calls         INTEGER NOT NULL DEFAULT 0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL,
    UNIQUE (task_id, phase)
);

CREATE TABLE IF NOT EXISTS model_cache_state (
    model_id        TEXT PRIMARY KEY,
    role            TEXT NOT NULL,
    warm            INTEGER NOT NULL,
    last_used_at    TEXT NOT NULL,
    loaded_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transition_stats (
    from_phase          TEXT NOT NULL,
    to_phase            TEXT NOT NULL,
    transition_count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (from_phase, to_phase)
);

CREATE TABLE IF NOT EXISTS nightly_jobs (
    job_id          TEXT PRIMARY KEY,
    scheduled_for   TEXT NOT NULL,
    status          TEXT NOT NULL,
    task_id         TEXT,
    branch_name     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    task_id         TEXT,
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id              TEXT PRIMARY KEY,
    task_id         TEXT,
    phase           TEXT,
    action          TEXT,
    status          TEXT,
    output          TEXT,
    verdict         TEXT,
    trace_data      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS engrams (
    id              TEXT PRIMARY KEY,
    content         TEXT,
    tags            TEXT,
    source          TEXT,
    importance      INTEGER DEFAULT 1,
    metadata        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS debate_logs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT,
    round_num       INTEGER,
    agent_role      TEXT,
    content         TEXT,
    verdict         TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_results_request_unique
    ON tool_results(request_id);

CREATE INDEX IF NOT EXISTS idx_traces_task_id ON traces(task_id);
"""


# =================================================================== #
#  SqliteStore
# =================================================================== #

class SqliteStore(StoreBackend):
    """SQLite-backed unified store -- WAL mode, busy_timeout, BEGIN IMMEDIATE.

    Implements both the Foundry-style ABC and the Ai-Agent-style method set
    on a single canonical schema of 16 tables.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._write_counter = 0

    # ---------------------------------------------------------------- #
    #  Lifecycle (ABC)
    # ---------------------------------------------------------------- #

    async def initialize(self) -> None:
        conn = await aiosqlite.connect(str(self._db_path), timeout=5.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(_SCHEMA_SQL)
        await self._ensure_columns(conn)
        await conn.commit()
        self._conn = conn

    async def close(self) -> None:
        async with self._lock:
            if self._conn:
                await self._conn.close()
                self._conn = None

    async def checkpoint(self) -> None:
        conn = self._connection()
        await conn.execute("PRAGMA wal_checkpoint(RESTART)")

    async def backup(self) -> str:
        conn = self._connection()
        backups_dir = self._db_path.parent / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = backups_dir / f"sdlc_{timestamp}.db"
        backup_conn = await aiosqlite.connect(str(backup_path))
        try:
            await conn.backup(backup_conn, pages=-1)
            await backup_conn.commit()
        finally:
            await backup_conn.close()
        return str(backup_path)

    # ---------------------------------------------------------------- #
    #  Internal helpers
    # ---------------------------------------------------------------- #

    def _connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Store not initialized")
        return self._conn

    async def _ensure_columns(self, conn: aiosqlite.Connection) -> None:
        """Idempotently add columns that may have been introduced later."""
        added: list[tuple[str, str, str]] = [
            ("tool_requests", "claim_token", "TEXT"),
            ("tool_requests", "resume_token", "TEXT NOT NULL DEFAULT ''"),
            ("tool_requests", "version", "INTEGER NOT NULL DEFAULT 0"),
            ("tool_requests", "lease_expires_at", "TEXT"),
            ("tool_requests", "attempt", "INTEGER NOT NULL DEFAULT 1"),
            ("tool_requests", "not_before", "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00'"),
        ]
        for table, column, spec in added:
            cursor = await conn.execute(f"PRAGMA table_info({table})")
            rows = await cursor.fetchall()
            existing = {str(row["name"]) for row in rows}
            if column not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    # ---------------------------------------------------------------- #
    #  Write / read executors
    # ---------------------------------------------------------------- #

    async def _execute_write(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> aiosqlite.Cursor:
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await conn.execute(sql, params)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        self._write_counter += 1
        if self._write_counter >= _CHECKPOINT_INTERVAL:
            await conn.execute("PRAGMA wal_checkpoint(RESTART)")
            self._write_counter = 0
        return cur

    async def _execute_read(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[aiosqlite.Row]:
        cur = await self._connection().execute(sql, params)
        return list(await cur.fetchall())

    # ---------------------------------------------------------------- #
    #  Core CRUD (Foundry-style using ``data`` JSON blob)
    # ---------------------------------------------------------------- #

    async def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        await self._execute_write(
            """INSERT INTO tasks (task_id, data, status, current_phase, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                task["task_id"],
                _json_dump(task),
                task.get("status"),
                task.get("current_phase"),
                now,
                now,
            ),
        )
        return task

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            "SELECT data FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        if not rows:
            return None
        return cast("dict[str, Any]", _json_load(rows[0]["data"]))

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = await self.get_task(task_id)
        if existing is None:
            raise ValueError(f"Task not found: {task_id}")
        existing.update(updates)
        now = _utc_now()
        status = updates.get("status", existing.get("status"))
        current_phase = updates.get("current_phase", existing.get("current_phase"))
        await self._execute_write(
            """UPDATE tasks
               SET data = ?, status = ?, current_phase = ?, updated_at = ?
               WHERE task_id = ?""",
            (_json_dump(existing), status, current_phase, now, task_id),
        )
        return existing

    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            "SELECT data FROM tasks ORDER BY created_at DESC",
        )
        tasks = [cast("dict[str, Any]", _json_load(r["data"])) for r in rows]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks

    # ---------------------------------------------------------------- #
    #  Phase history (Foundry)
    # ---------------------------------------------------------------- #

    async def save_phase_output(
        self, task_id: str, phase: str, output: dict[str, Any],
    ) -> None:
        await self._execute_write(
            "INSERT INTO phase_history (task_id, phase, output, created_at) VALUES (?, ?, ?, ?)",
            (task_id, phase, _json_dump(output), _utc_now()),
        )

    async def get_history(self, task_id: str) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            """SELECT phase, output, created_at
               FROM phase_history
               WHERE task_id = ?
               ORDER BY id ASC""",
            (task_id,),
        )
        history: list[dict[str, Any]] = []
        for row in rows:
            payload = cast("dict[str, Any]", _json_load(row["output"]))
            payload.setdefault("phase", row["phase"])
            payload.setdefault("created_at", row["created_at"])
            history.append(payload)
        return history

    # ---------------------------------------------------------------- #
    #  Checkpoints (Foundry)
    # ---------------------------------------------------------------- #

    async def save_checkpoint(self, task_id: str, checkpoint: dict[str, Any]) -> None:
        await self._execute_write(
            "INSERT OR REPLACE INTO checkpoints (task_id, data, created_at) VALUES (?, ?, ?)",
            (task_id, _json_dump(checkpoint), _utc_now()),
        )

    async def restore_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            "SELECT data FROM checkpoints WHERE task_id = ?",
            (task_id,),
        )
        if not rows:
            return None
        return cast("dict[str, Any]", _json_load(rows[0]["data"]))

    # ---------------------------------------------------------------- #
    #  Task lifecycle (Ai-Agent-style using individual columns)
    # ---------------------------------------------------------------- #

    async def create_task_v2(
        self,
        *,
        prompt: str,
        repo_path: str,
        priority: str,
        mode: str,
        status: str,
        current_phase: str,
        chat_only: bool = False,
    ) -> dict[str, Any]:
        now = _utc_now()
        task_id = _new_id("task")
        await self._execute_write(
            """INSERT INTO tasks
               (task_id, prompt, repo_path, priority, mode, status, current_phase,
                branch_name, chat_only, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (
                task_id, prompt, repo_path, priority, mode, status, current_phase,
                1 if chat_only else 0, now, now,
            ),
        )
        result = await self.get_task_v2(task_id)
        if result is None:
            raise RuntimeError("created task could not be loaded")
        return result

    async def get_task_v2(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            """SELECT task_id, prompt, repo_path, priority, mode, status, current_phase,
                      branch_name, chat_only, created_at, updated_at
               FROM tasks WHERE task_id = ?""",
            (task_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "task_id": str(r["task_id"]),
            "prompt": str(r["prompt"]),
            "repo_path": str(r["repo_path"]),
            "priority": str(r["priority"]),
            "mode": str(r["mode"]),
            "status": str(r["status"]),
            "current_phase": str(r["current_phase"]),
            "branch_name": str(r["branch_name"]) if r["branch_name"] is not None else None,
            "chat_only": bool(r["chat_only"]),
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }

    async def _update_task_columns(
        self,
        task_id: str,
        *,
        status: str | None = None,
        current_phase: str | None = None,
        branch_name: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if current_phase is not None:
            fields.append("current_phase = ?")
            values.append(current_phase)
        if branch_name is not None:
            fields.append("branch_name = ?")
            values.append(branch_name)
        if not fields:
            return
        now = _utc_now()
        fields.append("updated_at = ?")
        values.append(now)
        values.append(task_id)
        await self._execute_write(
            f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?",
            tuple(values),
        )

    async def cancel_task(self, task_id: str) -> bool:
        rows = await self._execute_read(
            """SELECT task_id FROM tasks
               WHERE task_id = ? AND status NOT IN ('DONE', 'CANCELED', 'FAILED')""",
            (task_id,),
        )
        if not rows:
            return False
        await self._update_task_columns(task_id, status="CANCELED")
        return True

    async def resume_task(self, task_id: str) -> bool:
        rows = await self._execute_read(
            """SELECT task_id FROM tasks
               WHERE task_id = ? AND status IN ('CANCELED', 'FAILED')""",
            (task_id,),
        )
        if not rows:
            return False
        await self._update_task_columns(task_id, status="QUEUED")
        return True

    async def list_runnable_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.list_runnable_tasks_with_options(limit=limit, include_running=False)

    async def list_runnable_tasks_with_options(
        self,
        *,
        limit: int = 20,
        include_running: bool = False,
    ) -> list[dict[str, Any]]:
        statuses = ["QUEUED"]
        if include_running:
            statuses.append("RUNNING")
        placeholders = ",".join("?" for _ in statuses)
        rows = await self._execute_read(
            f"""SELECT task_id FROM tasks
                WHERE status IN ({placeholders})
                ORDER BY updated_at ASC
                LIMIT ?""",
            (*statuses, limit),
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            task = await self.get_task_v2(str(row["task_id"]))
            if task is not None:
                results.append(task)
        return results

    async def try_mark_task_running(
        self,
        *,
        task_id: str,
        expected_phase: str,
        expected_updated_at: str,
    ) -> bool:
        now = _utc_now()
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = await conn.execute(
                    """UPDATE tasks
                       SET status = 'RUNNING', updated_at = ?
                       WHERE task_id = ? AND current_phase = ? AND updated_at = ? AND status = 'QUEUED'""",
                    (now, task_id, expected_phase, expected_updated_at),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return cursor.rowcount > 0

    async def recover_incomplete_tasks(self) -> int:
        now = _utc_now()
        cursor = await self._execute_write(
            "UPDATE tasks SET status = 'QUEUED', updated_at = ? WHERE status = 'RUNNING'",
            (now,),
        )
        return cursor.rowcount

    async def abandon_inflight_work(self) -> dict[str, int]:
        now = _utc_now()
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                task_cursor = await conn.execute(
                    """UPDATE tasks
                       SET status = 'CANCELED', updated_at = ?
                       WHERE status IN ('QUEUED', 'RUNNING', 'WAITING_TOOL')""",
                    (now,),
                )
                tool_cursor = await conn.execute(
                    """UPDATE tool_requests
                       SET status = 'FAILED', updated_at = ?,
                           claim_token = NULL, lease_expires_at = NULL
                       WHERE status IN ('PENDING', 'CLAIMED')""",
                    (now,),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return {
            "tasks": task_cursor.rowcount,
            "tool_requests": tool_cursor.rowcount,
        }

    # ---------------------------------------------------------------- #
    #  Phase runs & transitions (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def record_phase_run(
        self,
        *,
        task_id: str,
        phase: str,
        model: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        retry_count: int,
        status: str,
    ) -> str:
        now = _utc_now()
        run_id = _new_id("run")
        await self._execute_write(
            """INSERT INTO phase_runs
               (run_id, task_id, phase, model, input_json, output_json,
                started_at, finished_at, retry_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, task_id, phase, model,
             _json_dump(input_payload), _json_dump(output_payload),
             now, now, retry_count, status),
        )
        return run_id

    async def list_completed_phases(self, task_id: str) -> set[str]:
        rows = await self._execute_read(
            """SELECT DISTINCT to_phase FROM transitions
               WHERE task_id = ? AND validated = 1""",
            (task_id,),
        )
        return {str(r["to_phase"]) for r in rows}

    async def record_transition(
        self,
        *,
        task_id: str,
        from_phase: str,
        to_phase: str,
        reason: str,
        failure_class: str,
        confidence: float,
        validated: bool,
    ) -> str:
        now = _utc_now()
        transition_id = _new_id("trn")
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                await conn.execute(
                    """INSERT INTO transitions
                       (transition_id, task_id, from_phase, to_phase, reason,
                        failure_class, confidence, validated, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (transition_id, task_id, from_phase, to_phase, reason,
                     failure_class, confidence, 1 if validated else 0, now),
                )
                await conn.execute(
                    """INSERT INTO transition_stats (from_phase, to_phase, transition_count)
                       VALUES (?, ?, 1)
                       ON CONFLICT(from_phase, to_phase)
                       DO UPDATE SET transition_count = transition_count + 1""",
                    (from_phase, to_phase),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return transition_id

    async def on_transition(
        self,
        *,
        task_id: str,
        from_phase: str,
        to_phase: str,
        reason: str = "",
        failure_class: str = "",
        confidence: float = 0.0,
        validated: bool = False,
    ) -> str:
        """Record a phase transition. Alias for record_transition."""
        return await self.record_transition(
            task_id=task_id,
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            failure_class=failure_class,
            confidence=confidence,
            validated=validated,
        )

    async def apply_phase_step_transaction(
        self,
        *,
        task_id: str,
        from_phase: str,
        to_phase: str,
        model: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        phase_run_status: str,
        reason: str,
        failure_class: str,
        confidence: float,
        validated: bool,
        next_status: str,
        branch_name: str | None,
        model_calls: int = 1,
    ) -> tuple[str, str]:
        now = _utc_now()
        run_id = _new_id("run")
        transition_id = _new_id("trn")
        budget_id = _new_id("bdg")
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = await conn.execute(
                    "SELECT current_phase, status FROM tasks WHERE task_id = ?",
                    (task_id,),
                )
                task_row = await cursor.fetchone()
                if task_row is None:
                    raise KeyError(f"task not found: {task_id}")
                current_phase = str(task_row["current_phase"])
                current_status = str(task_row["status"])
                if current_phase != from_phase:
                    raise ValueError(
                        f"stale phase commit: expected {from_phase}, found {current_phase}"
                    )
                if current_status not in ("RUNNING", "QUEUED"):
                    raise ValueError(
                        f"task {task_id} not commit-eligible in status {current_status}"
                    )

                await conn.execute(
                    """INSERT INTO phase_runs
                       (run_id, task_id, phase, model, input_json, output_json,
                        started_at, finished_at, retry_count, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_id, task_id, from_phase, model,
                     _json_dump(input_payload), _json_dump(output_payload),
                     now, now, 0, phase_run_status),
                )
                await conn.execute(
                    """INSERT INTO transitions
                       (transition_id, task_id, from_phase, to_phase, reason,
                        failure_class, confidence, validated, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (transition_id, task_id, from_phase, to_phase, reason,
                     failure_class, confidence, 1 if validated else 0, now),
                )
                await conn.execute(
                    """INSERT INTO transition_stats (from_phase, to_phase, transition_count)
                       VALUES (?, ?, 1)
                       ON CONFLICT(from_phase, to_phase)
                       DO UPDATE SET transition_count = transition_count + 1""",
                    (from_phase, to_phase),
                )
                await conn.execute(
                    """INSERT INTO budgets
                       (budget_id, task_id, phase, model_calls, prompt_tokens, completion_tokens, updated_at)
                       VALUES (?, ?, ?, ?, 0, 0, ?)
                       ON CONFLICT(task_id, phase)
                       DO UPDATE SET
                           model_calls = model_calls + excluded.model_calls,
                           updated_at = excluded.updated_at""",
                    (budget_id, task_id, from_phase, model_calls, now),
                )

                if branch_name is None:
                    update_cursor = await conn.execute(
                        """UPDATE tasks
                           SET status = ?, current_phase = ?, updated_at = ?
                           WHERE task_id = ? AND current_phase = ?""",
                        (next_status, to_phase, now, task_id, from_phase),
                    )
                else:
                    update_cursor = await conn.execute(
                        """UPDATE tasks
                           SET status = ?, current_phase = ?, branch_name = ?, updated_at = ?
                           WHERE task_id = ? AND current_phase = ?""",
                        (next_status, to_phase, branch_name, now, task_id, from_phase),
                    )
                if update_cursor.rowcount != 1:
                    raise ValueError(f"phase commit conflict for task {task_id}")
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return (run_id, transition_id)

    async def last_transition(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            """SELECT from_phase, to_phase, reason, failure_class, confidence, validated, created_at
               FROM transitions
               WHERE task_id = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (task_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "from_phase": str(r["from_phase"]),
            "to_phase": str(r["to_phase"]),
            "reason": str(r["reason"]),
            "failure_class": str(r["failure_class"]),
            "confidence": float(r["confidence"]),
            "validated": bool(r["validated"]),
            "created_at": str(r["created_at"]),
        }

    # ---------------------------------------------------------------- #
    #  Tool requests / results (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def enqueue_tool_request(
        self,
        *,
        task_id: str,
        phase: str,
        kind: str,
        tool_name: str,
        payload: dict[str, Any],
        attempt: int = 1,
        not_before: int | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        request_id = _new_id("treq")
        resume_token = _new_id("resume")
        scheduled_for = (
            now
            if not_before is None
            else datetime.fromtimestamp(not_before, tz=UTC).isoformat()
        )
        await self._execute_write(
            """INSERT INTO tool_requests
               (request_id, task_id, phase, kind, tool_name, payload_json, status,
                created_at, updated_at, claimed_at, claimed_by, claim_token,
                resume_token, version, lease_expires_at, attempt, not_before)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0, NULL, ?, ?)""",
            (
                request_id, task_id, phase, kind, tool_name, _json_dump(payload),
                TOOL_REQUEST_PENDING, now, now, resume_token,
                max(1, attempt), scheduled_for,
            ),
        )
        record = await self.get_tool_request(request_id)
        if record is None:
            raise RuntimeError("tool request could not be loaded")
        return record

    async def get_tool_request(self, request_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            """SELECT request_id, task_id, phase, kind, tool_name, payload_json, status,
                      created_at, claimed_at, claimed_by, claim_token, resume_token,
                      version, lease_expires_at, attempt, not_before
               FROM tool_requests
               WHERE request_id = ?""",
            (request_id,),
        )
        if not rows:
            return None
        r = rows[0]
        payload = _json_load(str(r["payload_json"]))
        if not isinstance(payload, dict):
            payload = {}
        return {
            "request_id": str(r["request_id"]),
            "task_id": str(r["task_id"]),
            "phase": str(r["phase"]),
            "kind": str(r["kind"]),
            "tool_name": str(r["tool_name"]),
            "payload": payload,
            "status": str(r["status"]),
            "created_at": str(r["created_at"]),
            "claimed_at": str(r["claimed_at"]) if r["claimed_at"] is not None else None,
            "claimed_by": str(r["claimed_by"]) if r["claimed_by"] is not None else None,
            "claim_token": str(r["claim_token"]) if r["claim_token"] is not None else None,
            "resume_token": str(r["resume_token"] or request_id),
            "version": int(r["version"]),
            "lease_expires_at": str(r["lease_expires_at"]) if r["lease_expires_at"] is not None else None,
            "attempt": int(r["attempt"]) if r["attempt"] is not None else 1,
            "not_before": str(r["not_before"]),
        }

    async def has_inflight_tool_request(
        self,
        *,
        task_id: str,
        phase: str | None = None,
        kind: str | None = None,
        tool_name: str | None = None,
    ) -> bool:
        clauses = [
            "task_id = ?",
            "status IN (?, ?)",
        ]
        values: list[Any] = [task_id, TOOL_REQUEST_PENDING, TOOL_REQUEST_CLAIMED]
        if phase is not None:
            clauses.append("phase = ?")
            values.append(phase)
        if kind is not None:
            clauses.append("kind = ?")
            values.append(kind)
        if tool_name is not None:
            clauses.append("tool_name = ?")
            values.append(tool_name)
        rows = await self._execute_read(
            f"SELECT 1 FROM tool_requests WHERE {' AND '.join(clauses)} LIMIT 1",
            tuple(values),
        )
        return len(rows) > 0

    async def claim_tool_requests(
        self,
        *,
        worker_id: str,
        max_items: int,
        lease_seconds: int,
        heartbeat_timeout_seconds: int,
        requeue_stale: bool = True,
    ) -> list[dict[str, Any]]:
        now = _utc_now()
        lease_expires_at = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + max(5, lease_seconds), tz=UTC
        ).isoformat()
        records: list[dict[str, Any]] = []

        if requeue_stale:
            requeued = await self.requeue_stale_claims(
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            )
            if requeued:
                await self.add_event(
                    event_type="tool_request.requeued",
                    payload={"count": requeued, "worker_id": worker_id},
                )

        conn = self._connection()
        async with self._lock:
            cursor = await conn.execute(
                """SELECT tr.request_id, tr.version
                   FROM tool_requests AS tr
                   JOIN tasks AS t ON t.task_id = tr.task_id
                   WHERE tr.status = ? AND t.status IN ('QUEUED', 'RUNNING', 'WAITING_TOOL')
                     AND tr.not_before <= ?
                   ORDER BY tr.created_at ASC
                   LIMIT ?""",
                (TOOL_REQUEST_PENDING, now, max_items),
            )
            rows = await cursor.fetchall()

            for row in rows:
                request_id = str(row["request_id"])
                version = int(row["version"])
                claim_token = _new_id("claim")
                await conn.execute(
                    """UPDATE tool_requests
                       SET status = ?, claimed_at = ?, claimed_by = ?, claim_token = ?,
                           lease_expires_at = ?, updated_at = ?, version = version + 1
                       WHERE request_id = ? AND status = ? AND version = ?""",
                    (TOOL_REQUEST_CLAIMED, now, worker_id, claim_token,
                     lease_expires_at, now, request_id, TOOL_REQUEST_PENDING, version),
                )
                record = await self._get_tool_request_on_conn(conn, request_id)
                if record is not None and record["status"] == TOOL_REQUEST_CLAIMED:
                    records.append(record)
            await conn.commit()
        return records

    async def _get_tool_request_on_conn(
        self,
        conn: aiosqlite.Connection,
        request_id: str,
    ) -> dict[str, Any] | None:
        """Helper for claim_tool_requests to reuse the same connection."""
        cursor = await conn.execute(
            """SELECT request_id, task_id, phase, kind, tool_name, payload_json, status,
                      created_at, claimed_at, claimed_by, claim_token, resume_token,
                      version, lease_expires_at, attempt, not_before
               FROM tool_requests
               WHERE request_id = ?""",
            (request_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        payload = _json_load(str(row["payload_json"]))
        if not isinstance(payload, dict):
            payload = {}
        return {
            "request_id": str(row["request_id"]),
            "task_id": str(row["task_id"]),
            "phase": str(row["phase"]),
            "kind": str(row["kind"]),
            "tool_name": str(row["tool_name"]),
            "payload": payload,
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "claimed_at": str(row["claimed_at"]) if row["claimed_at"] is not None else None,
            "claimed_by": str(row["claimed_by"]) if row["claimed_by"] is not None else None,
            "claim_token": str(row["claim_token"]) if row["claim_token"] is not None else None,
            "resume_token": str(row["resume_token"] or request_id),
            "version": int(row["version"]),
            "lease_expires_at": str(row["lease_expires_at"]) if row["lease_expires_at"] is not None else None,
            "attempt": int(row["attempt"]) if row["attempt"] is not None else 1,
            "not_before": str(row["not_before"]),
        }

    async def store_tool_result(
        self,
        *,
        request_id: str,
        status: str,
        claim_token: str,
        resume_token: str,
        version: int,
        output_payload: dict[str, Any],
        logs: str,
        exit_code: int | None,
        error_message: str | None,
        failure_class: str | None,
    ) -> tuple[str, bool]:
        now = _utc_now()
        terminal_status = TOOL_REQUEST_COMPLETED if status == "ok" else TOOL_REQUEST_FAILED
        conn = self._connection()
        async with self._lock:
            cursor = await conn.execute(
                """SELECT task_id, status, claim_token, resume_token, version, lease_expires_at
                   FROM tool_requests WHERE request_id = ?""",
                (request_id,),
            )
            request_row = await cursor.fetchone()
            if request_row is None:
                raise KeyError(request_id)

            existing_cursor = await conn.execute(
                "SELECT result_id FROM tool_results WHERE request_id = ? LIMIT 1",
                (request_id,),
            )
            existing = await existing_cursor.fetchone()

            request_status = str(request_row["status"])
            request_task_id = str(request_row["task_id"])
            request_claim_token = str(request_row["claim_token"] or "")
            request_resume_token = str(request_row["resume_token"] or request_id)
            request_version = int(request_row["version"])
            lease_expires_at = (
                str(request_row["lease_expires_at"])
                if request_row["lease_expires_at"] is not None
                else None
            )

            if request_status in (TOOL_REQUEST_COMPLETED, TOOL_REQUEST_FAILED):
                if existing is None:
                    raise RuntimeError(f"request {request_id} is terminal but has no result row")
                return (str(existing["result_id"]), True)

            if request_status != TOOL_REQUEST_CLAIMED:
                raise ValueError(
                    f"request {request_id} is not claimable in state {request_status}"
                )
            if request_claim_token != claim_token:
                raise ValueError("claim token mismatch")
            if request_resume_token != resume_token:
                raise ValueError("resume token mismatch")
            if request_version != version:
                raise ValueError("version mismatch")
            if lease_expires_at is not None and lease_expires_at < now:
                raise ValueError("claim lease expired")

            result_id = _new_id("tres")
            try:
                await conn.execute(
                    """INSERT INTO tool_results
                       (result_id, request_id, task_id, status, output_json, logs,
                        exit_code, error_message, failure_class, created_at, consumed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (result_id, request_id, request_task_id, status,
                     _json_dump(output_payload), logs, exit_code,
                     error_message, failure_class, now),
                )
            except aiosqlite.IntegrityError:
                existing_cursor = await conn.execute(
                    "SELECT result_id FROM tool_results WHERE request_id = ? LIMIT 1",
                    (request_id,),
                )
                existing = await existing_cursor.fetchone()
                if existing is None:
                    raise
                await conn.commit()
                return (str(existing["result_id"]), True)

            await conn.execute(
                """UPDATE tool_requests
                   SET status = ?, updated_at = ?, claim_token = NULL,
                       lease_expires_at = NULL, version = version + 1
                   WHERE request_id = ? AND status = ? AND claim_token = ? AND version = ?""",
                (terminal_status, now, request_id, TOOL_REQUEST_CLAIMED, claim_token, version),
            )
            await conn.execute(
                """UPDATE tasks
                   SET status = 'QUEUED', updated_at = ?
                   WHERE task_id = ? AND status IN ('RUNNING', 'WAITING_TOOL', 'QUEUED')""",
                (now, request_task_id),
            )
            await conn.commit()
        return (result_id, False)

    async def next_unconsumed_tool_result(self, task_id: str) -> dict[str, Any] | None:
        rows = await self._execute_read(
            """SELECT result_id, request_id, status, output_json, logs,
                      exit_code, error_message, failure_class, created_at
               FROM tool_results
               WHERE task_id = ? AND consumed = 0
               ORDER BY created_at ASC
               LIMIT 1""",
            (task_id,),
        )
        if not rows:
            return None
        r = rows[0]
        output = _json_load(str(r["output_json"]))
        if not isinstance(output, dict):
            output = {}
        return {
            "result_id": str(r["result_id"]),
            "request_id": str(r["request_id"]),
            "status": str(r["status"]),
            "output": output,
            "logs": str(r["logs"]),
            "exit_code": int(r["exit_code"]) if r["exit_code"] is not None else None,
            "error_message": str(r["error_message"]) if r["error_message"] is not None else None,
            "failure_class": str(r["failure_class"]) if r["failure_class"] is not None else None,
            "created_at": str(r["created_at"]),
        }

    async def mark_tool_result_consumed(self, result_id: str) -> None:
        await self._execute_write(
            "UPDATE tool_results SET consumed = 1 WHERE result_id = ?",
            (result_id,),
        )

    # ---------------------------------------------------------------- #
    #  Budgets (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def update_budget(
        self,
        *,
        task_id: str,
        phase: str,
        model_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        now = _utc_now()
        budget_id = _new_id("bdg")
        conn = self._connection()
        async with self._lock:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                await conn.execute(
                    """INSERT INTO budgets
                       (budget_id, task_id, phase, model_calls, prompt_tokens, completion_tokens, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(task_id, phase)
                       DO UPDATE SET
                           model_calls = model_calls + excluded.model_calls,
                           prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                           completion_tokens = completion_tokens + excluded.completion_tokens,
                           updated_at = excluded.updated_at""",
                    (budget_id, task_id, phase, model_calls, prompt_tokens, completion_tokens, now),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def create_budget(
        self,
        *,
        task_id: str,
        phase: str,
        model_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Create or update a budget record. Alias for update_budget."""
        return await self.update_budget(
            task_id=task_id,
            phase=phase,
            model_calls=model_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def get_budgets(self, task_id: str) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            """SELECT phase, model_calls, prompt_tokens, completion_tokens, updated_at
               FROM budgets
               WHERE task_id = ?
               ORDER BY phase ASC""",
            (task_id,),
        )
        return [
            {
                "phase": str(r["phase"]),
                "model_calls": int(r["model_calls"]),
                "prompt_tokens": int(r["prompt_tokens"]),
                "completion_tokens": int(r["completion_tokens"]),
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        ]

    # ---------------------------------------------------------------- #
    #  Model cache (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def set_model_warm_state(
        self, *, model_id: str, role: str, warm: bool,
    ) -> None:
        now = _utc_now()
        await self._execute_write(
            """INSERT INTO model_cache_state (model_id, role, warm, last_used_at, loaded_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(model_id)
               DO UPDATE SET role = excluded.role, warm = excluded.warm,
                             last_used_at = excluded.last_used_at""",
            (model_id, role, 1 if warm else 0, now, now),
        )

    async def warm_models(self) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            """SELECT model_id, role, warm, last_used_at, loaded_at
               FROM model_cache_state
               WHERE warm = 1
               ORDER BY last_used_at DESC""",
        )
        return [
            {
                "model_id": str(r["model_id"]),
                "role": str(r["role"]),
                "warm": bool(r["warm"]),
                "last_used_at": str(r["last_used_at"]),
                "loaded_at": str(r["loaded_at"]),
            }
            for r in rows
        ]

    # ---------------------------------------------------------------- #
    #  Nightly jobs (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def set_nightly_job(
        self,
        *,
        scheduled_for: str,
        status: str,
        task_id: str | None,
        branch_name: str,
    ) -> str:
        now = _utc_now()
        job_id = _new_id("njob")
        await self._execute_write(
            """INSERT INTO nightly_jobs
               (job_id, scheduled_for, status, task_id, branch_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, scheduled_for, status, task_id, branch_name, now, now),
        )
        return job_id

    async def get_last_nightly_job_for_date(
        self, scheduled_for: str,
    ) -> dict[str, Any] | None:
        rows = await self._execute_read(
            """SELECT job_id, status, task_id, branch_name, created_at, updated_at
               FROM nightly_jobs
               WHERE scheduled_for = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (scheduled_for,),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "job_id": str(r["job_id"]),
            "status": str(r["status"]),
            "task_id": str(r["task_id"]) if r["task_id"] is not None else None,
            "branch_name": str(r["branch_name"]),
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }

    # ---------------------------------------------------------------- #
    #  Audit events (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def add_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
    ) -> str:
        now = _utc_now()
        event_id = _new_id("evt")
        await self._execute_write(
            """INSERT INTO audit_events (event_id, task_id, event_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (event_id, task_id, event_type, _json_dump(payload), now),
        )
        return event_id

    async def task_events(self, task_id: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = await self._execute_read(
            """SELECT event_id, event_type, payload_json, created_at
               FROM audit_events
               WHERE task_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (task_id, limit),
        )
        events: list[dict[str, Any]] = []
        for r in rows:
            p = _json_load(str(r["payload_json"]))
            if not isinstance(p, dict):
                p = {}
            events.append({
                "event_id": str(r["event_id"]),
                "event_type": str(r["event_type"]),
                "payload": p,
                "created_at": str(r["created_at"]),
            })
        return events

    # ---------------------------------------------------------------- #
    #  Bridge workers (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def update_worker_heartbeat(
        self, *, worker_id: str, metadata: dict[str, Any],
    ) -> None:
        now = _utc_now()
        await self._execute_write(
            """INSERT INTO bridge_workers (worker_id, metadata_json, last_heartbeat_at, status)
               VALUES (?, ?, ?, 'online')
               ON CONFLICT(worker_id)
               DO UPDATE SET
                   metadata_json = excluded.metadata_json,
                   last_heartbeat_at = excluded.last_heartbeat_at,
                   status = 'online'""",
            (worker_id, _json_dump(metadata), now),
        )

    async def mark_offline_workers(
        self, *, heartbeat_timeout_seconds: int,
    ) -> list[str]:
        from datetime import timedelta

        cutoff_dt = datetime.now(UTC) - timedelta(seconds=max(1, heartbeat_timeout_seconds))
        cutoff = cutoff_dt.isoformat()

        conn = self._connection()
        async with self._lock:
            cursor = await conn.execute(
                """SELECT worker_id
                   FROM bridge_workers
                   WHERE status = 'online' AND last_heartbeat_at < ?""",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            offline = [str(r["worker_id"]) for r in rows]
            if offline:
                for wid in offline:
                    await conn.execute(
                        "UPDATE bridge_workers SET status = 'offline' WHERE worker_id = ?",
                        (wid,),
                    )
                await conn.commit()
        return offline

    async def has_online_bridge_workers(
        self, *, heartbeat_timeout_seconds: int,
    ) -> bool:
        await self.mark_offline_workers(heartbeat_timeout_seconds=heartbeat_timeout_seconds)

        from datetime import timedelta

        cutoff_dt = datetime.now(UTC) - timedelta(seconds=max(1, heartbeat_timeout_seconds))
        cutoff = cutoff_dt.isoformat()
        rows = await self._execute_read(
            """SELECT 1 FROM bridge_workers
               WHERE status = 'online' AND last_heartbeat_at >= ?
               LIMIT 1""",
            (cutoff,),
        )
        return len(rows) > 0

    async def requeue_stale_claims(
        self, *, heartbeat_timeout_seconds: int,
    ) -> int:
        now = _utc_now()
        from datetime import timedelta

        cutoff_dt = datetime.now(UTC) - timedelta(seconds=max(1, heartbeat_timeout_seconds))
        cutoff = cutoff_dt.isoformat()

        offline = await self.mark_offline_workers(
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        )
        conn = self._connection()
        async with self._lock:
            stale_offline_ids: list[str] = []
            if offline:
                placeholders = ",".join("?" for _ in offline)
                cursor = await conn.execute(
                    f"""SELECT request_id
                        FROM tool_requests
                        WHERE status = ? AND claimed_by IN ({placeholders})""",
                    [TOOL_REQUEST_CLAIMED, *offline],
                )
                rows = await cursor.fetchall()
                stale_offline_ids = [str(r["request_id"]) for r in rows]
                if stale_offline_ids:
                    for rid in stale_offline_ids:
                        await conn.execute(
                            """UPDATE tool_requests
                               SET status = ?, claimed_by = NULL, claim_token = NULL,
                                   claimed_at = NULL, lease_expires_at = NULL,
                                   updated_at = ?, version = version + 1
                               WHERE request_id = ? AND status = ?""",
                            (TOOL_REQUEST_PENDING, now, rid, TOOL_REQUEST_CLAIMED),
                        )

            stale_lease_cursor = await conn.execute(
                """SELECT request_id
                   FROM tool_requests
                   WHERE status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
                (TOOL_REQUEST_CLAIMED, now),
            )
            stale_lease_rows = await stale_lease_cursor.fetchall()
            stale_lease_ids = [str(r["request_id"]) for r in stale_lease_rows]
            if stale_lease_ids:
                for rid in stale_lease_ids:
                    await conn.execute(
                        """UPDATE tool_requests
                           SET status = ?, claimed_by = NULL, claim_token = NULL,
                               claimed_at = NULL, lease_expires_at = NULL,
                               updated_at = ?, version = version + 1
                           WHERE request_id = ? AND status = ?""",
                        (TOOL_REQUEST_PENDING, now, rid, TOOL_REQUEST_CLAIMED),
                    )
            await conn.commit()
        return len(stale_offline_ids) + len(stale_lease_ids)

    # ---------------------------------------------------------------- #
    #  State snapshot (Ai-Agent)
    # ---------------------------------------------------------------- #

    async def task_state_snapshot(self, task_id: str) -> dict[str, Any]:
        task = await self.get_task_v2(task_id)
        if task is None:
            raise KeyError(task_id)

        rows = await self._execute_read(
            """SELECT run_id, phase, model, input_json, output_json,
                      started_at, finished_at, retry_count, status
               FROM phase_runs WHERE task_id = ?
               ORDER BY started_at ASC""",
            (task_id,),
        )
        phase_runs = [
            {
                "run_id": str(r["run_id"]),
                "phase": str(r["phase"]),
                "model": str(r["model"]),
                "input": _json_load(str(r["input_json"])) or {},
                "output": _json_load(str(r["output_json"])) or {},
                "started_at": str(r["started_at"]),
                "finished_at": str(r["finished_at"]),
                "retry_count": int(r["retry_count"]),
                "status": str(r["status"]),
            }
            for r in rows
        ]

        rows = await self._execute_read(
            """SELECT transition_id, from_phase, to_phase, reason, failure_class,
                      confidence, validated, created_at
               FROM transitions WHERE task_id = ?
               ORDER BY created_at ASC""",
            (task_id,),
        )
        transitions = [
            {
                "transition_id": str(r["transition_id"]),
                "from_phase": str(r["from_phase"]),
                "to_phase": str(r["to_phase"]),
                "reason": str(r["reason"]),
                "failure_class": str(r["failure_class"]),
                "confidence": float(r["confidence"]),
                "validated": bool(r["validated"]),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]

        rows = await self._execute_read(
            """SELECT request_id, phase, kind, tool_name, payload_json, status,
                      created_at, updated_at, claimed_at, claimed_by, claim_token,
                      resume_token, version, lease_expires_at, attempt, not_before
               FROM tool_requests WHERE task_id = ?
               ORDER BY created_at ASC""",
            (task_id,),
        )
        tool_requests = [
            {
                "request_id": str(r["request_id"]),
                "phase": str(r["phase"]),
                "kind": str(r["kind"]),
                "tool_name": str(r["tool_name"]),
                "payload": _json_load(str(r["payload_json"])) or {},
                "status": str(r["status"]),
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
                "claimed_at": str(r["claimed_at"]) if r["claimed_at"] is not None else None,
                "claimed_by": str(r["claimed_by"]) if r["claimed_by"] is not None else None,
                "claim_token": str(r["claim_token"]) if r["claim_token"] is not None else None,
                "resume_token": str(r["resume_token"]) if r["resume_token"] is not None else None,
                "version": int(r["version"]),
                "lease_expires_at": str(r["lease_expires_at"]) if r["lease_expires_at"] is not None else None,
                "attempt": int(r["attempt"]) if r["attempt"] is not None else 1,
                "not_before": str(r["not_before"]),
            }
            for r in rows
        ]

        rows = await self._execute_read(
            """SELECT result_id, request_id, status, output_json, logs, exit_code,
                      error_message, failure_class, created_at, consumed
               FROM tool_results WHERE task_id = ?
               ORDER BY created_at ASC""",
            (task_id,),
        )
        tool_results = [
            {
                "result_id": str(r["result_id"]),
                "request_id": str(r["request_id"]),
                "status": str(r["status"]),
                "output": _json_load(str(r["output_json"])) or {},
                "logs": str(r["logs"]),
                "exit_code": int(r["exit_code"]) if r["exit_code"] is not None else None,
                "error_message": str(r["error_message"]) if r["error_message"] is not None else None,
                "failure_class": str(r["failure_class"]) if r["failure_class"] is not None else None,
                "created_at": str(r["created_at"]),
                "consumed": bool(r["consumed"]),
            }
            for r in rows
        ]

        return {
            "task": task,
            "phase_runs": phase_runs,
            "transitions": transitions,
            "tool_requests": tool_requests,
            "tool_results": tool_results,
            "budgets": await self.get_budgets(task_id),
            "events": await self.task_events(task_id),
        }
