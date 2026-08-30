"""Transition validation against a phase graph contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc_phases.contracts import PhaseGraphContract


@dataclass(frozen=True)
class TransitionValidation:
    """Result of a transition validation check."""

    ok: bool
    reason: str = ""


class TransitionValidator:
    """Validates that a phase transition satisfies graph and gate constraints.

    Checks:
    1. The target phase is a valid outgoing edge from the current phase.
    2. All mandatory phases (required_completed) for the target are in the
       completed_phases set.
    3. The 'Done' phase is never a source of transitions.
    """

    def __init__(self, graph: PhaseGraphContract) -> None:
        self.graph = graph

    def validate(
        self,
        *,
        from_phase: str,
        to_phase: str,
        completed_phases: set[str] = field(default_factory=set),
    ) -> TransitionValidation:
        """Validate the transition and return a TransitionValidation result."""
        allowed = self.graph.allowed_next(from_phase)
        if to_phase not in allowed:
            return TransitionValidation(
                ok=False,
                reason=f"'{from_phase}' -> '{to_phase}' is not a valid transition",
            )

        required = set(self.graph.required_completed.get(to_phase, ()))
        missing = sorted(p for p in required if p not in completed_phases)
        if missing:
            return TransitionValidation(
                ok=False,
                reason=(
                    f"missing mandatory phases before '{to_phase}': "
                    f"{', '.join(missing)}"
                ),
            )

        if from_phase == "Done":
            return TransitionValidation(
                ok=False,
                reason="Done phase is terminal",
            )

        return TransitionValidation(ok=True, reason="ok")
