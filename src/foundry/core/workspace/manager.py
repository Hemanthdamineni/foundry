"""WorkspaceManager — workspace isolation, context boundaries, and lifecycle.

Each workspace is a self-contained execution environment with its own:
- SQLite store (tasks, phases, events)
- Context graph (repository state, symbol index)
- Memory domain (engrams, engram embeddings)
- Governance boundaries (budget, allowed tools, escalation rules)

The WorkspaceManager coordinates creation, listing, activation, and
deactivation of workspaces. It enforces the **strict isolation** principle:
workspaces cannot see each other's state unless explicitly shared.

Architecture reference:
    L1 Workspace Runtime — "Where does execution live?"
    GV Governance — "Boundaries that can't be crossed"
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
#  Workspace boundaries (governance ceilings per workspace)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkspaceBoundaries:
    """Immutable governance boundaries for a workspace.

    These are the "ceilings that can't be crossed" — per-workspace limits
    that override global defaults.
    """

    max_budget: float = 0.0  # 0 = unlimited
    max_concurrent_tasks: int = 10
    max_retry_per_task: int = 3
    allowed_tools: tuple[str, ...] = ()  # empty = all tools allowed
    denied_tools: tuple[str, ...] = ()
    escalation_enabled: bool = True
    autonomy_level: str = "supervised"  # "autonomous" | "supervised" | "restricted"

    def tool_allowed(self, tool_name: str) -> bool:
        """Check whether a tool is permitted in this workspace."""
        # Denylist takes precedence — if it's explicitly denied, block it
        if tool_name in self.denied_tools:
            return False
        # Allowlist: if non-empty, only listed tools are allowed
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return False
        return True


# --------------------------------------------------------------------------- #
#  Workspace state
# --------------------------------------------------------------------------- #


@dataclass
class WorkspaceState:
    """Mutable workspace state — tracks what's happening inside a workspace."""

    workspace_id: str
    path: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    active_tasks: int = 0
    total_tasks: int = 0
    status: str = "active"  # "active" | "paused" | "archived"
    boundaries: WorkspaceBoundaries = field(default_factory=WorkspaceBoundaries)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last_active timestamp."""
        self.last_active = time.time()


# --------------------------------------------------------------------------- #
#  WorkspaceManager
# --------------------------------------------------------------------------- #


class WorkspaceManager:
    """Manages workspace creation, activation, and isolation.

    Usage::

        mgr = WorkspaceManager()
        ws = mgr.create("/path/to/project", boundaries=WorkspaceBoundaries(...))
        mgr.activate(ws.workspace_id)
        current = mgr.current()
        # ... work happens inside workspace ...
        mgr.deactivate()
    """

    _MANIFEST = ".foundry/workspace.json"

    def __init__(self, search_from: str | Path | None = None) -> None:
        self._search_root = Path(search_from) if search_from else Path.cwd()
        self._workspaces: dict[str, WorkspaceState] = {}
        self._current_id: str | None = None
        self._load_existing()

    # -- Discovery ---------------------------------------------------------- #

    def _load_existing(self) -> None:
        """Scan from search_root upward for .foundry/workspace.json files."""
        for parent in [self._search_root] + list(self._search_root.parents):
            manifest = parent / self._MANIFEST
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    ws_id = data.get("workspace_id", "")
                    if ws_id:
                        boundaries = WorkspaceBoundaries(
                            max_budget=data.get("max_budget", 0.0),
                            max_concurrent_tasks=data.get("max_concurrent_tasks", 10),
                            max_retry_per_task=data.get("max_retry_per_task", 3),
                            allowed_tools=tuple(data.get("allowed_tools", [])),
                            denied_tools=tuple(data.get("denied_tools", [])),
                            escalation_enabled=data.get("escalation_enabled", True),
                            autonomy_level=data.get("autonomy_level", "supervised"),
                        )
                        state = WorkspaceState(
                            workspace_id=ws_id,
                            path=str(parent),
                            created_at=data.get("created_at", time.time()),
                            last_active=data.get("last_active", time.time()),
                            active_tasks=data.get("active_tasks", 0),
                            total_tasks=data.get("total_tasks", 0),
                            status=data.get("status", "active"),
                            boundaries=boundaries,
                            metadata=data.get("metadata", {}),
                        )
                        self._workspaces[ws_id] = state
                except (json.JSONDecodeError, KeyError):
                    continue

    # -- CRUD --------------------------------------------------------------- #

    def create(
        self,
        path: str | Path,
        *,
        workspace_id: str | None = None,
        boundaries: WorkspaceBoundaries | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceState:
        """Create a new workspace at the given path.

        Writes ``.foundry/workspace.json`` as the workspace manifest.
        """
        import uuid

        target = Path(path).expanduser().resolve()
        foundry_dir = target / ".foundry"
        foundry_dir.mkdir(parents=True, exist_ok=True)

        ws_id = workspace_id or f"ws_{uuid.uuid4().hex[:12]}"

        state = WorkspaceState(
            workspace_id=ws_id,
            path=str(target),
            boundaries=boundaries or WorkspaceBoundaries(),
            metadata=metadata or {},
        )

        # Persist manifest
        manifest_path = target / self._MANIFEST
        manifest_data = {
            "workspace_id": state.workspace_id,
            "path": state.path,
            "created_at": state.created_at,
            "last_active": state.last_active,
            "active_tasks": state.active_tasks,
            "total_tasks": state.total_tasks,
            "status": state.status,
            "max_budget": state.boundaries.max_budget,
            "max_concurrent_tasks": state.boundaries.max_concurrent_tasks,
            "max_retry_per_task": state.boundaries.max_retry_per_task,
            "allowed_tools": list(state.boundaries.allowed_tools),
            "denied_tools": list(state.boundaries.denied_tools),
            "escalation_enabled": state.boundaries.escalation_enabled,
            "autonomy_level": state.boundaries.autonomy_level,
            "metadata": state.metadata,
        }
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self._workspaces[ws_id] = state
        return state

    def get(self, workspace_id: str) -> WorkspaceState | None:
        return self._workspaces.get(workspace_id)

    def list_all(self) -> list[WorkspaceState]:
        return list(self._workspaces.values())

    def activate(self, workspace_id: str) -> WorkspaceState | None:
        """Set a workspace as the current active workspace."""
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return None
        self._current_id = workspace_id
        ws.touch()
        return ws

    def deactivate(self) -> None:
        """Clear the current active workspace."""
        self._current_id = None

    def current(self) -> WorkspaceState | None:
        """Return the currently active workspace, if any."""
        if self._current_id:
            return self._workspaces.get(self._current_id)
        return None

    def delete(self, workspace_id: str) -> bool:
        """Archive (soft-delete) a workspace. Does NOT delete files."""
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        ws.status = "archived"
        if self._current_id == workspace_id:
            self._current_id = None
        return True

    # -- Governance --------------------------------------------------------- #

    def check_tool_allowed(self, workspace_id: str, tool_name: str) -> bool:
        """Check whether a tool is permitted in the given workspace."""
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        return ws.boundaries.tool_allowed(tool_name)

    def check_budget(self, workspace_id: str, spent: float) -> bool:
        """Check whether a workspace has budget remaining."""
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        if ws.boundaries.max_budget <= 0:
            return True  # unlimited
        return spent < ws.boundaries.max_budget

    def check_concurrency(self, workspace_id: str) -> bool:
        """Check whether a workspace can accept more tasks."""
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        return ws.active_tasks < ws.boundaries.max_concurrent_tasks
