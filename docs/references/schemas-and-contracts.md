# Schemas and Contracts

> All Pydantic data models, enums, file formats, and serialization contracts — verified against `sdlc/models.py` and `sdlc/exceptions.py`.

---

## Core Enums

### TaskStatus

```python
class TaskStatus(StrEnum):
    ACTIVE    = "active"
    CANCELLED = "cancelled"
    DONE      = "done"
    STALLED   = "stalled"
```

### PhaseStatus

```python
class PhaseStatus(StrEnum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED   = "submitted"
    ACCEPTED    = "accepted"
    REJECTED    = "rejected"
    SKIPPED     = "skipped"
```

### DecisionAction

```python
class DecisionAction(StrEnum):
    PROCEED  = "proceed"
    RETRY    = "retry"
    ABORT    = "abort"
    ESCALATE = "escalate"
```

### FailureType

```python
class FailureType(StrEnum):
    RETRYABLE_MODEL       = "model_timeout"
    RETRYABLE_INFRA       = "infra_transient"
    RETRYABLE_DEBATE      = "debate_timeout"
    TERMINAL_VALIDATION   = "validation_failed"
    TERMINAL_PHASE        = "phase_mismatch"
    TERMINAL_SANDBOX      = "sandbox_violation"
    TERMINAL_DEPENDENCY   = "dependency_gone"
    TERMINAL_CONSENSUS    = "consensus_stalemate"
    ORCHESTRATION_CANCELLED = "cancelled"
    ORCHESTRATION_LIMIT   = "limit_reached"
    ORCHESTRATION_GATE    = "gate_blocked"
```

### SymbolKind

```python
class SymbolKind(StrEnum):
    MODULE     = "module"
    CLASS      = "class"
    FUNCTION   = "function"
    METHOD     = "method"
    VARIABLE   = "variable"
    CONSTANT   = "constant"
    IMPORT     = "import"
    INTERFACE  = "interface"
    TYPE_ALIAS = "type_alias"
    UNKNOWN    = "unknown"
```

### DebateAgentRole

```python
class DebateAgentRole(StrEnum):
    SPECS     = "specs"
    PLANNING  = "planning"
    CODING    = "coding"
    REVIEW    = "review"
    TESTING   = "testing"
    CONSENSUS = "consensus"
```

### ToolCapability

```python
class ToolCapability(StrEnum):
    LINT       = "lint"
    TYPING     = "typing"
    TESTING    = "testing"
    CODE_GRAPH = "code_graph"
    SANDBOX    = "sandbox"
    VERSIONING = "versioning"
    WORKFLOW   = "workflow"
```

---

## Core Models

### Task

```python
class Task(BaseModel):
    task_id: str
    description: str
    mode: str = "feature"
    status: TaskStatus = TaskStatus.ACTIVE
    current_phase: str = "Chatting"
    history: list[PhaseRecord] = []
    iteration_count: int = 0
    budget: BudgetPolicy = BudgetPolicy()
    snapshot: ExecutionSnapshot | None = None
    locked_prompts: dict[str, str] = {}
    created_at: datetime = _utc_now()
    updated_at: datetime = _utc_now()
    requires_approval: bool = False
```

### PhaseRecord

```python
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
```

### JudgeVerdict

```python
class JudgeVerdict(BaseModel):
    passed: bool
    reason: str
    issues: list[str] = []
    severity: str = "info"     # "info" | "warning" | "error" | "critical"
```

### Decision

```python
class Decision(BaseModel):
    action: DecisionAction
    reason: str
    retry_after_s: int | None = None
    failure_type: FailureType | None = None
```

### BudgetPolicy

```python
class BudgetPolicy(BaseModel):
    max_total_tokens: int = 100_000
    max_review_cycles: int = 8
    max_debate_rounds: int = 3
    max_runtime_minutes: int = 60
    fallback_depth: int = 2
    max_debate_budget_tokens: int = 15_000
    memory_enabled: bool = False
```

### Checkpoint

```python
class Checkpoint(BaseModel):
    task_id: str
    phase: str
    history: list[PhaseRecord]
    iteration_count: int
    adapter_states: dict[str, Any] = {}
    created_at: datetime = _utc_now()
    snapshot: ExecutionSnapshot | None = None
    debate_active: list[str] = []
```

### ExecutionSnapshot

```python
class ExecutionSnapshot(BaseModel):
    snapshot_id: str
    created_at: datetime
    graph_template: str
    graph_hash: str
    prompt_hashes: dict[str, str]
    model_routing_hash: str
    judge_schema_hash: str | None = None
    adapter_versions: dict[str, str] = {}
    ollama_models: dict[str, str] = {}
```

