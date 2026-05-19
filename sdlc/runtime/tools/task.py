"""Task lifecycle MCP tools — create, list, status, cancel, resume."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sdlc.engine.checkpoint import CheckpointError
from sdlc.models import Task, TaskStatus, WriteOp

if TYPE_CHECKING:
    from sdlc.engine.checkpoint import CheckpointManager
    from sdlc.engine.phase_graph import PhaseGraph
    from sdlc.runtime.store_backend import StoreBackend
    from sdlc.runtime.write_queue import WriteQueue


def _new_task(
    description: str,
    mode: str,
    judge_prompts: dict[str, str] | None = None,
) -> Task:
    now = datetime.now(UTC)
    return Task(
        task_id=uuid.uuid4().hex[:12],
        description=description,
        mode=mode,
        status=TaskStatus.ACTIVE,
        current_phase="Chatting",
        created_at=now,
        updated_at=now,
        locked_prompts=judge_prompts or {},
    )


async def create_task(
    write_queue: WriteQueue,
    description: str,
    mode: str = "feature",
    judge_prompts: dict[str, str] | None = None,
    trace_id: str | None = None,
) -> dict[str, str]:
    task = _new_task(description, mode, judge_prompts=judge_prompts)
    await write_queue.enqueue(
        WriteOp(target="task", action="create", payload=task.model_dump(mode="json")),
    )
    await write_queue.flush()
    result = {"task_id": task.task_id, "initial_phase": task.current_phase}
    if trace_id:
        result["trace_id"] = trace_id
    return result


async def get_status(store: StoreBackend, graph: PhaseGraph, task_id: str) -> dict[str, Any]:
    raw = await store.get_task(task_id)
    if raw is None:
        msg = f"Task not found: {task_id}"
        raise ValueError(msg)
    task = Task(**raw)
    persisted_history = await store.get_history(task_id)
    history = [
        record.model_dump(mode="json")
        for record in task.history
    ] or persisted_history
    return {
        "task_id": task.task_id,
        "phase": task.current_phase,
        "status": task.status.value,
        "mode": task.mode,
        "history": history,
        "iteration_count": task.iteration_count,
        "retry_count": task.retry_count,
        "last_failure_reason": task.last_failure_reason,
        "last_failure_type": task.last_failure_type,
        "estimated_progress": f"{round(graph.progress(task.current_phase))}%",
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def list_tasks(store: StoreBackend, status: str | None = None) -> dict[str, Any]:
    tasks = await store.list_tasks(status=status)
    return {
        "tasks": [
            {
                "task_id": t["task_id"],
                "phase": t.get("current_phase", "unknown"),
                "status": t.get("status", "unknown"),
                "description": t.get("description", ""),
                "created_at": t.get("created_at"),
            }
            for t in tasks
        ],
    }


async def cancel_task(store: StoreBackend, write_queue: WriteQueue, task_id: str) -> dict[str, Any]:
    raw = await store.get_task(task_id)
    if raw is None:
        msg = f"Task not found: {task_id}"
        raise ValueError(msg)
    task = Task(**raw)
    task.status = TaskStatus.CANCELLED
    task.updated_at = datetime.now(UTC)
    await write_queue.enqueue(
        WriteOp(target="task", action="update", payload=task.model_dump(mode="json")),
    )
    await write_queue.flush()
    return {"success": True, "cancelled_debate_agents": 0}


async def resume_task(
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    task_id: str,
) -> dict[str, Any]:
    """Restore task from latest checkpoint.

    Explicit MVP recovery entrypoint. SQLite is normal authority; checkpoint
    is the recovery snapshot. Returns mismatch/corrupt/not-recoverable errors
    explicitly without silently overwriting state.
    """
    try:
        checkpoint = checkpoint_mgr.restore(task_id)
    except CheckpointError as e:
        return {
            "recovered": False,
            "error": f"Checkpoint corrupt: {e}",
            "corrupt": True,
        }

    if checkpoint is None:
        return {
            "recovered": False,
            "error": f"No checkpoint found for task {task_id}",
            "not_recoverable": True,
        }

    raw = await store.get_task(task_id)

    if raw is None:
        task = Task(
            task_id=checkpoint.task_id,
            description=f"Restored from checkpoint (phase: {checkpoint.phase})",
            mode="feature",
            status=TaskStatus.ACTIVE,
            current_phase=checkpoint.phase,
            history=list(checkpoint.history),
            iteration_count=checkpoint.iteration_count,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await store.create_task(task.model_dump(mode="json"))
        return {
            "recovered": True,
            "restored_from_checkpoint": True,
            "phase": task.current_phase,
            "history_count": len(task.history),
            "iteration_count": task.iteration_count,
            "retry_count": task.retry_count,
        }

    task = Task(**raw)

    if task.current_phase != checkpoint.phase:
        return {
            "recovered": False,
            "error": (
                f"Checkpoint/state mismatch: SQLite phase '{task.current_phase}' "
                f"vs checkpoint phase '{checkpoint.phase}'"
            ),
            "mismatch": True,
            "sqlite_phase": task.current_phase,
            "checkpoint_phase": checkpoint.phase,
        }

    if len(task.history) != len(checkpoint.history):
        return {
            "recovered": False,
            "error": (
                f"Checkpoint/state mismatch: SQLite history length {len(task.history)} "
                f"vs checkpoint history length {len(checkpoint.history)}"
            ),
            "mismatch": True,
            "sqlite_history_count": len(task.history),
            "checkpoint_history_count": len(checkpoint.history),
        }

    return {
        "recovered": True,
        "restored_from_checkpoint": False,
        "phase": task.current_phase,
        "history_count": len(task.history),
        "iteration_count": task.iteration_count,
        "retry_count": task.retry_count,
        "last_failure_reason": task.last_failure_reason,
        "last_failure_type": task.last_failure_type,
    }
