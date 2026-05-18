"""Validate SDLC-MCP installation and current workspace."""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

from sdlc_mcp.bootstrap.workspace import WorkspaceState, detect_workspace, resolve_workspace


def _line(status: str, message: str) -> None:
    print(f"  {status} {message}")


def _check_python() -> bool:
    ok = sys.version_info >= (3, 12)
    status = "OK" if ok else "XX"
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    _line(status, f"Python {version}")
    return ok


def _check_command(name: str, *, required: bool = False) -> bool:
    ok = shutil.which(name) is not None
    status = "OK" if ok else ("XX" if required else "..")
    suffix = "available" if ok else "not found"
    _line(status, f"{name}: {suffix}")
    return ok or not required


def _check_workspace(root: Path) -> bool:
    state, sdlc_dir = detect_workspace(root)
    ok = state == WorkspaceState.READY
    _line("OK" if ok else "XX", f"workspace_state={state.value}")
    _line("..", f"workspace={root}")
    _line("..", f"sdlc_dir={sdlc_dir}")
    return ok


def _check_sqlite(root: Path) -> bool:
    db_path = root / ".sdlc" / "workspace.db"
    if not db_path.exists():
        _line("XX", f"database missing: {db_path}")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
    except sqlite3.Error as exc:
        _line("XX", f"database check failed: {exc}")
        return False

    expected = {"tasks", "phase_history", "checkpoints", "traces", "engrams", "debate_logs"}
    missing = expected - tables
    _line("OK" if mode.lower() == "wal" else "..", f"sqlite_journal={mode}")
    if missing:
        _line("XX", f"missing_tables={sorted(missing)}")
        return False
    _line("OK", "database schema ready")
    return True


def run_doctor(*, workspace: str | None = None) -> int:
    resolution = resolve_workspace(workspace=workspace)
    root = resolution.workspace_root
    print("SDLC-MCP doctor")
    _line("..", f"execution_root={resolution.execution_root}")
    _line("..", f"workspace_root={resolution.workspace_root}")
    _line("..", f"selection_reason={resolution.reason}")
    checks = [
        _check_python(),
        _check_command("sdlc-mcp", required=False),
        _check_command("opencode", required=False),
        _check_workspace(root),
        _check_sqlite(root),
    ]
    return 0 if all(checks) else 1
