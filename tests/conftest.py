"""Add the Helix source tree to sys.path so imports work from any CWD."""

from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_HELIX_ROOT = _THIS_DIR.parent

# Main source package
_SRC = _HELIX_ROOT / "src"

# Individual packages under packages/
_PKG_DIR = _HELIX_ROOT / "packages"
_PACKAGE_SRC_DIRS = sorted(
    p / "src" for p in _PKG_DIR.iterdir() if p.is_dir()
)

import sys

for _path in [_SRC, *_PACKAGE_SRC_DIRS]:
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
