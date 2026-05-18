"""Upgrade a workspace to the latest SDLC-MCP schema and templates."""

from __future__ import annotations

from sdlc_mcp.bootstrap.engine import BootstrapEngine
from sdlc_mcp.bootstrap.workspace import detect_workspace, resolve_workspace


def run_upgrade(*, workspace: str | None = None) -> int:
    resolution = resolve_workspace(workspace=workspace)
    root = resolution.workspace_root
    changed = BootstrapEngine(root).upgrade()
    state, sdlc_dir = detect_workspace(root)
    print("SDLC-MCP upgrade")
    print(f"  execution_root: {resolution.execution_root}")
    print(f"  workspace: {root}")
    print(f"  selection_reason: {resolution.reason}")
    print(f"  sdlc_dir: {sdlc_dir}")
    print(f"  state: {state.value}")
    print(f"  changed: {changed}")
    return 0
