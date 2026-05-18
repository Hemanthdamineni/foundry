"""Workspace detection — determines if a directory is SDLC-ready."""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from pathlib import Path


class WorkspaceState(enum.Enum):
    UNINITIALIZED = "uninitialized"
    PARTIAL = "partial"
    READY = "ready"
    NEEDS_UPGRADE = "needs_upgrade"


@dataclass(frozen=True)
class WorkspaceResolution:
    """Resolved Foundry workspace context for an execution directory."""

    execution_root: Path
    workspace_root: Path
    reason: str
    selected_by: str
    markers: tuple[str, ...]


PROJECT_MARKERS: tuple[str, ...] = (
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
)
LOCAL_WORKSPACE_MARKERS: tuple[str, ...] = (
    ".foundry",
    ".sdlc",
    "opencode.json",
)
ENV_WORKSPACE_KEY = "FOUNDRY_WORKSPACE"


def _workspace_state(root: Path) -> tuple[WorkspaceState, Path]:
    sdlc_dir = root / ".sdlc"

    if not sdlc_dir.exists():
        return WorkspaceState.UNINITIALIZED, sdlc_dir

    # Check for minimal bootstrap completeness
    has_state = (sdlc_dir / "state.json").exists()
    has_db = (sdlc_dir / "workspace.db").exists()
    has_traces = sdlc_dir.joinpath("traces").is_dir()
    has_checkpoints = sdlc_dir.joinpath("checkpoints").is_dir()
    has_logs = sdlc_dir.joinpath("logs").is_dir()
    has_config = sdlc_dir.joinpath("config").is_dir()

    if has_state and has_db and has_traces and has_checkpoints and has_logs and has_config:
        # Check schema version
        version_file = sdlc_dir / ".version"
        if version_file.exists():
            version = version_file.read_text().strip()
            if version != "1":
                return WorkspaceState.NEEDS_UPGRADE, sdlc_dir
        return WorkspaceState.READY, sdlc_dir

    if has_state or has_db or has_traces or has_checkpoints or has_config:
        return WorkspaceState.PARTIAL, sdlc_dir

    return WorkspaceState.UNINITIALIZED, sdlc_dir


def _markers(root: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if (root / name).exists())


def _env_workspace() -> tuple[str, Path] | None:
    value = os.environ.get(ENV_WORKSPACE_KEY)
    if value:
        return ENV_WORKSPACE_KEY, Path(value).expanduser().resolve()
    return None


def resolve_workspace(
    path: Path | str | None = None,
    *,
    workspace: Path | str | None = None,
) -> WorkspaceResolution:
    """Resolve execution and selected Foundry workspace roots.

    Precedence:
    1. explicit workspace argument
    2. FOUNDRY_WORKSPACE environment variable
    3. current working directory

    This intentionally performs no parent-directory discovery. Parent
    repositories, package manifests, and OpenCode configs are ignored unless
    selected by an explicit override.
    """
    execution_root = Path(path).expanduser().resolve() if path else Path.cwd().resolve()

    if workspace is not None:
        selected = Path(workspace).expanduser().resolve()
        return WorkspaceResolution(
            execution_root=execution_root,
            workspace_root=selected,
            reason="explicit workspace flag",
            selected_by="explicit_workspace",
            markers=_markers(selected, LOCAL_WORKSPACE_MARKERS + PROJECT_MARKERS),
        )

    env = _env_workspace()
    if env is not None:
        key, selected = env
        return WorkspaceResolution(
            execution_root=execution_root,
            workspace_root=selected,
            reason=f"{key} environment variable",
            selected_by="environment",
            markers=_markers(selected, LOCAL_WORKSPACE_MARKERS + PROJECT_MARKERS),
        )

    return WorkspaceResolution(
        execution_root=execution_root,
        workspace_root=execution_root,
        reason="current working directory",
        selected_by="current_working_directory",
        markers=_markers(execution_root, LOCAL_WORKSPACE_MARKERS + PROJECT_MARKERS),
    )


def detect_workspace(path: Path | str | None = None) -> tuple[WorkspaceState, Path]:
    """Detect SDLC workspace state in *path* (or CWD).

    Returns (state, sdlc_dir_path).
    """
    root = Path(path).resolve() if path else Path.cwd()
    return _workspace_state(root)
