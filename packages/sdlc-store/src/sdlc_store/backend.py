"""StoreBackend ABC — persistence abstraction combining Foundry and Ai-Agent patterns."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StoreBackend(ABC):
    """Abstract persistence layer. SQLite now, Postgres later."""

    # ------------------------------------------------------------------ #
    #  Core CRUD (Foundry-compatible)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Create a new task record from a dict (Foundry style).

        The dict is stored as a JSON blob in the ``data`` column.
        """

    @abstractmethod
    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a task by ID (Foundry style — deserialises ``data`` column)."""

    @abstractmethod
    async def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update a task record with partial merge into the ``data`` blob."""

    @abstractmethod
    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        """List tasks, optionally filtered by status (read from ``data`` blob)."""

    # ------------------------------------------------------------------ #
    #  Phase history (Foundry-compatible)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def save_phase_output(
        self, task_id: str, phase: str, output: dict[str, Any],
    ) -> None:
        """Append a phase record to a task's history."""

    @abstractmethod
    async def get_history(self, task_id: str) -> list[dict[str, Any]]:
        """Return persisted phase history for a task."""

    # ------------------------------------------------------------------ #
    #  Checkpoints (Foundry-compatible)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def save_checkpoint(self, task_id: str, checkpoint: dict[str, Any]) -> None:
        """Persist a checkpoint snapshot."""

    @abstractmethod
    async def restore_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        """Load the latest checkpoint for a task."""

    # ------------------------------------------------------------------ #
    #  Store lifecycle
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def checkpoint(self) -> None:
        """Flush or checkpoint the backing store (WAL checkpoint)."""

    @abstractmethod
    async def backup(self) -> str:
        """Create an online backup of the backing store. Returns the backup path."""

    @abstractmethod
    async def close(self) -> None:
        """Release backend resources."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables and run migrations."""

    # ------------------------------------------------------------------ #
    #  Task lifecycle (Ai-Agent-compatible)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def create_task_v2(
        self,
        *,
        prompt: str,
        repo_path: str,
        priority: str,
        mode: str,
        status: str,
        current_phase: str,
        chat_only: bool = False,
    ) -> dict[str, Any]:
        """Create a task using individual columns (Ai-Agent style)."""

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """Mark a task as canceled. Returns True if a row was updated."""

    @abstractmethod
    async def resume_task(self, task_id: str) -> bool:
        """Re-queue a canceled or failed task."""

    @abstractmethod
    async def list_runnable_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return tasks eligible for execution (QUEUED)."""

    @abstractmethod
    async def list_runnable_tasks_with_options(
        self,
        *,
        limit: int = 20,
        include_running: bool = False,
    ) -> list[dict[str, Any]]:
        """Return runnable tasks, optionally including RUNNING."""

    @abstractmethod
    async def try_mark_task_running(
        self,
        *,
        task_id: str,
        expected_phase: str,
        expected_updated_at: str,
    ) -> bool:
        """Optimistic CAS to transition a task from QUEUED to RUNNING."""

    @abstractmethod
    async def recover_incomplete_tasks(self) -> int:
        """Move RUNNING tasks back to QUEUED on startup."""

    @abstractmethod
    async def abandon_inflight_work(self) -> dict[str, int]:
        """Mark leftover inflight work as terminal. Returns counts."""

    # ------------------------------------------------------------------ #
    #  Phase runs & transitions (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def record_phase_run(
        self,
        *,
        task_id: str,
        phase: str,
        model: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        retry_count: int,
        status: str,
    ) -> str:
        """Record a phase execution attempt. Returns the run_id."""

    @abstractmethod
    async def list_completed_phases(self, task_id: str) -> set[str]:
        """Return distinct validated transition targets for a task."""

    @abstractmethod
    async def record_transition(
        self,
        *,
        task_id: str,
        from_phase: str,
        to_phase: str,
        reason: str,
        failure_class: str,
        confidence: float,
        validated: bool,
    ) -> str:
        """Record a phase transition and update transition_stats."""

    @abstractmethod
    async def apply_phase_step_transaction(
        self,
        *,
        task_id: str,
        from_phase: str,
        to_phase: str,
        model: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        phase_run_status: str,
        reason: str,
        failure_class: str,
        confidence: float,
        validated: bool,
        next_status: str,
        branch_name: str | None,
        model_calls: int = 1,
    ) -> tuple[str, str]:
        """Atomic phase-step commit: phase_run + transition + budget + task update."""

    @abstractmethod
    async def last_transition(self, task_id: str) -> dict[str, Any] | None:
        """Return the most recent transition for a task."""

    # ------------------------------------------------------------------ #
    #  Tool requests / results (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def enqueue_tool_request(
        self,
        *,
        task_id: str,
        phase: str,
        kind: str,
        tool_name: str,
        payload: dict[str, Any],
        attempt: int = 1,
        not_before: int | None = None,
    ) -> dict[str, Any]:
        """Enqueue a tool request for async execution."""

    @abstractmethod
    async def get_tool_request(self, request_id: str) -> dict[str, Any] | None:
        """Retrieve a tool request record."""

    @abstractmethod
    async def has_inflight_tool_request(
        self,
        *,
        task_id: str,
        phase: str | None = None,
        kind: str | None = None,
        tool_name: str | None = None,
    ) -> bool:
        """Check if a task has pending or claimed tool requests (optionally filtered)."""

    @abstractmethod
    async def claim_tool_requests(
        self,
        *,
        worker_id: str,
        max_items: int,
        lease_seconds: int,
        heartbeat_timeout_seconds: int,
        requeue_stale: bool = True,
    ) -> list[dict[str, Any]]:
        """Claim pending tool requests for a worker."""

    @abstractmethod
    async def store_tool_result(
        self,
        *,
        request_id: str,
        status: str,
        claim_token: str,
        resume_token: str,
        version: int,
        output_payload: dict[str, Any],
        logs: str,
        exit_code: int | None,
        error_message: str | None,
        failure_class: str | None,
    ) -> tuple[str, bool]:
        """Store a tool execution result. Returns (result_id, was_already_stored)."""

    @abstractmethod
    async def next_unconsumed_tool_result(self, task_id: str) -> dict[str, Any] | None:
        """Return the oldest unconsumed tool result for a task."""

    @abstractmethod
    async def mark_tool_result_consumed(self, result_id: str) -> None:
        """Mark a tool result as consumed."""

    # ------------------------------------------------------------------ #
    #  Budgets (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def update_budget(
        self,
        *,
        task_id: str,
        phase: str,
        model_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Upsert budget counters for a task+phase."""

    @abstractmethod
    async def get_budgets(self, task_id: str) -> list[dict[str, Any]]:
        """Return budget rows for a task."""

    # ------------------------------------------------------------------ #
    #  Model cache (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def set_model_warm_state(
        self, *, model_id: str, role: str, warm: bool,
    ) -> None:
        """Set the warm/cold state of a model."""

    @abstractmethod
    async def warm_models(self) -> list[dict[str, Any]]:
        """Return all models currently marked warm."""

    # ------------------------------------------------------------------ #
    #  Nightly jobs (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def set_nightly_job(
        self,
        *,
        scheduled_for: str,
        status: str,
        task_id: str | None,
        branch_name: str,
    ) -> str:
        """Create a nightly job record."""

    @abstractmethod
    async def get_last_nightly_job_for_date(
        self, scheduled_for: str,
    ) -> dict[str, Any] | None:
        """Return the most recent nightly job for a date string."""

    # ------------------------------------------------------------------ #
    #  Audit events (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def add_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
    ) -> str:
        """Append an audit event."""

    @abstractmethod
    async def task_events(
        self, task_id: str, limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return audit events for a task."""

    # ------------------------------------------------------------------ #
    #  Bridge workers (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def update_worker_heartbeat(
        self, *, worker_id: str, metadata: dict[str, Any],
    ) -> None:
        """Upsert a bridge-worker heartbeat."""

    @abstractmethod
    async def mark_offline_workers(
        self, *, heartbeat_timeout_seconds: int,
    ) -> list[str]:
        """Mark workers as offline past the heartbeat timeout. Returns their IDs."""

    @abstractmethod
    async def has_online_bridge_workers(
        self, *, heartbeat_timeout_seconds: int,
    ) -> bool:
        """Check if any bridge workers are online."""

    @abstractmethod
    async def requeue_stale_claims(
        self, *, heartbeat_timeout_seconds: int,
    ) -> int:
        """Requeue tool-request claims held by offline workers or with expired leases."""

    # ------------------------------------------------------------------ #
    #  State snapshot (Ai-Agent)
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def task_state_snapshot(self, task_id: str) -> dict[str, Any]:
        """Return a full state snapshot for a task (task + runs + transitions + tool data)."""
