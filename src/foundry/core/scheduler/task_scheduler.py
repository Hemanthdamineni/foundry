"""TaskScheduler — parallel task execution with capability routing.

Manages a pool of concurrent tasks, using the CapabilityRouter to determine
orchestration intensity and WorkspaceBoundaries to enforce limits.

Architecture reference:
    SC Scheduler — "When and in what order does work happen?"
    GV Governance — "Capability MoE — role-based routing"
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

from foundry.core.capability_router import CapabilityRouter, RigorLevel, RoutingDecision
from foundry.core.logging import get_logger
from foundry.core.workspace.manager import WorkspaceBoundaries

log = get_logger("foundry.scheduler")


# --------------------------------------------------------------------------- #
#  Task state
# --------------------------------------------------------------------------- #


class TaskStatus:
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """A task managed by the TaskScheduler."""

    task_id: str
    prompt: str
    workspace_id: str | None = None
    priority: int = 0  # Higher = runs first
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    status: str = TaskStatus.PENDING
    routing: RoutingDecision | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at


# --------------------------------------------------------------------------- #
#  TaskScheduler
# --------------------------------------------------------------------------- #


class TaskScheduler:
    """Manages parallel task execution with capability routing.

    Usage::

        scheduler = TaskScheduler(
            store=store,
            chronicle=chronicle,
            generate_fn=my_llm_generate,
        )

        # Schedule tasks
        task = scheduler.schedule("Implement auth module", workspace_id="ws_abc")
        task2 = scheduler.schedule("Add tests", priority=10)

        # Run all tasks
        results = await scheduler.run_all()

        # Or run a single task
        result = await scheduler.run(task.task_id)
    """

    def __init__(
        self,
        store: Any = None,
        chronicle: Any = None,
        generate_fn: Callable[[str], Awaitable[str]] | None = None,
        max_concurrent: int = 5,
        router: CapabilityRouter | None = None,
    ) -> None:
        self._store = store
        self._chronicle = chronicle
        self._generate_fn = generate_fn
        self._max_concurrent = max_concurrent
        self._router = router or CapabilityRouter()

        self._tasks: dict[str, ScheduledTask] = {}
        self._running: dict[str, asyncio.Task[None]] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, str]] = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def schedule(
        self,
        prompt: str,
        *,
        workspace_id: str | None = None,
        priority: int = 0,
        boundaries: WorkspaceBoundaries | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        """Schedule a new task for execution.

        The task is routed through the CapabilityRouter to determine
        orchestration intensity, then queued for execution.
        """
        task_id = f"sched_{uuid.uuid4().hex[:12]}"

        # Route the task
        routing = self._router.route(prompt, workspace_boundaries=boundaries)

        task = ScheduledTask(
            task_id=task_id,
            prompt=prompt,
            workspace_id=workspace_id,
            priority=priority,
            routing=routing,
            metadata=metadata or {},
        )

        self._tasks[task_id] = task

        # Enqueue (negative priority for min-heap → highest priority first)
        self._queue.put_nowait((-priority, task_id))

        task.status = TaskStatus.QUEUED

        log.info(
            "task scheduled: %s (rigor=%s, caps=%s, priority=%d)",
            task_id,
            routing.rigor.value,
            [c.value for c in routing.capabilities],
            priority,
        )

        return task

    async def run(self, task_id: str) -> str | None:
        """Run a single task to completion.

        Acquires a semaphore slot, runs the task, then releases.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Unknown task: {task_id}")

        if task.status == TaskStatus.RUNNING:
            raise ValueError(f"Task already running: {task_id}")

        async with self._semaphore:
            return await self._execute_task(task)

    async def run_all(self, timeout: float | None = None) -> dict[str, str | None]:
        """Run all queued tasks in parallel (up to max_concurrent).

        Returns a dict of task_id → result.
        """
        results: dict[str, str | None] = {}

        # Collect all pending tasks
        pending: list[str] = []
        while not self._queue.empty():
            _, task_id = await self._queue.get()
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.QUEUED:
                pending.append(task_id)

        # Run them concurrently
        async def _run_one(tid: str) -> None:
            try:
                result = await self.run(tid)
                results[tid] = result
            except Exception as exc:
                results[tid] = None
                task = self._tasks.get(tid)
                if task:
                    task.error = str(exc)
                    task.status = TaskStatus.FAILED

        tasks = [asyncio.create_task(_run_one(tid)) for tid in pending]

        if timeout:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
            except asyncio.TimeoutError:
                log.warning("run_all timed out after %.1fs", timeout)
        else:
            await asyncio.gather(*tasks, return_exceptions=True)

        return results

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status == TaskStatus.RUNNING and task_id in self._running:
            self._running[task_id].cancel()
            del self._running[task_id]

        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()
        return True

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        *,
        status: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[ScheduledTask]:
        results = list(self._tasks.values())
        if status:
            results = [t for t in results if t.status == status]
        if workspace_id:
            results = [t for t in results if t.workspace_id == workspace_id]
        return sorted(results, key=lambda t: t.created_at, reverse=True)[:limit]

    @property
    def stats(self) -> dict[str, Any]:
        status_counts = defaultdict(int)
        for task in self._tasks.values():
            status_counts[task.status] += 1

        return {
            "total": len(self._tasks),
            "running": len(self._running),
            "queued": self._queue.qsize(),
            "by_status": dict(status_counts),
            "max_concurrent": self._max_concurrent,
        }

    # -- Internal ----------------------------------------------------------- #

    async def _execute_task(self, task: ScheduledTask) -> str | None:
        """Execute a single task."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # Chronicle the start
        if self._chronicle:
            await self._chronicle.append(
                "task.started",
                {
                    "task_id": task.task_id,
                    "rigor": task.routing.rigor.value if task.routing else "standard",
                },
                workspace_id=task.workspace_id,
                task_id=task.task_id,
            )

        try:
            if self._generate_fn is None:
                # No generate function — return stub result
                result = f"Task {task.task_id} completed (no generate_fn configured)"
            else:
                # Use the generate function with the task prompt
                result = await self._generate_fn(task.prompt)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()

            # Chronicle the completion
            if self._chronicle:
                await self._chronicle.append(
                    "task.completed",
                    {
                        "task_id": task.task_id,
                        "duration_s": task.duration_s,
                        "result_length": len(result) if result else 0,
                    },
                    workspace_id=task.workspace_id,
                    task_id=task.task_id,
                )

            log.info(
                "task completed: %s (duration=%.1fs)",
                task.task_id,
                task.duration_s or 0,
            )

            return result

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            raise

        except Exception as exc:
            task.error = str(exc)
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()

            if self._chronicle:
                await self._chronicle.append(
                    "task.failed",
                    {"task_id": task.task_id, "error": str(exc)},
                    workspace_id=task.workspace_id,
                    task_id=task.task_id,
                )

            log.error("task failed: %s — %s", task.task_id, exc)
            return None
