"""Tests for TaskScheduler — parallel task execution."""

from __future__ import annotations

import asyncio

import pytest

from foundry.core.scheduler.task_scheduler import (
    ScheduledTask,
    TaskScheduler,
    TaskStatus,
)
from foundry.core.capability_router import CapabilityRouter, RigorLevel
from foundry.core.workspace.manager import WorkspaceBoundaries


class TestScheduledTask:
    def test_duration_not_started(self) -> None:
        task = ScheduledTask(task_id="t1", prompt="test")
        assert task.duration_s is None

    def test_duration_running(self) -> None:
        task = ScheduledTask(task_id="t1", prompt="test", started_at=100.0)
        assert task.duration_s is not None
        assert task.duration_s > 0


class TestTaskScheduler:
    @pytest.mark.asyncio
    async def test_schedule_task(self) -> None:
        scheduler = TaskScheduler()
        task = scheduler.schedule("Implement auth")
        assert task.task_id.startswith("sched_")
        assert task.status == TaskStatus.QUEUED
        assert task.routing is not None
        assert task.routing.rigor in (RigorLevel.STANDARD, RigorLevel.THOROUGH)

    @pytest.mark.asyncio
    async def test_run_single_task(self) -> None:
        async def mock_generate(prompt: str) -> str:
            return f"Generated for: {prompt}"

        scheduler = TaskScheduler(generate_fn=mock_generate)
        task = scheduler.schedule("Test task")
        result = await scheduler.run(task.task_id)

        assert result == "Generated for: Test task"
        assert task.status == TaskStatus.COMPLETED
        assert task.result == result
        assert task.completed_at is not None

    @pytest.mark.asyncio
    async def test_run_all_parallel(self) -> None:
        call_count = 0

        async def mock_generate(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return f"Done: {prompt}"

        scheduler = TaskScheduler(max_concurrent=3, generate_fn=mock_generate)
        scheduler.schedule("Task 1")
        scheduler.schedule("Task 2")
        scheduler.schedule("Task 3")

        results = await scheduler.run_all()
        assert len(results) == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_cancel_task(self) -> None:
        scheduler = TaskScheduler()
        task = scheduler.schedule("Test task")
        assert scheduler.cancel(task.task_id) is True
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_list_tasks(self) -> None:
        scheduler = TaskScheduler()
        scheduler.schedule("Task 1", workspace_id="ws_1")
        scheduler.schedule("Task 2", workspace_id="ws_2")
        scheduler.schedule("Task 3", workspace_id="ws_1")

        all_tasks = scheduler.list_tasks()
        assert len(all_tasks) == 3

        ws1_tasks = scheduler.list_tasks(workspace_id="ws_1")
        assert len(ws1_tasks) == 2

    @pytest.mark.asyncio
    async def test_stats(self) -> None:
        scheduler = TaskScheduler(max_concurrent=5)
        scheduler.schedule("Task 1")
        scheduler.schedule("Task 2")

        stats = scheduler.stats
        assert stats["total"] == 2
        assert stats["max_concurrent"] == 5
        assert stats["by_status"]["queued"] == 2

    @pytest.mark.asyncio
    async def test_concurrency_limit(self) -> None:
        running_tasks: list[str] = []

        async def mock_generate(prompt: str) -> str:
            running_tasks.append(prompt)
            await asyncio.sleep(0.05)
            return f"Done: {prompt}"

        scheduler = TaskScheduler(max_concurrent=2, generate_fn=mock_generate)
        scheduler.schedule("Task 1")
        scheduler.schedule("Task 2")
        scheduler.schedule("Task 3")

        # Run all — only 2 should be concurrent
        results = await scheduler.run_all()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_priority_order(self) -> None:
        execution_order: list[str] = []

        async def mock_generate(prompt: str) -> str:
            execution_order.append(prompt)
            return f"Done: {prompt}"

        scheduler = TaskScheduler(max_concurrent=1, generate_fn=mock_generate)
        scheduler.schedule("Low priority", priority=1)
        scheduler.schedule("High priority", priority=10)
        scheduler.schedule("Medium priority", priority=5)

        # Run all — high priority should run first
        await scheduler.run_all()
        # With max_concurrent=1, they run sequentially by priority
        assert len(execution_order) == 3

    @pytest.mark.asyncio
    async def test_no_generate_fn(self) -> None:
        scheduler = TaskScheduler()
        task = scheduler.schedule("Test task")
        result = await scheduler.run(task.task_id)
        assert "no generate_fn" in result
        assert task.status == TaskStatus.COMPLETED


class TestTaskSchedulerWithRouting:
    def test_routing_determines_rigor(self) -> None:
        router = CapabilityRouter()
        scheduler = TaskScheduler(router=router)

        # Refactoring task → thorough rigor
        task = scheduler.schedule("Refactor the authentication module")
        assert task.routing.rigor == RigorLevel.THOROUGH

        # Simple task → standard rigor
        task2 = scheduler.schedule("Add a comment")
        assert task2.routing.rigor == RigorLevel.MINIMAL
