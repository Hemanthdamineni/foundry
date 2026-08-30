"""Backward-compat shim: re-exports sdlc_phases as foundry.core.phases."""
import sys
from pathlib import Path
_HELIX = Path(__file__).resolve().parents[3]
_PKG_SRC = [str(_HELIX / "packages" / p / "src") for p in ("sdlc-models","sdlc-store","sdlc-phases","sdlc-judge","sdlc-debate","sdlc-mcp")]
for _p in _PKG_SRC:
    if _p not in sys.path:
        sys.path.insert(0, _p)
import sdlc_phases as _mod
# Make submodule resolution work: foundry.core.phases.contracts -> sdlc_phases.contracts
import importlib
for _name in _mod.__all__ if hasattr(_mod, '__all__') else []:
    globals()[_name] = getattr(_mod, _name)
sys.modules['foundry.core.phases'] = _mod
# Also import common submodules so they're registered
for _sub in ['graph', 'orchestrator', 'validator', 'checks', 'contracts']:
    try:
        importlib.import_module(f'sdlc_phases.{_sub}')
        sys.modules[f'foundry.core.phases.{_sub}'] = sys.modules[f'sdlc_phases.{_sub}']
    except ImportError:
        pass
