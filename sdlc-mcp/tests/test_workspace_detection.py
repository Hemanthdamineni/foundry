"""Workspace root resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc_mcp.bootstrap.workspace import WorkspaceState, detect_workspace, resolve_workspace


def test_nested_folder_ignores_parent_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    execution = repo / "Test"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()

    resolution = resolve_workspace(execution)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == execution
    assert resolution.selected_by == "current_working_directory"
    assert resolution.reason == "current working directory"


def test_nested_opencode_does_not_expand_workspace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    execution = repo / "Test"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()
    (execution / "opencode.json").write_text('{"$schema":"https://opencode.ai/config.json"}')

    resolution = resolve_workspace(execution)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == execution
    assert resolution.selected_by == "current_working_directory"
    assert "opencode.json" in resolution.markers


def test_monorepo_subfolder_is_workspace(tmp_path: Path) -> None:
    monorepo = tmp_path / "monorepo"
    frontend = monorepo / "frontend"
    (monorepo / ".git").mkdir(parents=True)
    (monorepo / "backend").mkdir()
    frontend.mkdir()

    resolution = resolve_workspace(frontend)

    assert resolution.execution_root == frontend
    assert resolution.workspace_root == frontend
    assert resolution.selected_by == "current_working_directory"


def test_empty_folder_is_workspace(tmp_path: Path) -> None:
    execution = tmp_path / "empty-folder"
    execution.mkdir()

    resolution = resolve_workspace(execution)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == execution
    assert resolution.selected_by == "current_working_directory"
    assert resolution.markers == ()


def test_explicit_workspace_overrides_execution_and_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    execution = repo / "nested"
    workspace = tmp_path / "isolated"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()
    workspace.mkdir()

    resolution = resolve_workspace(execution, workspace=workspace)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == workspace
    assert resolution.selected_by == "explicit_workspace"
    assert resolution.reason == "explicit workspace flag"


def test_foundry_environment_overrides_detection(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    execution = repo / "nested"
    workspace = tmp_path / "env-workspace"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("FOUNDRY_WORKSPACE", str(workspace))

    resolution = resolve_workspace(execution)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == workspace
    assert resolution.selected_by == "environment"
    assert resolution.reason == "FOUNDRY_WORKSPACE environment variable"


def test_other_workspace_env_vars_are_ignored(tmp_path: Path, monkeypatch) -> None:
    execution = tmp_path / "execution"
    workspace = tmp_path / "ignored-workspace"
    execution.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("SDLC_WORKSPACE", str(workspace))
    monkeypatch.setenv("FOUNDRY_WORKSPACE_ROOT", str(workspace))

    resolution = resolve_workspace(execution)

    assert resolution.execution_root == execution
    assert resolution.workspace_root == execution
    assert resolution.selected_by == "current_working_directory"


def test_detect_workspace_is_low_level_state_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    execution = repo / "nested"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()

    state, sdlc_dir = detect_workspace(execution)

    assert state == WorkspaceState.UNINITIALIZED
    assert sdlc_dir == execution / ".sdlc"


@pytest.mark.asyncio
async def test_mcp_detect_ignores_path_and_workspace_arguments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from sdlc_mcp.runtime.app import sdlc_detect_workspace

    repo = tmp_path / "repo"
    execution = repo / "Test"
    override = tmp_path / "override"
    (repo / ".git").mkdir(parents=True)
    execution.mkdir()
    override.mkdir()
    monkeypatch.chdir(execution)

    result = await sdlc_detect_workspace(path=str(repo), workspace=str(override))

    assert result["execution_root"] == str(execution)
    assert result["workspace_root"] == str(execution)
    assert result["selected_by"] == "current_working_directory"
    assert result["path_override_ignored"] is True
    assert result["workspace_override_ignored"] is True
