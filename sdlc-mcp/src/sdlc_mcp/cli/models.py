"""sdlc-mcp models — check and manage LLM models."""

from __future__ import annotations

import subprocess
import sys
from typing import Sequence


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _check_ollama() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        _ok(f"Ollama {result.stdout.strip()}")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _fail("Ollama not found — install from https://ollama.ai")
        return False


def _list_models() -> dict[str, str]:
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True, text=True, timeout=30,
    )
    models: dict[str, str] = {}
    for line in result.stdout.strip().split("\n")[1:]:
        parts = line.split()
        if parts:
            models[parts[0]] = " ".join(parts[1:3]) if len(parts) > 2 else "?"
    return models


def _pull_model(name: str) -> bool:
    print(f"  Pulling {name}...")
    result = subprocess.run(
        ["ollama", "pull", name],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode == 0:
        _ok(f"{name} pulled")
        return True
    _fail(f"Failed to pull {name}: {result.stderr.strip()}")
    return False


RECOMMENDED = [
    "qwen2.5-coder:7b",
    "llama3.2:3b",
]


def run_models(pull: Sequence[str] | None = None) -> int:
    print("╭─────────────────────────────────────╮")
    print("│  SDLC-MCP — Models                  │")
    print("╰─────────────────────────────────────╯")

    if not _check_ollama():
        return 1

    print("\nInstalled models:")
    try:
        models = _list_models()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _fail(f"Could not list models: {exc}")
        return 1

    if models:
        for name, details in models.items():
            print(f"  {name:30s} {details}")
    else:
        _warn("No models installed")

    print(f"\nRecommended models: {', '.join(RECOMMENDED)}")
    for name in RECOMMENDED:
        if name in models:
            _ok(f"{name}")
        else:
            _warn(f"{name} not pulled")

    pull_targets = list(pull) if pull else []
    if not pull_targets and not models:
        pull_targets = RECOMMENDED

    if pull_targets:
        print(f"\nPulling {len(pull_targets)} model(s)...")
        failures = 0
        for name in pull_targets:
            if not _pull_model(name):
                failures += 1
        if failures:
            _fail(f"{failures} pull(s) failed")
            return 1

    print("\nDone.")
    return 0
