"""AgentLoopGraph at `/home/zorro-omarchy/Desktop/Projects/Personal/00_Active/Helix/src/foundry/core/turn_engine/agent_loop_graph.py` (226 lines). Planner/executor/verifier/repairer loop. Flow: planner -> executor -> verifier -> DONE or repairer -> executor (loop). Loads prompts from `features/orchestrator/agents/*.md` files with sensible fallbacks. Configurable max_repairs (default 3). Verifier pass/fail detection via keyword heuristics. Repair count tracked via `_te_graph_state`."""

import os
import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_REPAIRS = 3
PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "features" / "orchestrator" / "agents"

# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

_PROMPT_CACHE: dict[str, str] = {}


def _load_prompt(name: str, fallback: str) -> str:
    """Load a prompt from ``PROMPT_DIR / f"{name}.md"``, caching the result.

    If the file does not exist or an error occurs, *fallback* is returned.
    """
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]

    path = PROMPT_DIR / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
        _PROMPT_CACHE[name] = text
        return text
    except (FileNotFoundError, OSError) as exc:
        logger.warning("Prompt file %s not found (%s); using fallback.", path, exc)
        return fallback


def _clear_prompt_cache() -> None:
    """Utility for tests -- clear the module-level prompt cache."""
    _PROMPT_CACHE.clear()


# ---------------------------------------------------------------------------
# Heuristic verifier
# ---------------------------------------------------------------------------

_PASS_KEYWORDS = (":white_check_mark:", "pass", "ok", "verified", "success")
_FAIL_KEYWORDS = (":x:", "fail", "error", "reject", "invalid")


def _verdict_from_text(text: str) -> bool:
    """Return ``True`` for pass, ``False`` for fail based on keyword heuristics.

    The check is case-insensitive.  ``_FAIL_KEYWORDS`` are tested first so that
    a message containing both "pass" and "fail" is classified as a failure.
    """
    lower = text.lower()
    for kw in _FAIL_KEYWORDS:
        if kw in lower:
            return False
    for kw in _PASS_KEYWORDS:
        if kw in lower:
            return True
    return False  # default: fail closed


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

@dataclass
class AgentLoopState:
    """Mutable state threaded through the agent loop graph."""
    planner_output: str = ""
    executor_output: str = ""
    verifier_output: str = ""
    repair_count: int = 0
    max_repairs: int = DEFAULT_MAX_REPAIRS
    done: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

AgentFn = Callable[[AgentLoopState], AgentLoopState]
"""Signature for any graph node: receives state, returns (possibly mutated) state."""


def planner_node(text_gen: Callable[[str], str]) -> AgentFn:
    """Return a node that calls *text_gen* with the planner prompt."""
    def _node(state: AgentLoopState) -> AgentLoopState:
        prompt = _load_prompt("planner", "You are a planning agent.")
        raw = text_gen(prompt + "\n\n" + state.metadata.get("task", ""))
        state.planner_output = raw
        return state
    return _node


def executor_node(text_gen: Callable[[str], str]) -> AgentFn:
    """Return a node that calls *text_gen* with the planner output."""
    def _node(state: AgentLoopState) -> AgentLoopState:
        prompt = _load_prompt("executor", "You are an execution agent.")
        raw = text_gen(prompt + "\n\n## Plan\n\n" + state.planner_output)
        state.executor_output = raw
        return state
    return _node


def verifier_node(text_gen: Callable[[str], str]) -> AgentFn:
    """Return a node that calls *text_gen* and then classifies pass/fail."""
    def _node(state: AgentLoopState) -> AgentLoopState:
        prompt = _load_prompt("verifier", "You are a verification agent.")
        raw = text_gen(prompt + "\n\n## Output\n\n" + state.executor_output)
        state.verifier_output = raw
        state.done = _verdict_from_text(raw)
        return state
    return _node


def repairer_node(text_gen: Callable[[str], str]) -> AgentFn:
    """Return a node that generates a repair prompt and increments the counter."""
    def _node(state: AgentLoopState) -> AgentLoopState:
        prompt = _load_prompt("repairer", "You are a repair agent.")
        raw = text_gen(
            prompt
            + "\n\n## Plan\n\n"
            + state.planner_output
            + "\n\n## Previous Output\n\n"
            + state.executor_output
            + "\n\n## Verifier Feedback\n\n"
            + state.verifier_output
        )
        state.executor_output = raw  # repair becomes the new executor output
        state.repair_count += 1
        return state
    return _node


# ---------------------------------------------------------------------------
# Graph runner
# ---------------------------------------------------------------------------

