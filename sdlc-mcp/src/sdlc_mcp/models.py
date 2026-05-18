"""Shared data models for the SDLC server."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PhaseStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class TaskStatus(enum.StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    DONE = "done"
    STALLED = "stalled"


class FailureType(enum.StrEnum):
    RETRYABLE_MODEL = "model_timeout"
    RETRYABLE_INFRA = "infra_transient"
    RETRYABLE_DEBATE = "debate_timeout"
    TERMINAL_VALIDATION = "validation_failed"
    TERMINAL_PHASE = "phase_mismatch"
    TERMINAL_SANDBOX = "sandbox_violation"
    TERMINAL_DEPENDENCY = "dependency_gone"
    TERMINAL_CONSENSUS = "consensus_stalemate"
    ORCHESTRATION_CANCELLED = "cancelled"
    ORCHESTRATION_LIMIT = "limit_reached"
    ORCHESTRATION_GATE = "gate_blocked"


class DecisionAction(enum.StrEnum):
    PROCEED = "proceed"
    RETRY = "retry"
    ABORT = "abort"
    ESCALATE = "escalate"


class BudgetPolicy(BaseModel):
    max_total_tokens: int = 100_000
    max_review_cycles: int = 8
    max_debate_rounds: int = 3
    max_runtime_minutes: int = 60
    fallback_depth: int = 2
    max_debate_budget_tokens: int = 15_000
    memory_enabled: bool = False


class PhaseRecord(BaseModel):
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
    task_id: str
    phase: str
    history: list[PhaseRecord]
    iteration_count: int
    adapter_states: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    snapshot: ExecutionSnapshot | None = None
    debate_active: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """Structured verdict from the JudgeEngine evaluation."""

    passed: bool
    reason: str
    issues: list[str] = Field(default_factory=list)
    severity: str = "info"  # "info", "warning", "error", "critical"


class Task(BaseModel):
    task_id: str
    description: str
    mode: str = "feature"
    status: TaskStatus = TaskStatus.ACTIVE
    current_phase: str = "Chatting"
    history: list[PhaseRecord] = Field(default_factory=list)
    iteration_count: int = 0
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    snapshot: ExecutionSnapshot | None = None
    locked_prompts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    requires_approval: bool = False


class Decision(BaseModel):
    action: DecisionAction
    reason: str
    retry_after_s: int | None = None
    failure_type: FailureType | None = None


class WriteOp(BaseModel):
    target: str
    action: str
    payload: dict[str, Any]
    source_span: str | None = None


class SymbolKind(enum.StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    UNKNOWN = "unknown"


class CodeSymbol(BaseModel):
    name: str
    kind: SymbolKind = SymbolKind.UNKNOWN
    file_path: str
    start_line: int = 0
    end_line: int = 0
    parent: str | None = None
    docstring: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportInfo(BaseModel):
    source: str
    alias: str | None = None
    file_path: str
    line: int = 0
    is_relative: bool = False


class FileIndex(BaseModel):
    path: str
    language: str = "unknown"
    symbols: list[CodeSymbol] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    mtime: float = 0.0
    sha256: str = ""
    size_bytes: int = 0
    indexed_at: str = ""


class DependencyGraph(BaseModel):
    files: dict[str, FileIndex] = Field(default_factory=dict)
    import_edges: dict[str, list[str]] = Field(default_factory=dict)
    dependents: dict[str, list[str]] = Field(default_factory=dict)
    indexed_at: str = ""
    file_count: int = 0
    symbol_count: int = 0


class ContextChunk(BaseModel):
    file_path: str
    language: str = "unknown"
    content: str
    start_line: int = 0
    end_line: int = 0
    symbol_name: str | None = None
    symbol_kind: str | None = None
    relevance_score: float = 0.0


class DebateAgentRole(enum.StrEnum):
    SPECS = "specs"
    PLANNING = "planning"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    CONSENSUS = "consensus"


class DebateAgentConfig(BaseModel):
    role: DebateAgentRole
    model: str = "qwen3:8b"
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024


class MinorityReport(BaseModel):
    agent_role: str
    objection: str
    round_number: int
    severity: str = "info"


class CollapseSignal(BaseModel):
    detected: bool = False
    confidence: float = 0.0
    reason: str = ""


class DebateRound(BaseModel):
    round_number: int
    responses: dict[str, str] = Field(default_factory=dict)
    previous_responses: dict[str, str] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""


class ConsensusResult(BaseModel):
    reached: bool = False
    passed: bool = False
    reason: str = ""
    disagreement_areas: list[str] = Field(default_factory=list)
    round_count: int = 0
    agent_verdicts: dict[str, bool] = Field(default_factory=dict)
    minority_reports: list[MinorityReport] = Field(default_factory=list)
    collapse_signal: CollapseSignal = Field(default_factory=CollapseSignal)
    residual_objections: list[str] = Field(default_factory=list)


class DebateTranscript(BaseModel):
    task_id: str
    phase: str
    output_preview: str = ""
    rounds: list[DebateRound] = Field(default_factory=list)
    consensus: ConsensusResult | None = None
    total_tokens_estimate: int = 0


class Engram(BaseModel):
    engram_id: str
    task_id: str
    phase: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str = "unknown"
    importance: float = 0.5
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexConfig(BaseModel):
    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.py",
            "*.js",
            "*.ts",
            "*.jsx",
            "*.tsx",
            "*.rs",
            "*.go",
            "*.java",
            "*.yaml",
            "*.yml",
            "*.json",
            "*.md",
        ],
    )
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.pyc",
            "__pycache__/*",
            ".git/*",
            "node_modules/*",
            ".pixi/*",
            ".venv/*",
            "data/*",
            ".opencode/*",
        ],
    )
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20
