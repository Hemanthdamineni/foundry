"""Tests for WorkspaceManager — workspace isolation and governance."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from foundry.core.workspace.manager import (
    WorkspaceBoundaries,
    WorkspaceManager,
    WorkspaceState,
)


@pytest.fixture
def tmp_workspace_dir(tmp_path: Path) -> Path:
    return tmp_path / "project"


class TestWorkspaceBoundaries:
    def test_default_boundaries(self) -> None:
        b = WorkspaceBoundaries()
        assert b.max_budget == 0.0  # unlimited
        assert b.max_concurrent_tasks == 10
        assert b.max_retry_per_task == 3
        assert b.allowed_tools == ()
        assert b.denied_tools == ()
        assert b.autonomy_level == "supervised"

    def test_tool_allowed_unrestricted(self) -> None:
        b = WorkspaceBoundaries()
        assert b.tool_allowed("any_tool") is True

    def test_tool_allowed_with_allowlist(self) -> None:
        b = WorkspaceBoundaries(allowed_tools=("read", "write", "execute"))
        assert b.tool_allowed("read") is True
        assert b.tool_allowed("delete") is False

    def test_tool_allowed_with_denylist(self) -> None:
        b = WorkspaceBoundaries(denied_tools=("rm", "sudo"))
        assert b.tool_allowed("read") is True
        assert b.tool_allowed("rm") is False
        assert b.tool_allowed("sudo") is False

    def test_denylist_takes_precedence(self) -> None:
        b = WorkspaceBoundaries(
            allowed_tools=("read", "write"),
            denied_tools=("write"),
        )
        assert b.tool_allowed("read") is True
        assert b.tool_allowed("write") is False
        assert b.tool_allowed("execute") is False  # not in allowlist


class TestWorkspaceManager:
    def test_create_workspace(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(tmp_workspace_dir)

        assert ws.workspace_id.startswith("ws_")
        assert ws.path == str(tmp_workspace_dir)
        assert ws.status == "active"

        # Manifest was written
        manifest = tmp_workspace_dir / ".foundry" / "workspace.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert data["workspace_id"] == ws.workspace_id

    def test_create_with_custom_boundaries(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        boundaries = WorkspaceBoundaries(
            max_budget=10.0,
            autonomy_level="autonomous",
            denied_tools=("sudo",),
        )
        ws = mgr.create(tmp_workspace_dir, boundaries=boundaries)

        assert ws.boundaries.max_budget == 10.0
        assert ws.boundaries.autonomy_level == "autonomous"
        assert ws.boundaries.tool_allowed("sudo") is False

    def test_activate_deactivate(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(tmp_workspace_dir)

        mgr.activate(ws.workspace_id)
        assert mgr.current() is ws

        mgr.deactivate()
        assert mgr.current() is None

    def test_list_all(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        mgr.create(tmp_workspace_dir)
        mgr.create(tmp_workspace_dir / "sub")

        all_ws = mgr.list_all()
        assert len(all_ws) == 2

    def test_delete_archives(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(tmp_workspace_dir)
        mgr.activate(ws.workspace_id)

        assert mgr.delete(ws.workspace_id) is True
        assert ws.status == "archived"
        assert mgr.current() is None  # deactivated on delete

    def test_check_tool_allowed(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(
            tmp_workspace_dir,
            boundaries=WorkspaceBoundaries(denied_tools=("rm",)),
        )

        assert mgr.check_tool_allowed(ws.workspace_id, "read") is True
        assert mgr.check_tool_allowed(ws.workspace_id, "rm") is False
        assert mgr.check_tool_allowed("nonexistent", "read") is False

    def test_check_budget(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(
            tmp_workspace_dir,
            boundaries=WorkspaceBoundaries(max_budget=10.0),
        )

        assert mgr.check_budget(ws.workspace_id, 5.0) is True
        assert mgr.check_budget(ws.workspace_id, 10.0) is False
        assert mgr.check_budget(ws.workspace_id, 15.0) is False

    def test_check_budget_unlimited(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(tmp_workspace_dir)  # default: max_budget=0 (unlimited)

        assert mgr.check_budget(ws.workspace_id, 999.0) is True

    def test_check_concurrency(self, tmp_workspace_dir: Path) -> None:
        mgr = WorkspaceManager(search_from=tmp_workspace_dir)
        ws = mgr.create(
            tmp_workspace_dir,
            boundaries=WorkspaceBoundaries(max_concurrent_tasks=2),
        )

        assert mgr.check_concurrency(ws.workspace_id) is True
        ws.active_tasks = 2
        assert mgr.check_concurrency(ws.workspace_id) is False
