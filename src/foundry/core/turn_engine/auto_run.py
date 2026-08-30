"""auto_run -- the serve/orchestrate driver that completes a TurnEngine loop.

Feeds a generic async generate function into the TurnEngine loop, calling
``get_turn`` / ``submit_turn`` until the graph is exhausted or a maximum
turn count is reached.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from foundry.core.logging import get_logger
from foundry.core.store import StoreBackend
from foundry.core.turn_engine.engine import TurnEngine
from foundry.core.turn_engine.graph import RoleGraph

log = get_logger("foundry.auto_run")


class AutoRunError(Exception):
    """Raised when auto_run exceeds the turn limit."""


async def auto_run(
    store: StoreBackend,
    task_id: str,
    graph: RoleGraph,
    generate_fn: Callable[[str], Awaitable[str]],
    *,
    max_turns: int = 50,
    step_callback: Callable[[str, str], Awaitable[None]] | None = None,
    governance: Any | None = None,
    task_prompt: str = "",
) -> Any:
    """Drive a ``TurnEngine`` to completion using *generate_fn*.

    Works identically for phase execution, debate, and the agent loop --
    only the ``RoleGraph`` passed in differs.

    Parameters
    ----------
    store:
        Backend used for persisting task and turn-engine state.
    task_id:
        Task identifier the engine operates against.
    graph:
        A ``RoleGraph`` implementation (e.g. ``PhaseRoleGraph``,
        ``DebateGraph``, ``AgentLoopGraph``).
    generate_fn:
        Async callable that takes a prompt string and returns generated
        text.  This is where the LLM provider (or a test stub) is plugged in.
    max_turns:
        Maximum number of turns before raising ``AutoRunError``.
        Default 50 -- more than enough for any single run.
    step_callback:
        Optional async callback invoked after each turn with
        ``(role, output)``.  Useful for logging, streaming progress, or
        emitting events.
    governance:
        Optional ``GovernanceGate`` instance.  When provided, runs a
        governance check before each turn to determine execution intensity.
    task_prompt:
        The original task prompt (used by governance for capability routing).

    Returns
    -------
    Any
        The final result value from the terminal ``TurnPrompt``.

    Raises
    ------
    AutoRunError
        If *max_turns* is exceeded without reaching a terminal state.
    TurnEngineError
        If the store or graph encounters an invariant violation.
    """
    # Run governance check if provided
    governance_decision = None
    if governance and task_prompt:
        from foundry.core.workspace.manager import WorkspaceBoundaries
        governance_decision = governance.check(task_prompt)
        if not governance_decision.allowed:
            log.warning(
                "governance denied task %s: %s",
                task_id,
                governance_decision.deny_reason,
            )
            raise AutoRunError(
                f"Governance denied: {governance_decision.deny_reason}"
            )
        log.info(
            "governance check passed: rigor=%s, max_repairs=%d, use_debate=%s",
            governance_decision.rigor.value,
            governance_decision.max_repairs,
            governance_decision.use_debate,
        )

    engine = TurnEngine(graph, store, task_id)

    for _ in range(max_turns):
        turn = await engine.get_turn()

        if turn.done:
            return turn.result

        output = await generate_fn(turn.prompt)

        if step_callback is not None:
            await step_callback(turn.role, output)

        result = await engine.submit_turn(turn.role, output)

        if not result.accepted:
            msg = (
                f"Turn submission rejected for role '{turn.role}' "
                f"on task {task_id}: {result.error}"
            )
            raise AutoRunError(msg)

        # If submit_turn already advanced us to terminal, short-circuit
        if result.next_turn is not None and result.next_turn.done:
            return result.next_turn.result

    msg = (
        f"Auto-run exceeded max turns ({max_turns}) for task {task_id} "
        f"without reaching terminal state."
    )
    raise AutoRunError(msg)
