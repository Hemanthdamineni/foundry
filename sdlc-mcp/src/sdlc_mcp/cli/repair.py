"""Repair missing SDLC-MCP workspace infrastructure."""

from __future__ import annotations

from sdlc_mcp.bootstrap.engine import BootstrapEngine
from sdlc_mcp.bootstrap.workspace import WorkspaceState, detect_workspace, resolve_workspace
from sdlc_mcp.cli.install import DEFAULT_PLUGINS, install_plugins


def run_repair(*, workspace: str | None = None) -> int:
    resolution = resolve_workspace(workspace=workspace)
    root = resolution.workspace_root
    engine = BootstrapEngine(root)
    changed = engine.ensure_workspace()
    state, sdlc_dir = detect_workspace(root)

    print("SDLC-MCP repair")
    print(f"  execution_root: {resolution.execution_root}")
    print(f"  workspace: {root}")
    print(f"  selection_reason: {resolution.reason}")
    print(f"  sdlc_dir: {sdlc_dir}")
    print(f"  state: {state.value}")
    print(f"  changed: {changed}")

    failures = install_plugins(DEFAULT_PLUGINS)
    if failures:
        print(f"  plugin_failures: {', '.join(failures)}")

    return 0 if state == WorkspaceState.READY else 1
