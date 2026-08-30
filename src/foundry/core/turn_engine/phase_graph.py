"""PhaseRoleGraph -- adapter from existing ``PhaseGraph`` to ``RoleGraph``.

Each phase is treated as a role.  The graph of valid phase transitions defines
the role-transition logic.
"""

from __future__ import annotations

from typing import Any

from foundry.core.turn_engine.graph import RoleGraph, Terminal

try:
    from foundry.core.orchestrator.phase_graph import PhaseGraph
except ImportError:  # pragma: no cover -- fallback for sdlc_runtime layout
    from foundry.features.sdlc_runtime.engine.phase_graph import (  # type: ignore[no-redef]
        PhaseGraph,
    )


class PhaseRoleGraph:
    """Adapter: wraps a ``PhaseGraph`` instance into a ``RoleGraph``.

    Every phase in the graph is a distinct role.  Transitions are determined
    by the phase graph's adjacency.  The ``"Done"`` phase is treated as
    terminal.
    """

    def __init__(self, phase_graph: PhaseGraph) -> None:
        if not isinstance(phase_graph, PhaseGraph):
            raise TypeError(f"Expected PhaseGraph, got {type(phase_graph).__name__}")
        self._pg = phase_graph

    # -- RoleGraph protocol --------------------------------------------------

    def initial_role(self, context: dict[str, Any]) -> str:  # noqa: ARG002
        """Return the first phase in the graph as the initial role.

        The *context* parameter is accepted for protocol conformance but is
        not used -- the initial phase is always the first phase in the graph.
        """
        return self._pg.phases[0]

    def prompt_for(self, role: str, context: dict[str, Any]) -> str:
        """Return a default prompt directing the LLM to execute *role*.

        Subclasses may override this to load phase-specific prompts from
        templates or agent files.
        """
        description = context.get("description", "")
        if description:
            return (
                f"Execute the {role} phase for the current task.\n\n"
                f"Task description: {description}"
            )
        return f"Execute the {role} phase for the current task."

    def next_role(
        self,
        current_role: str,
        output: str,  # noqa: ARG002
        context: dict[str, Any],  # noqa: ARG002
    ) -> str | None | type[Terminal]:
        """Determine the next phase following *current_role*.

        Delegates to ``PhaseGraph.possible_next()``.  If ``"Done"`` is the
        only transition available, or no transition exists, the graph is
        considered terminal.
        """
        # PhaseGraph uses "phase" terminology internally
        possible = self._pg.possible_next(current_role)

        if not possible:
            return None

        # If "Done" is an option, prefer the non-Done alternative when
        # there are exactly two choices (matching OrchestratorFSM.submit).
        if "Done" in possible and len(possible) > 1:
            non_done = [p for p in possible if p != "Done"]
            return non_done[0]

        # Exactly one target
        if len(possible) == 1:
            target = possible[0]
            return None if target == "Done" else target

        # Multiple non-Done targets -- ambiguous; fall back to first.
        return possible[0]

    # -- Convenience access -------------------------------------------------

    @property
    def phase_graph(self) -> PhaseGraph:
        """Return the underlying ``PhaseGraph`` instance."""
        return self._pg
