"""
Backward-compat shim: re-exports everything from sdlc_models.

Consumers in features/sdlc_runtime (25+ modules) import from
``foundry.core.models``. This module forwards those imports to the
canonical ``sdlc_models`` package so they resolve without moving code.
"""

from __future__ import annotations

from sdlc_models.phases import *
from sdlc_models.judge import *
from sdlc_models.debate import *
from sdlc_models.schemas import *
from sdlc_models.config import *
from sdlc_models.exceptions import *

# Re-export __all__ from sdlc_models so that ``from foundry.core.models import *``
# and IDE tooling see the same public surface.
from sdlc_models import __all__ as _sdlc_all  # noqa: E402

__all__ = _sdlc_all
