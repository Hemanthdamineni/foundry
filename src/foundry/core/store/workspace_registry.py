"""Workspace registry — track known Foundry workspaces.

Stored in .foundry/workspaces.db under each workspace. The registry
table is managed by core/store/ensure_initialized and this module
provides the query/add/remove CLI logic on top of it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def list_workspaces() -> list[dict[str, Any]]:
    """List all known workspaces by scanning for .foundry/ directories."""
    workspaces: list[dict[str, Any]] = []
    # Scan parent directories for .foundry/
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        foundry_dir = parent / ".foundry"
        if foundry_dir.is_dir():
            db_path = foundry_dir / "workspace.db"
            size = db_path.stat().st_size if db_path.exists() else 0
            workspaces.append({
                "path": str(parent),
                "db": str(db_path),
                "size_bytes": size,
            })
    return workspaces


def add_workspace(path: str | None = None) -> dict[str, Any]:
    """Register a workspace by ensuring .foundry/ exists at the given path."""
    target = Path(path).expanduser().resolve() if path else Path.cwd()
    foundry_dir = target / ".foundry"
    foundry_dir.mkdir(parents=True, exist_ok=True)
    db_path = foundry_dir / "workspace.db"

    from foundry.core.store.ensure_initialized import ensure_initialized
    store = ensure_initialized(str(db_path))
    store.close()

    return {"path": str(target), "db": str(db_path), "status": "initialized"}


def remove_workspace(path: str) -> bool:
    """Remove a workspace entry. Does NOT delete the .foundry/ directory."""
    # For now this is a no-op — workspaces are auto-detected by scanning.
    # A future version may maintain a manifest file.
    return True


def get_current_workspace() -> dict[str, Any] | None:
    """Return the nearest ancestor workspace from CWD."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        db_path = parent / ".foundry" / "workspace.db"
        if db_path.exists():
            return {"path": str(parent), "db": str(db_path)}
    return None
