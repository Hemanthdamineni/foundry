"""sdlc-mcp upgrade — upgrade prompts, templates, and config safely."""

from __future__ import annotations

from pathlib import Path

from sdlc.cli.init import (
    _install_context,
    _install_graphs,
    _install_prompts,
    _install_skill_md,
    _merge_opencode_json,
)
from sdlc.cli.merger import merge_opencode_json
from sdlc.templates import OPENCODE_FRAGMENT


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _info(msg: str) -> None:
    print(f"  · {msg}")


def run_upgrade() -> int:
    root = Path.cwd()

    print("╭─────────────────────────────────────╮")
    print("│  SDLC-MCP — Upgrade                 │")
    print("╰─────────────────────────────────────╯")

    print("\nUpgrading SKILL.md...")
    _install_skill_md(root, force=False)

    print("\nUpgrading prompt files...")
    _install_prompts(root, force=False)

    print("\nUpgrading context files...")
    _install_context(root, force=False)

    print("\nUpgrading graph templates...")
    _install_graphs(root, force=False)

    print("\nMerging opencode.json...")
    _merge_opencode_json(root)

    print("\nDone. New templates merged without overwriting existing content.")
    return 0
