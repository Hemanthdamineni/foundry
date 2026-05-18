"""Schema migrations — idempotent database and config upgrades."""

from __future__ import annotations

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    1: [
        "CREATE TABLE IF NOT EXISTS tasks ("
        "  task_id TEXT PRIMARY KEY,"
        "  data TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "  updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")",
        "CREATE TABLE IF NOT EXISTS phase_history ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  task_id TEXT NOT NULL REFERENCES tasks(task_id),"
        "  phase TEXT NOT NULL,"
        "  output TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")",
        "CREATE TABLE IF NOT EXISTS checkpoints ("
        "  task_id TEXT PRIMARY KEY,"
        "  data TEXT NOT NULL,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")",
        "CREATE TABLE IF NOT EXISTS traces ("
        "  id TEXT PRIMARY KEY,"
        "  task_id TEXT,"
        "  phase TEXT,"
        "  action TEXT,"
        "  status TEXT,"
        "  output TEXT,"
        "  verdict TEXT,"
        "  trace_data TEXT,"
        "  created_at TEXT DEFAULT (datetime('now')),"
        "  updated_at TEXT DEFAULT (datetime('now'))"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_traces_task_id ON traces(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_traces_phase ON traces(phase)",
        "CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)",
        "CREATE TABLE IF NOT EXISTS engrams ("
        "  id TEXT PRIMARY KEY,"
        "  content TEXT,"
        "  tags TEXT,"
        "  source TEXT,"
        "  importance INTEGER DEFAULT 1,"
        "  metadata TEXT,"
        "  created_at TEXT DEFAULT (datetime('now'))"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_engrams_tags ON engrams(tags)",
        "CREATE INDEX IF NOT EXISTS idx_engrams_source ON engrams(source)",
        "CREATE TABLE IF NOT EXISTS debate_logs ("
        "  id TEXT PRIMARY KEY,"
        "  task_id TEXT,"
        "  round_num INTEGER,"
        "  agent_role TEXT,"
        "  content TEXT,"
        "  verdict TEXT,"
        "  created_at TEXT DEFAULT (datetime('now'))"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_debate_logs_task_id ON debate_logs(task_id)",
    ],
}


def migration_for_version(version: int) -> list[str]:
    """Get SQL statements for migrating to *version*."""
    return MIGRATIONS.get(version, [])
