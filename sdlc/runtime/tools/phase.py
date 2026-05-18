"""Phase tools — get_next_action, submit_output, request_approval."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sdlc.engine.orchestrator import OrchestratorError
from sdlc.models import (
    Checkpoint,
    DebateTranscript,
    DecisionAction,
    JudgeVerdict,
    PhaseRecord,
    PhaseStatus,
    Task,
    TaskStatus,
    WriteOp,
)

if TYPE_CHECKING:
    from sdlc.engine.checkpoint import CheckpointManager
    from sdlc.engine.debate_runtime import DebateRuntime
    from sdlc.engine.execution_policy import ExecutionPolicy
    from sdlc.engine.judge import JudgeEngine
    from sdlc.engine.orchestrator import OrchestratorFSM
    from sdlc.runtime.pipelines.default import IndexPipeline
    from sdlc.runtime.store_backend import StoreBackend
    from sdlc.runtime.tracing import Tracer
    from sdlc.runtime.write_queue import WriteQueue


def _routes(model_routing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases = model_routing.get("phases", {})
    if not isinstance(phases, dict):
        return {}
    return {
        str(phase): route if isinstance(route, dict) else {}
        for phase, route in phases.items()
    }


def _route_for(model_routing: dict[str, Any], phase: str) -> dict[str, Any]:
    route = _routes(model_routing).get(phase, {})
    defaults = model_routing.get("defaults", {})
    if isinstance(defaults, dict):
        return {**defaults, **route}
    return route


async def get_next_action(  # noqa: PLR0913 - tool wiring keeps runtime dependencies explicit.
    store: StoreBackend,
    _checkpoint_mgr: CheckpointManager,
    orchestrator: OrchestratorFSM,
    task_id: str,
    model_routing: dict[str, Any],
    tracer: Tracer | None = None,
    index_pipeline: IndexPipeline | None = None,
) -> dict[str, Any]:
    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    phase = task.current_phase
    graph = orchestrator.graph
    route = _route_for(model_routing, phase)
    history = await store.get_history(task_id)
    if tracer is not None:
        await tracer.record_span(
            tracer.create_trace_id(),
            phase=phase,
            tool="sdlc_get_next_action",
            task_id=task_id,
        )

    relevant_files: list[str] = []
    context_chunks: list[dict[str, Any]] = []
    graph_summary: dict[str, Any] = {}

    if index_pipeline is not None:
        ctx = await index_pipeline.get_context_for_phase(
            phase=phase,
            target_files=None,
            description=task.description,
        )
        relevant_files = ctx.get("relevant_files", [])
        context_chunks = ctx.get("context_chunks", [])
        graph_summary = ctx.get("graph_summary", {})

    return {
        "task_id": task_id,
        "phase": phase,
        "phase_index": graph.index_of(phase),
        "subagent": route.get("subagent", "dev-sdlc"),
        "model": route.get("model", model_routing.get("default_model", "qwen3:8b")),
        "fallback_models": route.get("fallback_models", []),
        "prompt": _phase_prompt(phase, task.description),
        "context": {
            "task_description": task.description,
            "previous_outputs": history or [
                record.model_dump(mode="json") for record in task.history
            ],
            "relevant_files": relevant_files,
            "context_chunks": context_chunks,
            "graph_summary": graph_summary,
        },
        "constraints": {
            "must_produce": _phase_requirements(phase),
            "must_not_do": _phase_restrictions(phase),
            "bash_allowed_patterns": _phase_bash_patterns(phase, route),
        },
        "mode": task.mode,
        "requires_approval": task.requires_approval,
        "progress": graph.progress(phase),
    }


def _phase_prompt(phase: str, description: str) -> str:
    return (
        f"You are executing the {phase} phase for this SDLC task:\n\n"
        f"{description}\n\n"
        f"{_phase_requirements(phase)}"
    )


def _phase_requirements(phase: str) -> str:
    requirements = {
        "Chatting": "Clarify the task description and intent.",
        "ContextHarvesting": "Output must include ## Questions and ## Constraints sections. Ask every important question NOW — after spec approval no human questions are allowed.",
        "Specs": "Output must include ## Requirements, ## Scope, ## Constraints sections.",
        "Planning": "Output must include ## Implementation Plan, ## File Changes, ## Risks.",
        "Coding": "Output must reference specific files modified.",
        "Review": "Output must include ## Issues Found, ## Severity, ## Must Fix sections.",
        "Testing": "Output must include ## Test Results, ## Coverage, ## Failed sections.",
        "Done": "Summarize what was accomplished.",
    }
    return requirements.get(phase, "Complete the current phase.")


def _phase_restrictions(phase: str) -> list[str]:
    if phase in {"Coding", "Testing"}:
        return []
    return ["Do not edit files in this phase.", "Do not run mutating shell commands."]


def _phase_bash_patterns(phase: str, route: dict[str, Any]) -> list[str]:
    configured = route.get("bash_allowed_patterns")
    if isinstance(configured, list):
        return [str(item) for item in configured]
    if phase in {"Coding", "Testing"}:
        return [
            "test",
            "build",
            "lint",
            "format",
            "install",
            "npm *",
            "pip *",
            "pixi *",
            "git *",
            "python *",
        ]
    return []


def _debate_dict(transcript: DebateTranscript | None) -> dict[str, Any] | None:
    if transcript is None or transcript.consensus is None:
        return None
    return {
        "rounds": len(transcript.rounds),
        "consensus_reached": transcript.consensus.reached,
        "consensus_passed": transcript.consensus.passed,
        "reason": transcript.consensus.reason,
    }


def _is_iteration_limit_reached(
    phase: str,
    resolved: str,
    iteration_count: int,
    max_iterations: int,
) -> bool:
    return phase == "Review" and resolved == "Coding" and iteration_count >= max_iterations


async def _run_debate_if_needed(
    task: Task,
    phase: str,
    output: str,
    verdict: JudgeVerdict,
    debate_runtime: DebateRuntime | None,
) -> tuple[JudgeVerdict, DebateTranscript | None]:
    if debate_runtime is None:
        return verdict, None
    if task.budget.max_debate_rounds <= 0:
        return verdict, None
    if verdict.passed:
        return verdict, None

    transcript = await debate_runtime.run_debate(
        task=task,
        phase=phase,
        output=output,
        budget=task.budget,
    )

    if transcript.consensus and transcript.consensus.reached and transcript.consensus.passed:
        overridden = JudgeVerdict(
            passed=True,
            reason=f"Debate overturns judge: {transcript.consensus.reason}",
            issues=transcript.consensus.disagreement_areas,
            severity="info",
        )
        return overridden, transcript

    return verdict, transcript


async def submit_output(  # noqa: C901, PLR0912, PLR0913
    store: StoreBackend,
    _checkpoint_mgr: CheckpointManager,
    orchestrator: OrchestratorFSM,
    policy: ExecutionPolicy,
    write_queue: WriteQueue,
    task_id: str,
    phase: str,
    output: str,
    max_iterations: int = 8,
    next_phase: str | None = None,
    judge_engine: JudgeEngine | None = None,
    tracer: Tracer | None = None,
    debate_runtime: DebateRuntime | None = None,
) -> dict[str, Any]:
    raw = await store.get_task(task_id)
    if raw is None:
        return {"accepted": False, "error": f"Task not found: {task_id}"}
    task = Task(**raw)
    if tracer is not None:
        await tracer.record_span(
            tracer.create_trace_id(),
            phase=phase,
            tool="sdlc_submit_output",
            task_id=task_id,
        )

    if task.current_phase != phase:
        return {
            "accepted": False,
            "error": f"Phase mismatch: expected '{task.current_phase}', got '{phase}'",
            "hint": "Call sdlc_get_next_action to resync",
        }

    budget_check = await policy.check_budget(task)
    if budget_check.action == DecisionAction.ABORT:
        return {
            "accepted": False,
            "error": budget_check.reason,
            "hint": "Budget exhausted. Task will be cancelled.",
        }

    try:
        resolved = orchestrator.submit(phase, target=next_phase)
    except OrchestratorError as e:
        return {"accepted": False, "error": str(e), "hint": "Check phase graph configuration."}

    task.iteration_count += 1

    verdict: JudgeVerdict | None = None
    debate_transcript: DebateTranscript | None = None
    if judge_engine is not None and phase != "Chatting":
        verdict = await judge_engine.evaluate(task, phase, resolved, output)
        if verdict is not None and not verdict.passed:
            verdict, debate_transcript = await _run_debate_if_needed(
                task, phase, output, verdict, debate_runtime,
            )

    if verdict is not None and not verdict.passed:
        if _is_iteration_limit_reached(phase, resolved, task.iteration_count, max_iterations):
            verdict = JudgeVerdict(
                passed=True,
                reason=f"Max iterations ({max_iterations}) reached, forcing transition",
                issues=verdict.issues,
                severity="warning",
            )
        else:
            record = PhaseRecord(
                phase=phase,
                status=PhaseStatus.REJECTED,
                output=output,
                error=verdict.reason,
                completed_at=datetime.now(UTC),
                iteration_count=task.iteration_count,
            )
            task.history.append(record)
            task.updated_at = datetime.now(UTC)
            await write_queue.enqueue(
                WriteOp(
                    target="task",
                    action="update",
                    payload=task.model_dump(mode="json"),
                ),
            )
            await write_queue.flush()
            result: dict[str, Any] = {
                "accepted": False,
                "error": f"Judge rejected: {verdict.reason}",
                "issues": verdict.issues,
                "severity": verdict.severity,
                "hint": "Fix the issues and resubmit.",
            }
            debate_info = _debate_dict(debate_transcript)
            if debate_info:
                result["debate"] = debate_info
            return result

    if _is_iteration_limit_reached(phase, resolved, task.iteration_count, max_iterations):
        resolved = "Done"

    record = PhaseRecord(
        phase=phase,
        status=PhaseStatus.ACCEPTED,
        output=output,
        completed_at=datetime.now(UTC),
        iteration_count=task.iteration_count,
    )
    task.history.append(record)
    task.current_phase = resolved
    task.requires_approval = False
    task.updated_at = datetime.now(UTC)
    if resolved == "Done":
        task.status = TaskStatus.DONE

    checkpoint = Checkpoint(
        task_id=task_id,
        phase=task.current_phase,
        history=task.history,
        iteration_count=task.iteration_count,
        created_at=datetime.now(UTC),
    )
    await write_queue.enqueue(
        WriteOp(target="task", action="update", payload=task.model_dump(mode="json")),
    )
    await write_queue.enqueue(
        WriteOp(
            target="phase_output",
            action="create",
            payload={
                "task_id": task_id,
                "phase": phase,
                "output": output,
                "status": "accepted",
                "iteration_count": task.iteration_count,
                "judge_verdict": verdict.model_dump(mode="json") if verdict else None,
            },
        ),
    )
    await write_queue.enqueue(
        WriteOp(target="checkpoint", action="create", payload=checkpoint.model_dump(mode="json")),
    )
    await write_queue.flush()

    result = {
        "accepted": True,
        "next_phase": resolved,
        "reason": f"Transition from '{phase}' to '{resolved}'",
        "iteration_count": task.iteration_count,
        "judge_verdict": verdict.model_dump(mode="json") if verdict else None,
    }
    debate_info = _debate_dict(debate_transcript)
    if debate_info:
        result["debate"] = debate_info
    return result


async def request_approval(  # noqa: PLR0913
    store: StoreBackend,
    write_queue: WriteQueue,
    task_id: str,
    phase: str,
    summary: str,
    *,
    approved: bool = False,
    tracer: Tracer | None = None,
) -> dict[str, Any]:
    raw = await store.get_task(task_id)
    if raw is None:
        return {"approved": False, "error": "Task not found"}
    task = Task(**raw)
    if tracer is not None:
        await tracer.record_span(
            tracer.create_trace_id(),
            phase=phase,
            tool="sdlc_request_approval",
            task_id=task_id,
        )
    task.requires_approval = not approved
    task.updated_at = datetime.now(UTC)
    await write_queue.enqueue(
        WriteOp(target="task", action="update", payload=task.model_dump(mode="json")),
    )
    await write_queue.flush()
    if approved:
        return {"approved": True, "feedback": "Approved.", "phase": phase, "summary": summary}
    return {
        "approved": False,
        "pending": True,
        "phase": phase,
        "feedback": "Approval pending. Re-run sdlc_request_approval with approved=true.",
        "summary": summary,
    }