def run_agent_loop(
    text_gen: Callable[[str], str],
    *,
    task: str = "",
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    metadata: Optional[dict[str, Any]] = None,
) -> AgentLoopState:
    """Execute the full planner -> executor -> verifier [-> repairer -> executor] loop.

    Parameters
    ----------
    text_gen:
        A callable that accepts a prompt string and returns the model response.
    task:
        The initial task description passed into the planner.
    max_repairs:
        Maximum number of repair cycles before forcing termination.
    metadata:
        Additional key-value pairs attached to ``state.metadata``.

    Returns
    -------
    AgentLoopState
        The final state after the loop terminates (either verified or
        repair-limit exhausted).
    """
    state = AgentLoopState(max_repairs=max_repairs)
    if metadata:
        state.metadata.update(metadata)
    state.metadata["task"] = task

    planner = planner_node(text_gen)
    executor = executor_node(text_gen)
    verifier = verifier_node(text_gen)
    repairer = repairer_node(text_gen)

    # ---- planner ----
    state = planner(state)

    # ---- executor ----
    state = executor(state)

    while True:
        # ---- verifier ----
        state = verifier(state)

        if state.done:
            logger.info("Verification passed after %d repair(s).", state.repair_count)
            break

        if state.repair_count >= state.max_repairs:
            logger.warning(
                "Repair limit (%d) reached; terminating with failure.",
                state.max_repairs,
            )
            state.done = True  # mark as done (failure) so callers can inspect
            break

        # ---- repairer (feeds back into executor) ----
        state = repairer(state)

        # ---- executor (re-run with repair context) ----
        state = executor(state)
        # loop back to verifier

    return state


# ---------------------------------------------------------------------------
# Convenience: synchronous text generator for testing / simple usage
# ---------------------------------------------------------------------------

def _dummy_text_gen(prompt: str) -> str:
    """A no-op text generator that echoes the prompt length for smoke tests."""
    return f"dummy response (prompt length: {len(prompt)})"


# ---------------------------------------------------------------------------
# RoleGraph adapter — AgentLoopGraph class
# ---------------------------------------------------------------------------


class AgentLoopGraph:
    """RoleGraph-compatible adapter for the agent loop (planner → executor → verifier → repairer).

    Wraps ``run_agent_loop`` in a turn-based protocol compatible with
    ``TurnEngine`` and ``auto_run``.
    """

    ROLES = ("planner", "executor", "verifier", "repairer")

    def __init__(
        self,
        max_repairs: int = DEFAULT_MAX_REPAIRS,
    ) -> None:
        self._max_repairs = max_repairs

    def initial_role(self, context: dict[str, Any]) -> str:
        return "planner"

    def prompt_for(self, role: str, context: dict[str, Any]) -> str:
        task_prompt = context.get("task", context.get("prompt", ""))
        plan = context.get("plan", "")
        history = context.get("history", "")

        rich_prompts = {
            "planner": (
                "You are a planning agent. Analyze the task below and produce a "
                "detailed plan with specific steps. Return your plan as plain text "
                "with clear numbered steps.\n\n"
                f"Task: {task_prompt}"
            ),
            "executor": (
                "You are an execution agent. Follow the plan below and implement "
                "each step. Write complete, production-quality code.\n\n"
                f"Plan: {plan}\n\n"
                f"Task: {task_prompt}"
            ),
            "verifier": (
                "You are a verification agent. Review the implementation below for "
                "correctness, edge cases, and code quality. Reply with a line "
                "containing ':white_check_mark:' if it passes or ':x:' if it fails, "
                "followed by your detailed review.\n\n"
                f"Implementation: {history}"
            ),
            "repairer": (
                "You are a repair agent. Fix the issues identified by the verifier. "
                "Return the corrected implementation.\n\n"
                f"Plan: {plan}\n\n"
                f"Previous implementation: {history}"
            ),
        }

        # If context has task content, use the rich prompts; otherwise fall back
        # to static prompts from .md files or simple defaults.
        if task_prompt:
            base = rich_prompts.get(role, f"You are a {role} agent.")
            if role not in ("planner",) and task_prompt:
                return base + f"\n\nOriginal task: {task_prompt}"
            return base

        fallbacks = {
            "planner": "You are a planning agent. Design an implementation plan.",
            "executor": "You are an execution agent. Implement the plan.",
            "verifier": "You are a verification agent. Verify the implementation.",
            "repairer": "You are a repair agent. Fix the issues found by the verifier.",
        }
        return _load_prompt(role, fallbacks.get(role, f"You are a {role} agent."))

    def next_role(
        self,
        current_role: str,
        output: str,
        context: dict[str, Any],
    ) -> str | None:
        match current_role:
            case "planner":
                return "executor"
            case "executor":
                return "verifier"
            case "verifier":
                if _verdict_from_text(output):
                    return None  # DONE — passed
                repair_count = context.get("repair_count", 0)
                if repair_count >= self._max_repairs:
                    return None  # DONE — max repairs exhausted
                context["repair_count"] = repair_count + 1
                return "repairer"
            case "repairer":
                return "executor"
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "AgentLoopGraph",
    "AgentLoopState",
    "AgentFn",
    "agent_loop_graph",
    "planner_node",
    "executor_node",
    "verifier_node",
    "repairer_node",
    "run_agent_loop",
    "DEFAULT_MAX_REPAIRS",
    "PROMPT_DIR",
]
