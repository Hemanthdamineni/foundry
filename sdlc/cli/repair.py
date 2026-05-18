"""sdlc-mcp repair — repair broken config or plugin setup."""

from __future__ import annotations

import shutil
from pathlib import Path

from sdlc.cli.init import run_init
from sdlc.cli.install import DEFAULT_PLUGINS, install_plugins, install_ocx


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _info(msg: str) -> None:
    print(f"  · {msg}")


def _check_opencode_json(root: Path) -> bool:
    target = root / "opencode.json"
    if not target.exists():
        _warn("opencode.json missing — will be created")
        return False

    import json

    try:
        json.loads(target.read_text())
        _ok("opencode.json is valid JSON")
        return True
    except json.JSONDecodeError:
        _warn("opencode.json is corrupted — will recreate")
        target.unlink()
        return False


def _check_mcp_entry() -> bool:
    """Verify sdlc-mcp CLI is importable."""
    try:
        from sdlc.cli import cli as _cli  # noqa: F401

        _ok("sdlc-mcp CLI importable")
        return True
    except ImportError as exc:
        _warn(f"sdlc-mcp CLI not importable: {exc}")
        return False


def _repair_plugins() -> None:
    if not shutil.which("ocx"):
        if install_ocx():
            _ok("ocx installed")
        else:
            _warn("Could not install ocx")
            return

    failures = install_plugins(DEFAULT_PLUGINS)
    for plugin in DEFAULT_PLUGINS:
        if plugin in failures:
            _warn(f"Failed to reinstall plugin: {plugin}")
        else:
            _ok(f"Plugin {plugin}")


def _repair_db(root: Path) -> None:
    db_path = root / "data" / "sdlc.db"
    if db_path.exists():
        _ok("Database exists")
        return

    from sdlc.cli.init import _create_sdlc_db

    _create_sdlc_db(root)


def run_repair() -> int:
    root = Path.cwd()

    print("╭─────────────────────────────────────╮")
    print("│  SDLC-MCP — Repair                  │")
    print("╰─────────────────────────────────────╯")

    issues = 0

    # 1. Check MCP entry
    if not _check_mcp_entry():
        _warn("Reinstall with: pip install -e .")
        issues += 1

    # 2. Check opencode.json
    _check_opencode_json(root)

    # 3. Regenerate project config (non-destructive merge)
    print("\nRegenerating project config...")
    run_init(force=False, no_plugins=True)

    # 4. Repair plugins
    print("\nRepairing plugins...")
    _repair_plugins()

    # 5. Repair database
    print("\nRepairing database...")
    _repair_db(root)

    print(f"\n{'Repair complete!' if issues == 0 else f'{issues} issue(s) require manual fix'}")
    return 0 if issues == 0 else 1
