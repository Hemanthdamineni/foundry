"""Phase and task enums, records, and execution state models for the SDLC pipeline.

Merges enums and models from:
- Helix/foundry/sdlc/models.py
- Ai-Agent-Server/latest/src/phases.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (merged from both projects)
# ---------------------------------------------------------------------------


class Phase(StrEnum):
    """SDLC pipeline phase identifiers.

    From Ai-Agent-Server phases.py.
    """

    CHATTING = "Chatting"
    SPECS = "Specs"
    PLANNING = "Planning"
    CODING = "Coding"
    REVIEW = "Review"
    DONE = "Done"


def parse_phase(value: str) -> Phase | None:
    """Case-insensitive parse of a string into a Phase."""
    candidate = value.strip().lower()
    for phase in Phase:
        if phase.value.lower() == candidate:
            return phase
    return None


def normalize_phase(value: str | None) -> Phase:
    """Return a valid Phase, defaulting to CHATTING for None/unrecognised."""
    if not value:
        return Phase.CHATTING
    parsed = parse_phase(value)
    if parsed is not None:
        return parsed
    return Phase.CHATTING


class PhaseStatus(StrEnum):
    """Per-phase status within an execution run.

    From Helix models.py.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class TaskStatus(StrEnum):
    """Top-level task lifecycle status (merged from both projects).

    Helix model: ACTIVE, CANCELLED, DONE, STALLED
    Ai-Agent-Server: QUEUED, RUNNING, WAITING_TOOL, DONE, CANCELED, FAILED
    Combined enum includes all unique values (CANCELLED/CANCELED kept distinct).
    """

    # From Ai-Agent-Server
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    CANCELED = "canceled"  # US spelling

    # From Helix
    ACTIVE = "active"
    CANCELLED = "cancelled"  # British spelling
    STALLED = "stalled"

    # Both
    DONE = "done"
    FAILED = "failed"


class FailureType(StrEnum):
    """All failure types from both projects.

    Helix: RETRYABLE_*, TERMINAL_*, ORCHESTRATION_*
    """

    # Retryable failures
    RETRYABLE_MODEL = "model_timeout"
    RETRYABLE_INFRA = "infra_transient"
    RETRYABLE_DEBATE = "debate_timeout"
    RETRYABLE_TOOL = "tool_failure"

    # Terminal failures
    TERMINAL_VALIDATION = "validation_failed"
    TERMINAL_PHASE = "phase_mismatch"
    TERMINAL_SANDBOX = "sandbox_violation"
    TERMINAL_DEPENDENCY = "dependency_gone"
    TERMINAL_CONSENSUS = "consensus_stalemate"
    TERMINAL_SCHEMA = "schema_violation"

    # Orchestration failures
    ORCHESTRATION_CANCELLED = "cancelled"
    ORCHESTRATION_LIMIT = "limit_reached"
    ORCHESTRATION_GATE = "gate_blocked"


class DecisionAction(StrEnum):
    """Action a decision-maker can return after evaluating a step.

    From Helix models.py.
    """

    PROCEED = "proceed"
    RETRY = "retry"
    ABORT = "abort"
    ESCALATE = "escalate"


# ---------------------------------------------------------------------------
# Budget / policy
# ---------------------------------------------------------------------------


class BudgetPolicy(BaseModel):
    """Resource and iteration budgets for a task execution.

    From Helix models.py.
    """

    max_total_tokens: int = 100_000
    max_review_cycles: int = 8
    max_debate_rounds: int = 3
    max_runtime_minutes: int = 60
    fallback_depth: int = 2
    max_debate_budget_tokens: int = 15_000
    memory_enabled: bool = False


# ---------------------------------------------------------------------------
# Execution records and snapshots
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PhaseRecord(BaseModel):
    """Record of one phase execution within a task.

    From Helix models.py.
    """

    phase: str
    status: PhaseStatus = PhaseStatus.PENDING
    output: str | None = None
    model_used: str | None = None
    token_estimate: int | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    lineage: list[dict[str, Any]] | None = None
    iteration_count: int = 0


class ExecutionSnapshot(BaseModel):
    """Immutable snapshot of the execution configuration at a point in time.

    From Helix models.py.
    """

    snapshot_id: str
    created_at: datetime
    graph_template: str
    graph_hash: str
    prompt_hashes: dict[str, str]
    model_routing_hash: str
    judge_schema_hash: str | None = None
    adapter_versions: dict[str, str] = Field(default_factory=dict)
    ollama_models: dict[str, str] = Field(default_factory=dict)


class Checkpoint(BaseModel):
    """Serialisable checkpoint for pausing/resuming a task mid-execution.

    From Helix models.py.
    """

    task_id: str
    phase: str
    history: list[PhaseRecord]
    iteration_count: int
    adapter_states: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    snapshot: ExecutionSnapshot | None = None
    debate_active: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------


class Decision(BaseModel):
    """Structured decision returned by a judge or orchestrator gate.

    From Helix models.py.
    """

    action: DecisionAction
    reason: str
    retry_after_s: int | None = None
    failure_type: FailureType | None = None


# ---------------------------------------------------------------------------
# Task aggregate
# ---------------------------------------------------------------------------


class Task(BaseModel):
    """Top-level task aggregate used by the orchestrator.

    From Helix models.py.
    """

    task_id: str
    description: str
    mode: str = "feature"
    status: TaskStatus = TaskStatus.ACTIVE
    current_phase: str = "Chatting"
    history: list[PhaseRecord] = Field(default_factory=list)
    iteration_count: int = 0
    retry_count: int = 0
    last_failure_reason: str | None = None
    last_failure_type: str | None = None
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    snapshot: ExecutionSnapshot | None = None
    locked_prompts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    requires_approval: bool = False


__all__ = [
    "Phase",
    "parse_phase",
    "normalize_phase",
    "PhaseStatus",
    "TaskStatus",
    "FailureType",
    "DecisionAction",
    "BudgetPolicy",
    "PhaseRecord",
    "ExecutionSnapshot",
    "Checkpoint",
    "Decision",
    "Task",
]
