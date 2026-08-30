"""sdlc-debate: Multi-agent debate protocol for SDLC task validation.

Provides:
- ConsensusEngine — pure-logic consensus, minority reports, collapse detection
- DebateRuntime — orchestration of the 3-round debate protocol
- DebateCoordinator — wraps runtime with Ai-Agent-Server personality configs
"""

from __future__ import annotations

from sdlc_debate.consensus import ConsensusEngine
from sdlc_debate.coordinator import DebateCoordinator, DebateResult
from sdlc_debate.runtime import DebateRuntime

__all__ = [
    "ConsensusEngine",
    "DebateRuntime",
    "DebateCoordinator",
    "DebateResult",
]
