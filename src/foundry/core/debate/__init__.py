"""Re-exports of debate classes from the sdlc-debate package."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the packages/ tree is importable from the foundry/ tree.
_HELIX = Path(__file__).resolve().parents[3]
_PKG_SRC = [
    str(_HELIX / "packages" / p / "src")
    for p in ("sdlc-models", "sdlc-store", "sdlc-phases", "sdlc-judge", "sdlc-debate", "sdlc-mcp")
]
for _p in _PKG_SRC:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sdlc_debate.consensus import ConsensusEngine
from sdlc_debate.coordinator import DebateCoordinator

__all__ = [
    "ConsensusEngine",
    "DebateCoordinator",
]
