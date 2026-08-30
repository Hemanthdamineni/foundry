"""Backward-compat re-export — canonical PhaseGraph lives in foundry.core.orchestrator.phase_graph."""
from foundry.core.orchestrator.phase_graph import PhaseGraph, PhaseGraphError

__all__ = ["PhaseGraph", "PhaseGraphError"]
