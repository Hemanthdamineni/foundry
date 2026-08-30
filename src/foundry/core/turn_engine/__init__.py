"""TurnEngine -- drive any role-based protocol forward one turn at a time.

This package provides the kernel abstraction for orchestrating role-based
workflows in a session-safe, idempotent manner.

Exports
-------
TurnEngine
    Drives a ``RoleGraph`` forward one turn at a time, persisting state
    through ``StoreBackend``.

TurnPrompt, TurnResult
    Data classes for the engine's input/output contract.

RoleGraph
    Protocol that any role-based graph must implement.

Terminal
    Sentinel for signalling graph completion.

PhaseRoleGraph
    Adapter wrapping ``PhaseGraph`` into a ``RoleGraph`` (each phase = a
    role, phase transitions = role transitions).

DebateGraph
    Turn-based multi-agent debate protocol
    (debater_a -> debater_b -> debater_c -> consensus [+ rounds]).

AgentLoopGraph
    Planner/executor/verifier/repairer agent loop with configurable
    repair cycles and prompt loading from ``.md`` files.

auto_run
    Driver function that feeds an LLM generate callback into a TurnEngine
    and runs it to completion.
"""

from __future__ import annotations

from foundry.core.turn_engine.agent_loop_graph import (  # noqa: F401
    AgentLoopGraph,
    AgentLoopState,
    run_agent_loop,
)
from foundry.core.turn_engine.auto_run import auto_run, AutoRunError
from foundry.core.turn_engine.debate_graph import DebateGraph
from foundry.core.turn_engine.engine import TurnEngine, TurnPrompt, TurnResult
from foundry.core.turn_engine.graph import RoleGraph, Terminal
from foundry.core.turn_engine.phase_graph import PhaseRoleGraph

__all__ = [
    "AgentLoopState",
    "DebateGraph",
    "PhaseRoleGraph",
    "RoleGraph",
    "Terminal",
    "TurnEngine",
    "TurnPrompt",
    "TurnResult",
    "AutoRunError",
    "auto_run",
    "run_agent_loop",
]
