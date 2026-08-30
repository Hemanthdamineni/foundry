"""DebateGraph -- turn-based debate protocol.

Roles
    ``debater_a``, ``debater_b``, ``debater_c``, ``consensus``

Flow
    1. Each debater receives the artefact under review plus their persona
       prompt and submits an evaluation.
    2. After all three debaters have submitted, the ``consensus`` role
       aggregates their evaluations.
    3. If consensus passes, the graph is terminal.
    4. If consensus does not pass, a new round begins (max rounds is
       configurable; default 1).

State is persisted through the ``StoreBackend``, not kept in memory, so the
engine can be resumed after interruption.
"""

from __future__ import annotations

from typing import Any

from foundry.core.store import StoreBackend
from foundry.core.turn_engine.graph import RoleGraph, Terminal

_DEBATER_ROLES = ("debater_a", "debater_b", "debater_c")
_CONSENSUS_ROLE = "consensus"
_ALL_ROLES = (*_DEBATER_ROLES, _CONSENSUS_ROLE)

# Key used to communicate graph-specific state to the TurnEngine for
# persistence across turns.  The TurnEngine pops this key from the context
# dict after ``next_role`` and stores its value inside the task's
# ``turn_engine._graph_state`` blob.
_TE_GRAPH_STATE_KEY = "_te_graph_state"


class DebateGraph:
    """Turn-based debate protocol.

    Parameters
    ----------
    store:
        Store backend used to persist and retrieve debate round state.
    task_id:
        Task under debate.
    max_rounds:
        Maximum debate rounds before forced termination.  Each round is
        4 roles (3 debaters + 1 consensus).
    artefact:
        The content being debated (e.g. a code diff, design document).
    persona_prompts:
        Optional custom persona prompts keyed by role.  Falls back to
        built-in defaults for any role not provided.
    """

    def __init__(
        self,
        store: StoreBackend,
        task_id: str,
        *,
        max_rounds: int = 1,
        artefact: str = "",
        persona_prompts: dict[str, str] | None = None,
    ) -> None:
        self._store = store
        self._task_id = task_id
        self._max_rounds = max_rounds
        self._artefact = artefact

        # Merge custom prompts over sensible defaults
        custom = persona_prompts or {}
        self._prompts: dict[str, str] = {
            "debater_a": custom.get(
                "debater_a",
                _DEFAULT_DEBATER_A_PROMPT,
            ),
            "debater_b": custom.get(
                "debater_b",
                _DEFAULT_DEBATER_B_PROMPT,
            ),
            "debater_c": custom.get(
                "debater_c",
                _DEFAULT_DEBATER_C_PROMPT,
            ),
            "consensus": custom.get(
                "consensus",
                _DEFAULT_CONSENSUS_PROMPT,
            ),
        }

    # -- RoleGraph protocol --------------------------------------------------

    def initial_role(self, context: dict[str, Any]) -> str:  # noqa: ARG002
        """Return ``debater_a`` as the first role in round 1."""
        return "debater_a"

    def prompt_for(self, role: str, context: dict[str, Any]) -> str:
        """Return the persona prompt for *role*, appended with context."""
        artefact = context.get("artefact", self._artefact)
        round_num = self._current_round_number(context)
        base = self._prompts.get(role, "Review the provided artefact.")

        lines = [
            base,
            "",
            f"Round {round_num} of {self._max_rounds}",
        ]
        if artefact:
            lines.append("")
            lines.append("--- Artefact under review ---")
            lines.append(artefact)

        # Include previous round outputs for debaters in round 2+
        if role in _DEBATER_ROLES and round_num > 1:
            prior = self._previous_round_outputs(context)
            if prior:
                lines.append("")
                lines.append("--- Previous round output ---")
                lines.append(prior)

        return "\n".join(lines)

    def next_role(
        self,
        current_role: str,
        output: str,  # noqa: ARG002
        context: dict[str, Any],
    ) -> str | None | type[Terminal]:
        """Advance to the next debater, transition to consensus, or end."""
        round_num = self._current_round_number(context)

        # Advance within the current round
        if current_role in ("debater_a", "debater_b"):
            next_idx = _DEBATER_ROLES.index(current_role) + 1
            return _DEBATER_ROLES[next_idx]

        # debater_c -> consensus
        if current_role == "debater_c":
            return _CONSENSUS_ROLE

        # consensus -> check if another round is needed
        if current_role == _CONSENSUS_ROLE:
            if round_num < self._max_rounds:
                # Start a new round
                self._increment_round(context)
                return "debater_a"
            return None  # terminal

        # Unknown role -- fail safe
        return None

    # -- Internal helpers ---------------------------------------------------

    def _current_round_number(self, context: dict[str, Any]) -> int:
        """Read the current round number from the graph-state blob.

        The TurnEngine persists this blob inside the task's ``turn_engine``
        metadata after each ``next_role`` call, making round tracking
        interruption-safe.
        """
        gs = context.get(_TE_GRAPH_STATE_KEY) or {}
        raw = gs.get("debate_round", 1)
        return raw if isinstance(raw, int) and raw >= 1 else 1

    def _increment_round(self, context: dict[str, Any]) -> None:
        """Increment the debate round counter.

        Writes into ``context[_TE_GRAPH_STATE_KEY]`` which the TurnEngine
        picks up and persists after ``next_role`` returns.
        """
        gs = context.setdefault(_TE_GRAPH_STATE_KEY, {})
        if not gs:
            gs = context[_TE_GRAPH_STATE_KEY] = {}
        current = gs.get("debate_round", 1)
        gs["debate_round"] = current + 1

    def _previous_round_outputs(self, context: dict[str, Any]) -> str:
        """Aggregate all debater outputs from the previous round."""
        round_num = self._current_round_number(context)
        if round_num <= 1:
            return ""
        # In a real implementation this would query phase_history for
        # ``turn_engine/<role>`` entries; the context here is best-effort.
        history = context.get("_debate_history", {})
        lines: list[str] = []
        for role in _DEBATER_ROLES:
            prev = history.get(role, "")
            if prev:
                lines.append(f"--- {role} (round {round_num - 1}) ---")
                lines.append(prev if len(prev) <= 2000 else prev[:2000] + "...")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Default persona prompts
