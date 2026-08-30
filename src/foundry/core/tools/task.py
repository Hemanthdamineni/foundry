"""Task management tool functions for the MCP server.

Each function is referenced by the ``@app.tool()`` decorators in
``runtime/app.py`` and encapsulates the logic for creating, querying,
cancelling, and resuming SDLC tasks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from foundry.core.checkpoint.manager import CheckpointManager
    from foundry.core.orchestrator.phase_graph import PhaseGraph
    from foundry.core.store.ensure_initialized import BootstrapStore as StoreBackend
    from foundry.core.write_queue import WriteQueue


async def create_task(
    write_queue: WriteQueue,
    description: str,
    mode: str = "feature",
    judge_prompts: dict[str, str] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a new SDLC task and enqueue its creation.

    Parameters
    ----------
    write_queue:
        Serialized write queue for persistence.
    description:
        Free-text description of the task.
    mode:
        Workflow mode (``"feature"``, ``"bugfix"``, ``"refactor"``, …).
    judge_prompts:
        Optional locked judge prompt overrides keyed by transition name.
    trace_id:
        Optional trace ID to associate with this task.

    Returns
    -------
    dict
        Created task summary or error.
    """
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task: dict[str, Any] = {
        "task_id": task_id,
        "description": description,
        "mode": mode,
        "status": "queued",
        "current_phase": "Chatting",
        "history": [],
        "iteration_count": 0,
        "retry_count": 0,
        "locked_prompts": judge_prompts or {},
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
    }

    from foundry.core.models import WriteOp

    await write_queue.enqueue(WriteOp(target="task", action="create", payload=task))
    await write_queue.flush()

    return {
        "task_id": task_id,
        "description": description,
        "mode": mode,
        "status": "queued",
    }


async def get_status(
    store: StoreBackend,
    graph: PhaseGraph,
    task_id: str,
) -> dict[str, Any]:
    """Get the current status and progress of a task.

    Parameters
    ----------
    store:
        Active store backend.
    graph:
        Phase graph used to compute progress.
    task_id:
        The task to query.

    Returns
    -------
    dict
        Task status including phase, progress percentage, and history summary.
    """
    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    from foundry.core.models import Task

    task = Task(**raw)
    history_summary = [
        {
            "phase": h.phase,
            "status": h.status.value if hasattr(h.status, "value") else h.status,
            "output_preview": (h.output or "")[:120] if h.output else None,
        }
        for h in task.history
    ]

    return {
        "task_id": task.task_id,
        "description": task.description,
        "mode": task.mode,
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "current_phase": task.current_phase,
        "progress_pct": round(graph.progress(task.current_phase), 1),
        "iteration_count": task.iteration_count,
        "retry_count": task.retry_count,
        "history": history_summary,
    }


async def list_tasks(
    store: StoreBackend,
    status: str | None = None,
) -> dict[str, Any]:
    """List all tasks, optionally filtered by status.

    Parameters
    ----------
    store:
        Active store backend.
    status:
        Optional status filter.

    Returns
    -------
    dict
        ``{tasks: […], total: N}``.
    """
    try:
        raw_tasks = await store.list_tasks(status=status)
    except Exception as exc:
        return {"error": f"Failed to list tasks: {exc}"}

    tasks = [
        {
            "task_id": t.get("task_id"),
            "description": t.get("description", ""),
            "mode": t.get("mode", "feature"),
            "status": t.get("status", "unknown"),
            "current_phase": t.get("current_phase", ""),
            "created_at": t.get("created_at"),
        }
        for t in raw_tasks
    ]

    return {"tasks": tasks, "total": len(tasks)}


async def cancel_task(
    store: StoreBackend,
    write_queue: WriteQueue,
    task_id: str,
) -> dict[str, Any]:
    """Cancel a task — marks it as cancelled and persists.

    Parameters
    ----------
    store:
        Active store backend.
    write_queue:
        Serialized write queue for persistence.
    task_id:
        The task to cancel.

    Returns
    -------
    dict
        Confirmation or error.
    """
    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    raw["status"] = "cancelled"
    raw["updated_at"] = datetime.now(UTC).isoformat()

    from foundry.core.models import WriteOp

    await write_queue.enqueue(WriteOp(target="task", action="update", payload=raw))
    await write_queue.flush()

    return {"task_id": task_id, "status": "cancelled"}


async def resume_task(
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    task_id: str,
) -> dict[str, Any]:
    """Resume a task from its latest checkpoint.

    Parameters
    ----------
    store:
        Active store backend.
    checkpoint_mgr:
        Checkpoint manager for restoring state.
    task_id:
        The task to resume.

    Returns
    -------
    dict
        Restored task state or error.
    """
    raw = await store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    checkpoint = checkpoint_mgr.restore(task_id)
    if checkpoint is None:
        return {
            "task_id": task_id,
            "status": raw.get("status"),
            "current_phase": raw.get("current_phase"),
            "message": "No checkpoint found — resuming from stored task state",
        }

    raw["status"] = "running"
    raw["current_phase"] = checkpoint.phase
    raw["updated_at"] = datetime.now(UTC).isoformat()

    from foundry.core.models import WriteOp

    await write_queue.enqueue(WriteOp(target="task", action="update", payload=raw))
    await write_queue.flush()

    return {
        "task_id": task_id,
        "status": "running",
        "current_phase": checkpoint.phase,
        "iteration_count": checkpoint.iteration_count,
        "history_count": len(checkpoint.history),
    }
