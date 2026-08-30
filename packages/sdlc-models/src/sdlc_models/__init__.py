"""sdlc-models: Shared data models for the Helix SDLC pipeline.

This package provides a single source of truth for enums, Pydantic
schemas, configuration models, and exceptions used across the SDLC
orchestrator, judge engine, debate system, indexing pipeline, and
persistence layer.

It merges models from two codebases:
- Helix/foundry/sdlc/models.py, config.py, exceptions.py
- Ai-Agent-Server/latest/src/phases.py, schemas.py
"""

from __future__ import annotations

from sdlc_models.phases import (
    BudgetPolicy,
    Checkpoint,
    Decision,
    DecisionAction,
    ExecutionSnapshot,
    FailureType,
    Phase,
    PhaseRecord,
    PhaseStatus,
    Task,
    TaskStatus,
    normalize_phase,
    parse_phase,
)
from sdlc_models.judge import JudgeVerdict, ReviewDecision
from sdlc_models.debate import (
    CollapseSignal,
    ConsensusResult,
    DebateAgentConfig,
    DebateAgentRole,
    DebateRound,
    DebateTranscript,
    Engram,
    MinorityReport,
)
from sdlc_models.schemas import (
    CodeSymbol,
    CodingOutput,
    ContextChunk,
    DependencyGraph,
    DoneOutput,
    FileIndex,
    ImportInfo,
    PlanOutput,
    ReviewOutput,
    SpecOutput,
    SymbolKind,
    WriteOp,
)
from sdlc_models.config import (
    IndexConfigModel,
    LLMConfig,
    LLMProviderConfig,
    LLMRoutingConfig,
    LoggingConfig,
    SandboxConfig,
    SDLCSettings,
    StoreConfig,
)
from sdlc_models.exceptions import (
    SDLCError,
    CheckpointError,
    CodeGraphError,
    ConfigError,
    DebateError,
    JudgeError,
    ModelError,
    OrchestratorError,
    PhaseError,
    PhaseGraphError,
    PolicyError,
    SandboxError,
    SchemaViolationError,
    StoreError,
    ToolError,
)

__all__ = [
    # phases
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
    # judge
    "ReviewDecision",
    "JudgeVerdict",
    # debate
    "DebateAgentRole",
    "DebateAgentConfig",
    "MinorityReport",
    "CollapseSignal",
    "DebateRound",
    "ConsensusResult",
    "DebateTranscript",
    "Engram",
    # schemas
    "SpecOutput",
    "PlanOutput",
    "CodingOutput",
    "ReviewOutput",
    "DoneOutput",
    "SymbolKind",
    "CodeSymbol",
    "ImportInfo",
    "FileIndex",
    "DependencyGraph",
    "ContextChunk",
    "WriteOp",
    # config
    "IndexConfigModel",
    "LoggingConfig",
    "StoreConfig",
    "SandboxConfig",
    "LLMProviderConfig",
    "LLMRoutingConfig",
    "LLMConfig",
    "SDLCSettings",
    # exceptions
    "SDLCError",
    "ConfigError",
    "StoreError",
    "PhaseError",
    "ToolError",
    "PolicyError",
    "CheckpointError",
    "SandboxError",
    "DebateError",
    "JudgeError",
    "ModelError",
    "CodeGraphError",
    "PhaseGraphError",
    "OrchestratorError",
    "SchemaViolationError",
]
