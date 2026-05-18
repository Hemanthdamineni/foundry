"""StoreBackend ABC — persistence abstraction. Orchestrator never imports aiosqlite."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StoreBackend(ABC):
    """Abstract persistence layer. SQLite now, Postgres later."""

    @abstractmethod
    async def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Create a new task record."""

    @abstractmethod
    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a task by ID."""

    @abstractmethod
    async def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update a task record."""

    @abstractmethod
    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        """List tasks, optionally filtered by status."""

    @abstractmethod
    async def save_phase_output(
        self, task_id: str, phase: str, output: dict[str, Any],
    ) -> None:
        """Append a phase record to a task's history."""

    @abstractmethod
    async def get_history(self, task_id: str) -> list[dict[str, Any]]:
        """Return persisted phase history for a task."""

    @abstractmethod
    async def save_checkpoint(self, task_id: str, checkpoint: dict[str, Any]) -> None:
        """Persist a checkpoint snapshot."""

    @abstractmethod
    async def restore_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        """Load the latest checkpoint for a task."""

    @abstractmethod
    async def checkpoint(self) -> None:
        """Flush or checkpoint the backing store."""

    @abstractmethod
    async def close(self) -> None:
        """Release backend resources."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables and run migrations."""
