"""foundry orchestrate — autonomous SDLC workflow execution.

Uses the TurnEngine from foundry.core.turn_engine for phase graph traversal,
with SqliteStore for persistence and PhaseRoleGraph for role-based transitions.

Three execution modes:
  - Template:     static template outputs per phase (no LLM, no interactive)
  - Interactive:  reads phase output from stdin
  - LLM:          auto_run with a simple Ollama generate function
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from foundry.core.logging import bootstrap_logging, get_logger
from foundry.core.store import SqliteStore
from foundry.core.orchestrator.phase_graph import PhaseGraph
from foundry.core.turn_engine import (
    PhaseRoleGraph,
    TurnEngine,
    auto_run,
)

log = get_logger("cli.orchestrate")

_PHASE_DESCRIPTIONS: dict[str, str] = {
    "Chatting": "Initial requirements gathering and context discovery",
    "Specs": "Formal specification with requirements, scope, and constraints",
    "Planning": "Implementation plan with file changes and risk assessment",
    "Coding": "Implementation of the planned changes",
    "Review": "Review and quality assessment of the implementation",
    "Done": "Task completed",
}

# Template outputs used when no LLM provider or interactive input is available
_TEMPLATE_OUTPUTS: dict[str, str] = {
    "Chatting": (
        "## Scope\n"
        "Analysis of the task description and initial requirements.\n"
        "\n"
        "## Questions\n"
        "- What is the core functionality being implemented?\n"
        "- What are the key constraints and non-goals?\n"
        "- What existing code or patterns should be followed?\n"
        "\n"
        "## Constraints\n"
        "- Follow existing code style and conventions\n"
        "- Maintain backward compatibility where possible\n"
    ),
    "Specs": (
        "## Requirements\n"
        "- Feature must match the described behavior\n"
        "- Code must compile without errors\n"
        "- All existing tests must continue to pass\n"
        "\n"
        "## Scope\n"
        "- Implementation limited to the described change\n"
        "- No scope creep beyond what is specified\n"
        "\n"
        "## Constraints\n"
        "- Use the same language and frameworks as the existing codebase\n"
        "- Keep changes minimal and focused\n"
    ),
    "Planning": (
        "## Implementation Plan\n"
        "1. Understand the existing code structure\n"
        "2. Implement the required changes\n"
        "3. Verify the changes work correctly\n"
        "\n"
        "## File Changes\n"
        "- Files will be determined during implementation\n"
        "\n"
        "## Risks\n"
        "- Minimal risk given the scope of the change\n"
    ),
    "Coding": (
        "## Files Modified\n"
        "Changes applied to the workspace according to the plan.\n"
        "\n"
        "## Status\n"
        "ok\n"
        "Implementation complete.\n"
    ),
    "Review": (
        "## Issues Found\n"
        "No issues found during review. All criteria met.\n"
        "\n"
        "## Severity\n"
        "none\n"
        "\n"
        "## Verdict\n"
        "approved — ready to proceed to Done\n"
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an autonomous SDLC workflow",
    )
    parser.add_argument(
        "workflow",
        nargs="?",
        default="default",
        help="Workflow name (unused, kept for backward compat)",
    )
    parser.add_argument(
        "--description",
        "-d",
        required=True,
        help="Task description — what should be done",
    )
    parser.add_argument(
        "--mode",
        "-m",
        default="feature",
        choices=["feature", "bugfix", "refactor", "research", "docs"],
        help="Workflow mode (default: feature)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Prompt for phase output interactively",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Attempt LLM-based execution (requires Ollama or configured provider)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=8,
        help="Maximum review iterations before forcing completion",
    )
    parser.add_argument(
        "--config-dir",
        default="config",
        help="Path to config directory (default: config/)",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Path to the workspace (default: current directory)",
    )
    return parser


def main(args: list[str] | None = None) -> None:
    """Entry point — parse args and run the async workflow loop."""
    parser = _build_parser()
    parsed = parser.parse_args(args)

    # Bootstrap logging early
    bootstrap_logging(level="INFO", json_format=False)

    print("\n═══ Foundry Orchestrate ═══")
    print(f"  Task:      {parsed.description}")
    print(f"  Mode:      {parsed.mode}")
    print(f"  Interactive: {parsed.interactive}")
    print(f"  LLM:       {parsed.llm}")
    print(f"  Workspace: {parsed.workspace}")
    print(f"  Config:    {parsed.config_dir}\n")

    try:
        asyncio.run(
            _run_workflow(
                description=parsed.description,
                mode=parsed.mode,
                interactive=parsed.interactive,
                use_llm=parsed.llm,
                max_iterations=parsed.max_iterations,
                config_dir=Path(parsed.config_dir),
                workspace=Path(parsed.workspace),
            ),
        )
    except KeyboardInterrupt:
        print("\nWorkflow interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nWorkflow failed: {exc}")
        log.exception("Workflow execution failed")
        sys.exit(1)


async def _run_workflow(  # noqa: PLR0913
    *,
    description: str,
    mode: str = "feature",
    interactive: bool = False,
    use_llm: bool = False,
    max_iterations: int = 8,
    config_dir: Path = Path("config"),
    workspace: Path = Path("."),
) -> None:
    """Core workflow execution — uses TurnEngine to drive the phase loop."""
    # ── 1. Load PhaseGraph from config or use built-in default ─────────
    phase_graph_file = config_dir / "phase_graph.yaml"
    if phase_graph_file.exists():
        import yaml
        with phase_graph_file.open() as f:
            graph_data = yaml.safe_load(f) or {}
        if "phases" in graph_data and isinstance(graph_data["phases"], dict):
            # Translate dict format (Chatting: [Done, Specs]) to list format
            phases_list: list[str] = []
            transitions_list: list[dict[str, str]] = []
            for from_phase, to_phases in graph_data["phases"].items():
                phases_list.append(from_phase)
                if isinstance(to_phases, list):
                    for to_phase in to_phases:
                        transitions_list.append({"from": from_phase, "to": to_phase})
            graph_data = {"phases": phases_list, "transitions": transitions_list}
        pg = PhaseGraph(graph_data)
        print(f"  Using phase graph from: {phase_graph_file}")
    else:
        # Built-in default phase graph
        pg = PhaseGraph({
            "phases": ["Chatting", "Specs", "Planning", "Coding", "Review", "Done"],
            "transitions": [
                {"from": "Chatting", "to": "Done"},
                {"from": "Chatting", "to": "Specs"},
                {"from": "Specs", "to": "Planning"},
                {"from": "Planning", "to": "Coding"},
                {"from": "Coding", "to": "Review"},
                {"from": "Review", "to": "Coding"},
                {"from": "Review", "to": "Done"},
            ],
        })
        print("  Using built-in phase graph (config/phase_graph.yaml not found)")

    prg = PhaseRoleGraph(pg)

    # ── 2. Initialise store ───────────────────────────────
    store = SqliteStore(workspace / ".foundry" / "sdlc.db")
    await store.initialize()

    # ── 3. Create task ─────────────────────────────────
    task_id = f"wf_{uuid.uuid4().hex[:12]}"
    task_payload: dict[str, Any] = {
        "task_id": task_id,
        "description": description,
        "mode": mode,
        "status": "running",
        "current_phase": "Chatting",
        "history": [],
        "iteration_count": 0,
        "retry_count": 0,
        "locked_prompts": {},
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await store.create_task(task_payload)

    print(f"  Task ID:   {task_id}")
    print(f"  Created:   {task_payload['created_at']}\n")

    context: dict[str, Any] = {
        "description": description,
        "mode": mode,
    }

    # ── 4. Execute ───────────────────────────────────
    start_time = time.monotonic()

    print("╔═════════════════════════════════════════════╗")
    print("║          Phase Execution Loop                ║")
    print("╚═════════════════════════════════════════════╝\n")

    if use_llm:
        await _run_llm_workflow(
            store=store,
            task_id=task_id,
            phase_role_graph=prg,
            context=context,
            max_iterations=max_iterations,
        )
    elif interactive:
        await _run_interactive_workflow(
            store=store,
            task_id=task_id,
            phase_role_graph=prg,
            context=context,
            max_iterations=max_iterations,
        )
    else:
        await _run_template_workflow(
            store=store,
            task_id=task_id,
            phase_role_graph=prg,
            context=context,
            max_iterations=max_iterations,
        )

    # Mark task as done in store
    await store.update_task(task_id, {"status": "done"})

    # ── 5. Summary ───────────────────────────────────
    elapsed = time.monotonic() - start_time
    print("╔═════════════════════════════════════════════╗")
    print("║          Workflow Complete                    ║")
    print("╚═════════════════════════════════════════════╝\n")
    print(f"  Task:      {description}")
    print(f"  Task ID:   {task_id}")
    print(f"  Mode:      {mode}")
    print(f"  Duration:  {elapsed:.1f}s")
    print(f"  Status:    done\n")

    # ── 6. Cleanup ──────────────────────────────────
    await store.checkpoint()
    await store.close()


# --------------------------------------------------------------------------- #
#  Template mode
# --------------------------------------------------------------------------- #


async def _run_template_workflow(
    *,
    store: SqliteStore,
    task_id: str,
    phase_role_graph: PhaseRoleGraph,
    context: dict[str, Any],
    max_iterations: int,
) -> None:
    """Run workflow using static template outputs for each phase."""
    engine = TurnEngine(phase_role_graph, store, task_id)
    iteration = 0
    review_cycles = 0

    while True:
        turn = await engine.get_turn()
        if turn.done:
            break

        iteration += 1
        role = turn.role
        phase_info = _PHASE_DESCRIPTIONS.get(role, "")

        print(f"─── [{iteration}] {role} ───")
        if phase_info:
            print(f"    {phase_info}")

        output = _TEMPLATE_OUTPUTS.get(
            role,
            f"## {role} Output\nTask: {context.get('description', '')}\n",
        )
        print("    Using template output (use --interactive or --llm for dynamic)\n")
        print(f"    Output preview: {output[:120].strip()!r}...\n")

        # Enforce max review cycles
        if role == "Review":
            review_cycles += 1
            if review_cycles >= max_iterations:
                print(
                    f"  ⚠ Max review cycles ({max_iterations}) reached"
                    " — forcing completion",
                )
                output = (
                    "## Issues Found\nNone.\n\n"
                    "## Verdict\napproved — ready to proceed to Done"
                )

        result = await engine.submit_turn(role, output)
        if not result.accepted:
            print(f"  ⚠ Turn rejected: {result.error}")
            break

        next_role = result.next_turn.role if result.next_turn else ""
        print(f"  → {role} → {next_role}\n")

        if result.next_turn is not None and result.next_turn.done:
            break


# --------------------------------------------------------------------------- #
#  Interactive mode
# --------------------------------------------------------------------------- #


async def _run_interactive_workflow(
    *,
    store: SqliteStore,
    task_id: str,
    phase_role_graph: PhaseRoleGraph,
    context: dict[str, Any],
    max_iterations: int,
) -> None:
    """Run workflow reading phase output interactively from stdin."""
    engine = TurnEngine(phase_role_graph, store, task_id)
    iteration = 0
    review_cycles = 0

    while True:
        turn = await engine.get_turn()
        if turn.done:
            break

        iteration += 1
        role = turn.role
        phase_info = _PHASE_DESCRIPTIONS.get(role, "")

        print(f"─── [{iteration}] {role} ───")
        if phase_info:
            print(f"    {phase_info}")

        output = _read_interactive_input(role)
        print(f"    Output preview: {output[:120].strip()!r}...\n")

        # Enforce max review cycles
        if role == "Review":
            review_cycles += 1
            if review_cycles >= max_iterations:
                print(
                    f"  ⚠ Max review cycles ({max_iterations}) reached"
                    " — forcing completion",
                )
                output = (
                    "## Issues Found\nNone.\n\n"
                    "## Verdict\napproved — ready to proceed to Done"
                )

        result = await engine.submit_turn(role, output)
        if not result.accepted:
            print(f"  ⚠ Turn rejected: {result.error}")
            break

        next_role = result.next_turn.role if result.next_turn else ""
        print(f"  → {role} → {next_role}\n")

        if result.next_turn is not None and result.next_turn.done:
            break


# --------------------------------------------------------------------------- #
#  LLM mode
# --------------------------------------------------------------------------- #


async def _run_llm_workflow(
    *,
    store: SqliteStore,
    task_id: str,
    phase_role_graph: PhaseRoleGraph,
    context: dict[str, Any],
    max_iterations: int,
) -> None:
    """Run workflow using auto_run with a simple LLM generate function.

    The generate function calls an Ollama-compatible API endpoint to produce
    phase output.  auto_run drives the TurnEngine loop until the graph is
    exhausted or max_turns is exceeded.
    """
    iteration_count: list[int] = [0]  # mutable for closure

    async def generate_fn(prompt: str) -> str:
        """Simple LLM generate using an Ollama-compatible API."""
        payload = {
            "model": "qwen3:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:11434/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "").strip()
                    log.warning("Ollama returned status %s", resp.status)
                    return ""
        except ImportError:
            log.error("aiohttp is required for LLM mode")
            return ""
        except Exception as exc:
            log.warning("LLM generate failed: %s", exc)
            return ""

    async def step_callback(role: str, output: str) -> None:
        """Log each turn for the CLI output."""
        iteration_count[0] += 1
        phase_info = _PHASE_DESCRIPTIONS.get(role, "")
        print(f"─── [{iteration_count[0]}] {role} ───")
        if phase_info:
            print(f"    {phase_info}")
        print(f"    Output preview: {output[:120].strip()!r}...\n")

    # Compute an upper bound on turns: at most (phases * max_iterations)
    num_phases = len(phase_role_graph.phase_graph.phases)
    max_turns = num_phases * (max_iterations + 1)

    await auto_run(
        store=store,
        task_id=task_id,
        graph=phase_role_graph,
        generate_fn=generate_fn,
        max_turns=max_turns,
        step_callback=step_callback,
    )


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #


def _read_interactive_input(phase: str) -> str:
    """Read multi-line phase output from stdin."""
    print(f"\n  Enter output for phase '{phase}' (Ctrl+D / Ctrl+Z when done):")
    lines: list[str] = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip() or _TEMPLATE_OUTPUTS.get(
        phase,
        f"## {phase}\n(empty)",
    )