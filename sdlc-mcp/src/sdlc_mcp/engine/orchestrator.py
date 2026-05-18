"""OrchestratorFSM — phase transitions only. Never sees budget, retry, or failure logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdlc_mcp.engine.execution_policy import ExecutionPolicy
    from sdlc_mcp.engine.phase_graph import PhaseGraph


class OrchestratorError(Exception):
    """Orchestrator-level error."""


class OrchestratorFSM:
    """Deterministic phase state machine. Answers only: what phase comes next?"""  # noqa: D400

    def __init__(self, graph: PhaseGraph, policy: ExecutionPolicy) -> None:
        self._graph = graph
        self._policy = policy

    @property
    def graph(self) -> PhaseGraph:
        return self._graph

    @property
    def policy(self) -> ExecutionPolicy:
        return self._policy

    def submit(self, current_phase: str, target: str | None = None) -> str:
        if current_phase not in self._graph.phases:
            msg = f"Unknown phase: {current_phase}"
            raise OrchestratorError(msg)
        next_phases = self._graph.possible_next(current_phase)
        if not next_phases:
            msg = f"Phase '{current_phase}' has no outgoing transitions"
            raise OrchestratorError(msg)
        if target:
            if target not in next_phases:
                msg = (
                    f"Target '{target}' not a valid transition from "
                    f"'{current_phase}': {next_phases}"
                )
                raise OrchestratorError(msg)
            return target
        if len(next_phases) == 1:
            return next_phases[0]
        if len(next_phases) == 2 and "Done" in next_phases:  # noqa: PLR2004
            return next_phases[0] if next_phases[0] != "Done" else next_phases[1]
        msg = f"Ambiguous transition from '{current_phase}': {next_phases}"
        raise OrchestratorError(msg)

    def can_submit(self, current_phase: str) -> bool:
        return (
            current_phase in self._graph.phases
            and bool(self._graph.possible_next(current_phase))
        )

    def is_terminal(self, phase: str) -> bool:
        return phase == "Done" or not self._graph.possible_next(phase)

    def is_valid_transition(self, from_phase: str, to_phase: str) -> bool:
        return self._graph.is_valid_transition(from_phase, to_phase)
