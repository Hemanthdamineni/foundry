"""Re-export JudgeEngine from sdlc_judge."""

import sys
from pathlib import Path

_HELIX = Path(__file__).resolve().parents[3]
_PKG_SRC = [
    str(_HELIX / "packages" / p / "src")
    for p in ("sdlc-models", "sdlc-store", "sdlc-phases", "sdlc-judge", "sdlc-debate", "sdlc-mcp")
]
for _p in _PKG_SRC:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sdlc_judge.engine import JudgeEngine

__all__ = ["JudgeEngine"]
