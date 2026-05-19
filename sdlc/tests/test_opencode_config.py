"""Validates opencode.json config files against known-good key sets.

Scans the repo for ALL opencode.json files (excluding build artifacts)
and validates each against a known set of valid top-level keys. This
prevents regressions where removed keys (agents, mcpServers, plugins)
get re-introduced and break `opencode` CLI startup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _find_repo_root() -> Path:
    p = Path(__file__).resolve().parent
    for parent in [p] + list(p.parents):
        if (parent / ".git").is_dir() or (parent / ".git").is_file():
            return parent
    msg = "Could not find repo root (.git not found)"
    raise RuntimeError(msg)


REPO_DIR = _find_repo_root()

SKIP_DIRS: set[str] = {".git", "node_modules", "__pycache__", ".pixi", ".venv",
                       "graphify-out", "data"}

KNOWN_DEPRECATED_KEYS: set[str] = {"agents", "mcpServers", "plugins"}

VALID_TOP_LEVEL_KEYS: set[str] = {
    "$schema", "shell", "logLevel", "server", "command", "skills",
    "reference", "watcher", "snapshot", "plugin", "share", "autoshare",
    "autoupdate", "disabled_providers", "enabled_providers", "model",
    "small_model", "default_agent", "username", "mode", "agent",
    "provider", "mcp", "formatter", "lsp", "instructions", "layout",
    "permission", "tools", "attachment", "enterprise", "tool_output",
    "compaction", "experimental",
}


def _find_opencode_configs() -> list[Path]:
    configs: list[Path] = []
    for p in REPO_DIR.rglob("opencode.json"):
        rel = p.relative_to(REPO_DIR)
        if any(skip in rel.parts for skip in SKIP_DIRS):
            continue
        configs.append(p)
    return sorted(configs)


def _load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


@pytest.fixture(params=_find_opencode_configs(),
                ids=lambda p: str(p.relative_to(REPO_DIR)))
def config_path(request: pytest.FixtureRequest) -> Path:
    return request.param


def test_config_is_valid_json(config_path: Path) -> None:
    raw = config_path.read_text()
    parsed = json.loads(raw)
    assert isinstance(parsed, dict), (
        f"{config_path.name}: must be a JSON object"
    )


def test_no_deprecated_top_level_keys(config_path: Path) -> None:
    config = _load_config(config_path)
    found = KNOWN_DEPRECATED_KEYS & config.keys()
    assert not found, (
        f"{config_path.relative_to(REPO_DIR)}: deprecated keys {found}. "
        f"Use 'agent' instead of 'agents', 'mcp' instead of 'mcpServers'."
    )


def test_all_keys_are_recognized(config_path: Path) -> None:
    config = _load_config(config_path)
    unknown = set(config.keys()) - VALID_TOP_LEVEL_KEYS
    assert not unknown, (
        f"{config_path.relative_to(REPO_DIR)}: unknown keys {unknown}"
    )


def test_instructions_is_list(config_path: Path) -> None:
    config = _load_config(config_path)
    val = config.get("instructions")
    if val is not None:
        assert isinstance(val, list), (
            f"{config_path.relative_to(REPO_DIR)}: 'instructions' must be a list"
        )


def test_agent_config_is_object(config_path: Path) -> None:
    config = _load_config(config_path)
    val = config.get("agent")
    if val is not None:
        assert isinstance(val, dict), (
            f"{config_path.relative_to(REPO_DIR)}: 'agent' must be an object"
        )


def test_mcp_config_is_object(config_path: Path) -> None:
    config = _load_config(config_path)
    val = config.get("mcp")
    if val is not None:
        assert isinstance(val, dict), (
            f"{config_path.relative_to(REPO_DIR)}: 'mcp' must be an object"
        )
        for name, svc in val.items():
            assert isinstance(svc, dict), (
                f"{config_path.relative_to(REPO_DIR)}: MCP '{name}' must be object"
            )
            svc_type = svc.get("type")
            assert svc_type in ("local", "remote"), (
                f"{config_path.relative_to(REPO_DIR)}: MCP '{name}' "
                f"unsupported type '{svc_type}'"
            )