### WriteOp

```python
class WriteOp(BaseModel):
    target: str              # "task", "phase", "checkpoint", "memory"
    action: str              # "create", "update", "save"
    payload: dict[str, Any]
    source_span: str | None = None
```

---

## Indexing Models

### FileIndex

```python
class FileIndex(BaseModel):
    path: str
    language: str = "unknown"
    symbols: list[CodeSymbol] = []
    imports: list[ImportInfo] = []
    mtime: float = 0.0
    sha256: str = ""
    size_bytes: int = 0
    indexed_at: str = ""
```

### CodeSymbol

```python
class CodeSymbol(BaseModel):
    name: str
    kind: SymbolKind = SymbolKind.UNKNOWN
    file_path: str
    start_line: int = 0
    end_line: int = 0
    parent: str | None = None
    docstring: str | None = None
    metadata: dict[str, Any] = {}
```

### ImportInfo

```python
class ImportInfo(BaseModel):
    source: str
    alias: str | None = None
    file_path: str
    line: int = 0
    is_relative: bool = False
```

### DependencyGraph

```python
class DependencyGraph(BaseModel):
    files: dict[str, FileIndex] = {}
    import_edges: dict[str, list[str]] = {}
    dependents: dict[str, list[str]] = {}
    indexed_at: str = ""
    file_count: int = 0
    symbol_count: int = 0
```

### ContextChunk

```python
class ContextChunk(BaseModel):
    file_path: str
    language: str = "unknown"
    content: str
    start_line: int = 0
    end_line: int = 0
    symbol_name: str | None = None
    symbol_kind: str | None = None
    relevance_score: float = 0.0
```

### IndexConfig

```python
class IndexConfig(BaseModel):
    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: list[str] = ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
                                    "*.rs", "*.go", "*.java", "*.yaml", "*.yml",
                                    "*.json", "*.md"]
    exclude_patterns: list[str] = ["*.pyc", "__pycache__/*", ".git/*",
                                    "node_modules/*", ".pixi/*", ".venv/*",
                                    "data/*", ".opencode/*"]
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20
```

---

## Debate Models

### DebateAgentConfig

```python
class DebateAgentConfig(BaseModel):
    role: DebateAgentRole
    model: str = "qwen3:8b"
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024
```

### DebateRound

```python
class DebateRound(BaseModel):
    round_number: int
    responses: dict[str, str] = {}
    previous_responses: dict[str, str] = {}
    started_at: str = ""
    completed_at: str = ""
```

### DebateTranscript

```python
class DebateTranscript(BaseModel):
    task_id: str
    phase: str
    output_preview: str = ""
    rounds: list[DebateRound] = []
    consensus: ConsensusResult | None = None
    total_tokens_estimate: int = 0
```

### ConsensusResult

```python
class ConsensusResult(BaseModel):
    reached: bool = False
    passed: bool = False
    reason: str = ""
    disagreement_areas: list[str] = []
    round_count: int = 0
    agent_verdicts: dict[str, bool] = {}
    minority_reports: list[MinorityReport] = []
    collapse_signal: CollapseSignal = CollapseSignal()
    residual_objections: list[str] = []
```

### MinorityReport

```python
class MinorityReport(BaseModel):
    agent_role: str
    objection: str
    round_number: int
    severity: str = "info"
```

### CollapseSignal

```python
class CollapseSignal(BaseModel):
    detected: bool = False
    confidence: float = 0.0
    reason: str = ""
```

### Engram

```python
class Engram(BaseModel):
    engram_id: str
    task_id: str
    phase: str
    content: str
    tags: list[str] = []
    source: str = "unknown"
    importance: float = 0.5
    created_at: str = ""
    metadata: dict[str, Any] = {}
```

---

## Exception Hierarchy

Source: `sdlc/exceptions.py`

```python
class SDLCError(Exception):            # Base — accepts failure_type: str, details: dict
class ConfigError(SDLCError): ...      # Configuration loading or validation
class StoreError(SDLCError): ...       # Persistence layer
class PhaseError(SDLCError): ...       # Phase transition or validation
class ToolError(SDLCError): ...        # Tool adapter execution
class PolicyError(SDLCError): ...      # Execution policy decisions
class CheckpointError(SDLCError): ...  # Checkpoint save/restore
class SandboxError(SDLCError): ...     # Sandbox execution isolation
class DebateError(SDLCError): ...      # Debate runtime or consensus
class JudgeError(SDLCError): ...       # Judge evaluation
class ModelError(SDLCError): ...       # Model routing or inference
class CodeGraphError(SDLCError): ...   # Code graph / AST parsing
```
