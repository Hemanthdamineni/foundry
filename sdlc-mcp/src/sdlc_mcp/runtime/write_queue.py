"""WriteQueue — single-worker serialized persistence writer. Prevents SQLite write contention."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from enum import StrEnum

from sdlc_mcp.models import WriteOp


class QueueTarget(StrEnum):
    TASK = "task"
    TRACE = "trace"
    CHECKPOINT = "checkpoint"
    PHASE_OUTPUT = "phase_output"
    MEMORY = "memory"
    DELEGATION = "delegation"


WriteHandler = Callable[[WriteOp], Awaitable[None] | None]


class WriteQueue:
    """Single-worker serialized writer. Enqueue from any coroutine; FIFO drain in background."""

    def __init__(self, handler: WriteHandler | None = None) -> None:
        self._queue: asyncio.Queue[WriteOp] = asyncio.Queue()
        self._handler = handler
        self._worker_task: asyncio.Task[None] | None = None
        self._last_error: BaseException | None = None
        self._running = False

    def set_handler(self, handler: WriteHandler) -> None:
        self._handler = handler

    async def enqueue(self, op: WriteOp) -> None:
        self._raise_if_failed()
        await self._queue.put(op)

    async def flush(self) -> None:
        await self._queue.join()
        self._raise_if_failed()

    async def checkpoint(self) -> None:
        await self.flush()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_error = None
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        await self.flush()
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                op = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            try:
                if self._handler:
                    result = self._handler(op)
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:  # noqa: BLE001
                self._last_error = exc
            finally:
                self._queue.task_done()

    def _raise_if_failed(self) -> None:
        if self._last_error is None:
            return
        msg = "WriteQueue handler failed"
        raise RuntimeError(msg) from self._last_error

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()


__all__ = ["QueueTarget", "WriteHandler", "WriteQueue"]
