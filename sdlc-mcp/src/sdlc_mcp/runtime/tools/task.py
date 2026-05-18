"""Task lifecycle MCP tools — create, list, status, cancel."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sdlc_mcp.models import Task, TaskStatus, WriteOp

if TYPE_CHECKING:
    from sdlc_mcp.engine.phase_graph import PhaseGraph
    from sdlc_mcp.runtime.store_backend import StoreBackend
    from sdlc_mcp.runtime.write_queue import WriteQueue


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
