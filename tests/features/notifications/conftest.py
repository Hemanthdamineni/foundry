"""conftest for notification tests — adds src/ to sys.path and enables asyncio."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the Helix src/ tree is importable.
_src = str(Path(__file__).resolve().parents[3] / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def pytest_configure(config):
    """Enable asyncio mode for all tests in this package."""
    config.option.asyncio_mode = "auto"
