"""TurnEngine -- drives ANY role-based protocol forward one turn at a time.

Works identically for phase execution (wrapping ``PhaseGraph``), multi-agent
debate, and the planner/executor/verifier/repairer agent loop -- only the
``RoleGraph`` passed in differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from foundry.core.store import StoreBackend
from foundry.core.turn_engine.graph import RoleGraph, Terminal

# Namespace key stored inside the task's JSON blob to track turn-engine state.
_TE_KEY = "turn_engine"

# Key inside the context dict that a RoleGraph may populate during
# ``next_role`` to communicate graph-specific state that the TurnEngine
# should persist as part of the task's turn-engine metadata.
_TE_GRAPH_STATE_KEY = "_te_graph_state"


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #


@dataclass
class TurnPrompt:
    """The prompt describing what the current role should do."""

    role: str
    prompt: str
    context: dict[str, Any] = field(default_factory=dict)
    done: bool = False
    result: Any = None


@dataclass
class TurnResult:
    """Result of submitting a turn's output."""

    accepted: bool
    next_turn: TurnPrompt | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
#  TurnEngine
# --------------------------------------------------------------------------- #


class TurnEngineError(Exception):
    """Raised for invariant violations within the TurnEngine."""


class TurnEngine:
    """Drives a ``RoleGraph`` forward one turn at a time.

    **Idempotent ``get_turn``**
        Calling ``get_turn`` repeatedly without ``submit_turn`` returns the
        same prompt every time -- no side effects.

    **Exactly-once ``submit_turn``**
        Each call persists output and advances the graph.  A role mismatch
        guard prevents replaying or skipping roles.
    """

    def __init__(self, graph: RoleGraph, store: StoreBackend, task_id: str) -> None:
        self.graph = graph
        self.store = store
        self.task_id = task_id

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def get_turn(self) -> TurnPrompt:
        """Return the current role and its prompt/context.

        Idempotent -- safe to call repeatedly without side effects.  Reads
        state from the store but does not mutate anything.
        """
        task = await self._require_task()
        te_state = task.get(_TE_KEY, {})
        context = task.get("context", {})

        # Inject persisted graph state into context so RoleGraph
        # implementations (e.g. DebateGraph, AgentLoopGraph) can read
        # their own metadata from ``context[_TE_GRAPH_STATE_KEY]``.
        self._inject_graph_state(te_state, context)

        # Already complete?
        if te_state.get("complete"):
            return TurnPrompt(
                role="",
                prompt="",
                done=True,
                result=te_state.get("result"),
            )

        # Determine current role (lazy-first-run via initial_role)
        current_role: str
        stored_role = te_state.get("current_role")
        if stored_role is not None:
            current_role = stored_role
        else:
            current_role = self.graph.initial_role(context)

        # Build the prompt for this role
        prompt_text = self.graph.prompt_for(current_role, context)

        return TurnPrompt(
            role=current_role,
            prompt=prompt_text,
            context=context,
            done=False,
        )

    async def submit_turn(self, role: str, output: str) -> TurnResult:
        """Validate and persist output for *role*, then advance the graph.

        1. Verifies *role* matches the engine's expected current role.
        2. Persists the output to ``phase_history`` under a
           ``"turn_engine/<role>"`` phase key.
        3. Calls ``self.graph.next_role(...)`` to determine what comes next.
        4. If the graph is complete (``None`` or ``Terminal`` returned),
           marks the engine as finished and returns a ``TurnPrompt`` with
           ``done=True``.
        5. Otherwise, builds the next ``TurnPrompt`` and returns it.
        """
        task = await self._require_task()
        te_state = task.get(_TE_KEY, {})
        context = task.get("context", {})

        # Inject persisted graph state so the graph can read its metadata
        self._inject_graph_state(te_state, context)

        # -- Resolve expected role -------------------------------------------
        expected_role: str
        stored_role = te_state.get("current_role")
        if stored_role is not None:
            expected_role = stored_role
        else:
            expected_role = self.graph.initial_role(context)

        if role != expected_role:
            return TurnResult(
                accepted=False,
                error=(
                    f"Role mismatch: submitted '{role}' but the engine "
                    f"expects '{expected_role}' for task {self.task_id}"
                ),
            )

        # -- Persist output --------------------------------------------------
        history_entry: dict[str, Any] = {
            "role": role,
            "output": output,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self.store.save_phase_output(
            self.task_id,
            f"turn_engine/{role}",
            history_entry,
        )

        # -- Advance the graph -----------------------------------------------
        next_val = self.graph.next_role(expected_role, output, context)

        # Collect graph-specific state that the graph stored in the context
        # dict during ``next_role``.  The graph is responsible for setting
        # ``context[_TE_GRAPH_STATE_KEY]`` if it needs the TurnEngine to
        # persist extra metadata.
        graph_state = context.pop(_TE_GRAPH_STATE_KEY, None)

        # Treat both None and Terminal as "done"
        if next_val is None or next_val is Terminal:
            new_te: dict[str, Any] = {
                "complete": True,
                "result": output,
                "current_role": None,
            }
            if graph_state is not None:
                new_te["_graph_state"] = graph_state
            await self.store.update_task(self.task_id, {_TE_KEY: new_te})
            return TurnResult(
                accepted=True,
                next_turn=TurnPrompt(
                    role="",
                    prompt="",
                    done=True,
                    result=output,
                ),
            )

        next_role: str = next_val  # type: ignore[assignment]

        # Update stored state -- merge graph state if provided
        new_te = {
            "complete": False,
            "current_role": next_role,
        }
        if graph_state is not None:
            new_te["_graph_state"] = graph_state
        await self.store.update_task(self.task_id, {_TE_KEY: new_te})

        # Build next turn
        prompt_text = self.graph.prompt_for(next_role, context)
        next_turn = TurnPrompt(
            role=next_role,
            prompt=prompt_text,
            context=context,
            done=False,
        )

        return TurnResult(accepted=True, next_turn=next_turn)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    async def _require_task(self) -> dict[str, Any]:
        """Load the task or raise ``TurnEngineError``."""
        task = await self.store.get_task(self.task_id)
        if task is None:
            raise TurnEngineError(f"Task not found: {self.task_id}")
        return task

    @staticmethod
    def _inject_graph_state(
        te_state: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """Copy the persisted ``_graph_state`` into the context dict.

        The ``RoleGraph`` protocol receives the task's context dict.
        Graph implementations that persist metadata (e.g. debate round
        number, repair counter) store it under ``_TE_KEY["_graph_state"]``.
        This helper makes that state available as
        ``context[_TE_GRAPH_STATE_KEY]`` so that ``prompt_for`` and
        ``next_role`` can read it on every turn.
        """
        gs = te_state.get("_graph_state")
        if gs is not None:
            context[_TE_GRAPH_STATE_KEY] = gs
