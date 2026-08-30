"""Phase transition tool functions for the MCP server.

Each function is referenced by the ``@app.tool()`` decorators in
``runtime/app.py`` and implements the core orchestrator loop: determining
the next action, submitting phase output, and requesting human approval.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from foundry.features.sdlc_runtime.engine.checkpoint import CheckpointManager
    from foundry.features.sdlc_runtime.engine.debate_runtime import DebateRuntime
    from foundry.features.sdlc_runtime.engine.judge import JudgeEngine
    from foundry.features.sdlc_runtime.engine.orchestrator import OrchestratorFSM
    from foundry.features.sdlc_runtime.engine.execution_policy import ExecutionPolicy
    from foundry.features.sdlc_runtime.engine.phase_graph import PhaseGraph
    from foundry.features.sdlc_runtime.runtime.pipelines.default import IndexPipeline
    from foundry.features.sdlc_runtime.runtime.store_backend import StoreBackend
    from foundry.features.sdlc_runtime.runtime.tool_executor import ToolExecutor
    from foundry.features.sdlc_runtime.runtime.tool_gate import ToolGate
    from foundry.features.sdlc_runtime.runtime.tracing import Tracer
    from foundry.features.sdlc_runtime.runtime.write_queue import WriteQueue

from foundry.core.logging import get_logger

log = get_logger("tools.phase")


async def get_next_action(
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    orchestrator: OrchestratorFSM,
    task_id: str,
    model_routing: dict[str, Any],
    *,
    tracer: Tracer | None = None,
    index_pipeline: IndexPipeline | None = None,
) -> dict[str, Any]:
    """Determine the next action for a task based on its current phase.

    Parameters
    ----------
    store:
        Active store backend.
    checkpoint_mgr:
        Checkpoint manager (used if resuming from a checkpoint).
    orchestrator:
        The orchestrator FSM for the task's mode.
    task_id:
        Task to advance.
    model_routing:
        Model routing configuration.
    tracer:
        Optional tracer for observability.
    index_pipeline:
        Optional index pipeline for context harvesting.

    Returns
    -------
    dict
        The next action description with phase, suggested model, and
        available transitions.
    """
    from foundry.core.models import Task

    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    task = Task(**raw)
    current = task.current_phase

    if orchestrator.is_terminal(current):
        return {
            "task_id": task_id,
            "phase": current,
            "action": "complete",
            "message": f"Task is in terminal phase '{current}' — no further action needed.",
        }

    # Restore checkpoint if available (task was interrupted mid-phase)
    checkpoint = checkpoint_mgr.restore(task_id)
    if checkpoint is not None and checkpoint.phase == current:
        log.info("Resumed from checkpoint for task %s phase %s", task_id, current)

    # Determine possible next phases
    possible = orchestrator.graph.possible_next(current)
    phase_models = model_routing.get("phases", {}).get(current, {})
    suggested_model = None
    models_list = phase_models.get("models", []) if isinstance(phase_models, dict) else []
    if models_list:
        suggested_model = models_list[0]

    # Context harvesting hint for early phases
    context_hint = None
    if current == "Chatting" and index_pipeline is not None:
        context_hint = "Context harvesting available — run sdlc_harvest_context to gather requirements."

    return {
        "task_id": task_id,
        "phase": current,
        "action": "continue",
        "possible_transitions": possible,
        "suggested_model": suggested_model,
        "context_hint": context_hint,
        "description": task.description,
        "iteration": task.iteration_count,
    }


async def submit_output(  # noqa: PLR0913, PLR0912
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    orchestrator: OrchestratorFSM,
    policy: ExecutionPolicy,
    write_queue: WriteQueue,
    task_id: str,
    phase: str,
    output: str,
    *,
    max_iterations: int = 8,
    next_phase: str | None = None,
    judge_engine: JudgeEngine | None = None,
    tracer: Tracer | None = None,
    debate_runtime: DebateRuntime | None = None,
    tool_executor: ToolExecutor | None = None,
    tool_gate: ToolGate | None = None,
    workspace_path: str = ".",
    all_files: bool = False,
) -> dict[str, Any]:
    """Submit phase output, run judgement, and advance the task state.

    Parameters
    ----------
    store:
        Active store backend.
    checkpoint_mgr:
        Checkpoint manager for saving phase progress.
    orchestrator:
        The orchestrator FSM for the task's mode.
    policy:
        Execution policy for budget/retry decisions.
    write_queue:
        Serialized write queue for persistence.
    task_id:
        The task being worked on.
    phase:
        The phase whose output is being submitted.
    output:
        Raw phase output text.
    max_iterations:
        Maximum allowed iterations before forced review.
    next_phase:
        Optional explicit next phase (bypasses FSM).
    judge_engine:
        Optional LLM judge engine.
    tracer:
        Optional tracer for observability.
    debate_runtime:
        Optional debate runtime for multi-agent review.
    tool_executor:
        Optional tool executor for running gates.
    tool_gate:
        Optional tool gate for pre-approval checks.
    workspace_path:
        Path to the workspace root.
    all_files:
        If True, include all workspace files in context.

    Returns
    -------
    dict
        Submission result including acceptance, verdict, and next phase.
    """
    from foundry.core.models import (
        Checkpoint,
        DecisionAction,
        PhaseRecord,
        PhaseStatus,
        Task,
        WriteOp,
    )

    raw = await store.get_task(task_id)
    if raw is None:
        return {"accepted": False, "error": f"Task not found: {task_id}"}

    task = Task(**raw)

    # ── Phase match guard ──────────────────────────────────────────────
    if phase != task.current_phase:
        return {
            "accepted": False,
            "error": (
                f"Phase mismatch: submitted '{phase}' but task is "
                f"in '{task.current_phase}'"
            ),
        }

    # ── Save phase output ──────────────────────────────────────────────
    phase_record = PhaseRecord(
        phase=phase,
        status=PhaseStatus.SUBMITTED,
        output=output,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    task.history.append(phase_record)

    # ── Determine next phase ───────────────────────────────────────────
    target_phase: str | None = next_phase
    if target_phase is None:
        try:
            target_phase = orchestrator.submit(phase)
        except Exception as exc:
            task.status = "failed"
            task.last_failure_reason = str(exc)
            await _persist_task(store, write_queue, task)
            return {
                "accepted": False,
                "error": f"Orchestrator rejected transition: {exc}",
                "task_id": task_id,
            }

    if target_phase is None:
        target_phase = "Done"

    # ── Judge evaluation ───────────────────────────────────────────────
    verdict = None
    if judge_engine is not None and target_phase != "Done":
        try:
            verdict = await judge_engine.evaluate(task, phase, target_phase, output)
            if not verdict.passed:
                log.warning(
                    "Judge rejected %s → %s for task %s: %s",
                    phase,
                    target_phase,
                    task_id,
                    verdict.reason,
                )
        except Exception as exc:
            log.warning("Judge engine failed for task %s: %s", task_id, exc)
            verdict = None

    # ── Budget check ──────────────────────────────────────────────────
    budget_decision = await policy.check_budget(task)
    if budget_decision.action == DecisionAction.ABORT:
        task.status = "failed"
        task.last_failure_reason = budget_decision.reason
        await _persist_task(store, write_queue, task)
        return {
            "accepted": False,
            "error": budget_decision.reason,
            "budget_exhausted": True,
            "task_id": task_id,
        }

    # ── Advance state ──────────────────────────────────────────────────
    task.current_phase = target_phase
    task.iteration_count += 1
    task.updated_at = datetime.now(UTC).isoformat()
    task.status = "running" if target_phase != "Done" else "done"

    # ── Save checkpoint ────────────────────────────────────────────────
    checkpoint = Checkpoint(
        task_id=task_id,
        phase=target_phase,
        history=task.history,
        iteration_count=task.iteration_count,
    )
    checkpoint_mgr.save(checkpoint)
    await store.save_checkpoint(task_id, checkpoint.model_dump(mode="json"))

    await _persist_task(store, write_queue, task)

    # ── Run gates if configured ────────────────────────────────────────
    gate_results: dict[str, Any] = {}
    if tool_gate is not None and target_phase == "Review" and tool_executor is not None:
        gate_results = await _run_gates(tool_gate, tool_executor, workspace_path)

    result: dict[str, Any] = {
        "accepted": True,
        "task_id": task_id,
        "previous_phase": phase,
        "next_phase": target_phase,
        "iteration": task.iteration_count,
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "judge_verdict": verdict.model_dump(mode="json") if verdict is not None else None,
    }
    if gate_results:
        result["gate_results"] = gate_results

    # ── Debate if configured ───────────────────────────────────────────
    if debate_runtime is not None and target_phase == "Review":
        try:
            debate_result = await debate_runtime.run_debate(
                task=task,
                phase=phase,
                output=output,
                budget=task.budget,
            )
            result["debate"] = {
                "rounds": len(debate_result.rounds) if hasattr(debate_result, "rounds") else 0,
                "consensus": (
                    debate_result.consensus.model_dump(mode="json")
                    if hasattr(debate_result, "consensus") and debate_result.consensus
                    else None
                ),
            }
        except Exception as exc:
            log.warning("Debate runtime failed for task %s: %s", task_id, exc)

    return result


async def request_approval(
    store: StoreBackend,
    write_queue: WriteQueue,
    task_id: str,
    phase: str,
    summary: str,
    *,
    approved: bool = False,
    tracer: Tracer | None = None,
) -> dict[str, Any]:
    """Request or record human approval for a phase transition.

    Parameters
    ----------
    store:
        Active store backend.
    write_queue:
        Serialized write queue for persistence.
    task_id:
        The task requiring approval.
    phase:
        The phase requesting approval.
    summary:
        Human-readable summary of what needs approval.
    approved:
        Pre-approved flag — if True the approval is recorded immediately.
    tracer:
        Optional tracer for observability.

    Returns
    -------
    dict
        Approval status.
    """
    from foundry.core.models import Task, WriteOp

    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    task = Task(**raw)

    approval_record = {
        "task_id": task_id,
        "phase": phase,
        "summary": summary,
        "approved": approved,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if approved:
        task.requires_approval = False
        task.updated_at = datetime.now(UTC).isoformat()
        await write_queue.enqueue(
            WriteOp(target="task", action="update", payload=task.model_dump(mode="json"))
        )
        await write_queue.flush()

        return {
            "task_id": task_id,
            "phase": phase,
            "approved": True,
            "message": "Approval recorded — task may proceed.",
        }

    return {
        "task_id": task_id,
        "phase": phase,
        "approved": False,
        "message": "Pending approval — use foundry approve to grant.",
        "summary": summary,
    }


# ── Helpers ──────────────────────────────────────────────────────────


async def _persist_task(
    store: StoreBackend,
    write_queue: WriteQueue,
    task: Any,
) -> None:
    """Persist the updated task via the write queue and store."""
    from foundry.core.models import WriteOp

    task_dict = task.model_dump(mode="json") if hasattr(task, "model_dump") else task
    await write_queue.enqueue(WriteOp(target="task", action="update", payload=task_dict))
    await write_queue.flush()
    await store.update_task(task.task_id, task_dict)


async def _run_gates(
    tool_gate: ToolGate,
    tool_executor: ToolExecutor,
    workspace_path: str,
) -> dict[str, Any]:
    """Run tool gates (lint, types, tests, secrets) after a phase transition.

    Returns a dict of ``{gate_name: passed/bool}``.
    """
    from sdlc_models.phases import Task as SdlcTask

    results: dict[str, Any] = {}
    required = tool_gate.required_gates("Review")
    for gate_name in required:
        adapter = tool_executor.get_adapter(gate_name)
        if adapter is None:
            results[gate_name] = {"passed": True, "skipped": "No adapter registered"}
            continue
        try:
            adapter_result = await adapter.execute(
                SdlcTask(task_id="gate-check", description="Gate check", status="running")
            )
            passed = adapter_result.get("passed", False)
            results[gate_name] = {
                "passed": passed,
                "details": adapter_result,
            }
        except Exception as exc:
            results[gate_name] = {
                "passed": False,
                "error": str(exc),
            }
    return results
