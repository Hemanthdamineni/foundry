"""Workspace bootstrap CLI for SDLC-MCP."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from sdlc_mcp.bootstrap.engine import BootstrapEngine
from sdlc_mcp.bootstrap.workspace import WorkspaceState, detect_workspace, resolve_workspace
from sdlc_mcp.cli.install import DEFAULT_PLUGINS, install_plugins


def _ok(msg: str) -> None:
    print(f"  OK {msg}")


def _info(msg: str) -> None:
    print(f"  .. {msg}")


def _warn(msg: str) -> None:
    print(f"  !! {msg}")


def _fail(msg: str) -> None:
    print(f"  XX {msg}")


def _check_python() -> bool:
    if sys.version_info < (3, 12):
        _fail(f"Python >= 3.12 required, have {sys.version_info.major}.{sys.version_info.minor}")
        return False
    _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def _check_has_cmd(name: str, label: str | None = None) -> bool:
    label = label or name
    if shutil.which(name):
        _ok(f"{label} available")
        return True
    _warn(f"{label} not found (optional)")
    return False


def _check_opencode() -> bool:
    opencode = shutil.which("opencode")
    if not opencode:
        _warn("opencode CLI not found; MCP still works when registered by your harness")
        return False
    try:
        result = subprocess.run(
            ["opencode", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        _warn("opencode CLI found but version check failed")
        return False
    version = result.stdout.strip() or "unknown"
    _ok(f"OpenCode ({version})")
    return True


def _check_ollama_model(model: str) -> bool:
    if not shutil.which("ollama"):
        return False
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return model in result.stdout


def _check_models() -> None:
    if not shutil.which("ollama"):
        _info("Ollama not installed; runtime LLM providers are disabled by default")
        return
    for model in ("qwen2.5-coder:7b", "llama3.2:3b"):
        if _check_ollama_model(model):
            _ok(f"Ollama model {model}")
        else:
            _warn(f"Ollama model {model} not pulled")


def _validate_env() -> bool:
    print("\nValidating environment...")
    ok = _check_python()
    _check_opencode()
    _check_has_cmd("node", "Node.js")
    _check_has_cmd("uv", "uv")
    _check_has_cmd("pipx", "pipx")
    _check_has_cmd("ollama", "Ollama")
    _info("OpenCode's selected model is used by default for all phase reasoning")
    return ok


def _print_status(root: Path, changed: bool) -> None:
    state, sdlc_dir = detect_workspace(root)
    label = "changed" if changed else "already up to date"
    _ok(f"Workspace {label}: {root}")
    _ok(f"State: {state.value}")
    _ok(f"SDLC dir: {sdlc_dir}")
    if state != WorkspaceState.READY:
        _warn("Workspace is not fully ready; run `sdlc-mcp repair` or inspect .sdlc/")


def run_init(
    *,
    force: bool = False,
    no_plugins: bool = False,
    workspace: str | None = None,
) -> int:
    print("SDLC-MCP bootstrap")
    _validate_env()

    resolution = resolve_workspace(workspace=workspace)
    root = resolution.workspace_root
    _info(f"Execution cwd: {resolution.execution_root}")
    _info(f"Workspace root: {resolution.workspace_root}")
    _info(f"Selection reason: {resolution.reason}")
    engine = BootstrapEngine(root)
    changed = engine.upgrade() if force else engine.ensure_workspace()
    _print_status(root, changed)

    if not no_plugins:
        print("\nInstalling OpenCode plugins...")
        failures = install_plugins(DEFAULT_PLUGINS)
        for plugin in DEFAULT_PLUGINS:
            if plugin in failures:
                _warn(f"Failed to install plugin: {plugin}")
            else:
                _ok(f"Plugin {plugin} installed")

    print("\nReady. Open this folder in OpenCode, select foundry, and prompt normally.")
    return 0
