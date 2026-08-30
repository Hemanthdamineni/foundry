"""OrchestratorFSM — deterministic phase state machine."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdlc_phases.graph import PhaseGraph


class OrchestratorError(Exception):
    """Orchestrator-level error."""


class OrchestratorFSM:
    """Deterministic phase state machine.

    Answers only: what phase comes next, and is a given transition valid?
    """

    def __init__(self, graph: PhaseGraph) -> None:
        self._graph = graph

    @property
    def graph(self) -> PhaseGraph:
        return self._graph

    def submit(self, current_phase: str, target: str | None = None) -> str:
        """Determine the next phase.

        If *target* is given and valid, returns it.
        If there is exactly one outgoing transition, returns that.
        If there are two transitions and one is 'Done', returns the other.
        Otherwise raises OrchestratorError.
        """
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
        if len(next_phases) == 2 and "Done" in next_phases:
            return next_phases[0] if next_phases[0] != "Done" else next_phases[1]
        msg = f"Ambiguous transition from '{current_phase}': {next_phases}"
        raise OrchestratorError(msg)

    def can_submit(self, current_phase: str) -> bool:
        """Return True if the phase has at least one outgoing transition."""
        return (
            current_phase in self._graph.phases
            and bool(self._graph.possible_next(current_phase))
        )

    def is_terminal(self, phase: str) -> bool:
        """Return True if the phase is terminal (Done or no outgoing edges)."""
        return phase == "Done" or not self._graph.possible_next(phase)

    def is_valid_transition(self, from_phase: str, to_phase: str) -> bool:
        """Delegate to the underlying PhaseGraph."""
        return self._graph.is_valid_transition(from_phase, to_phase)