# --------------------------------------------------------------------------- #

_DEFAULT_DEBATER_A_PROMPT = (
    "You are Debater A, a thorough code reviewer focused on correctness.\n"
    "Analyse the artefact below for:\n"
    "1. Logic errors and edge cases\n"
    "2. Type safety and API contract violations\n"
    "3. Concurrency or resource-handling issues\n"
    "State your verdict clearly (PASS / FAIL) and list specific issues."
)

_DEFAULT_DEBATER_B_PROMPT = (
    "You are Debater B, focused on design and maintainability.\n"
    "Analyse the artefact below for:\n"
    "1. Architectural consistency\n"
    "2. Abstraction appropriateness (not over- nor under-engineered)\n"
    "3. Naming, structure, and readability\n"
    "State your verdict clearly (PASS / FAIL) and list specific concerns."
)

_DEFAULT_DEBATER_C_PROMPT = (
    "You are Debater C, focused on test coverage and safety.\n"
    "Analyse the artefact below for:\n"
    "1. Test coverage (unit, integration, edge cases)\n"
    "2. Error-handling and failure modes\n"
    "3. Regression risk\n"
    "State your verdict clearly (PASS / FAIL) and list test gaps."
)

_DEFAULT_CONSENSUS_PROMPT = (
    "You are the neutral Consensus Judge.\n"
    "Review the three debater evaluations above and decide:\n"
    "1. Is there genuine consensus or sycophantic agreement?\n"
    "2. What are the key disagreement areas?\n"
    "3. Is the artefact ready to proceed?\n\n"
    "Return a JSON object with keys:\n"
    '- "passed" (bool): overall verdict\n'
    '- "reason" (str): justification\n'
    '- "disagreement_areas" (list of str): issues still unresolved\n'
    '- "minority_positions" (list of dict): {{"agent": str, "position": str}}\n'
    '- "sycophancy_risk" (str): "none" | "low" | "medium" | "high"'
)
