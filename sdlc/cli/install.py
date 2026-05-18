"""OpenCode plugin installer — wraps ocx for automatic plugin setup."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Sequence


def _has_ocx() -> bool:
    return shutil.which("ocx") is not None


def install_ocx(quiet: bool = False) -> bool:
    """Install ocx CLI if not present."""
    if _has_ocx():
        return True
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "opencode-cli"],
            capture_output=True,
            check=True,
        )
        return _has_ocx()
    except subprocess.CalledProcessError:
        return False


def install_plugins(
    plugins: Sequence[str],
    *,
    quiet: bool = False,
) -> list[str]:
    """Run *ocx add* for each plugin. Returns list of failures."""
    if not _has_ocx() and not install_ocx(quiet=quiet):
        return list(plugins)

    failures: list[str] = []
    for plugin in plugins:
        result = subprocess.run(
            ["ocx", "add", plugin],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append(plugin)
    return failures


DEFAULT_PLUGINS: list[str] = [
    "kdco/background-agents",
    "felixAnhalt/opencode-worktree-session",
]
