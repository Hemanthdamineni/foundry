# Schemas and Contracts

> All Pydantic data models, enums, file formats, and serialization contracts.

---

## Core Enums

### TaskStatus

```python
class TaskStatus(StrEnum):
    ACTIVE     = "active"
    COMPLETED  = "completed"
    STALLED    = "stalled"      # Budget exhausted or irrecoverable failure
    CANCELLED  = "cancelled"
```

### PhaseStatus

```python
class PhaseStatus(StrEnum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    SKIPPED     = "skipped"
```

### SymbolKind

```python
class SymbolKind(StrEnum):
    FUNCTION = "function"
    METHOD   = "method"
    CLASS    = "class"
    VARIABLE = "variable"
    UNKNOWN  = "unknown"
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
    iteration_count: int = 0
    history: list[PhaseRecord] = []
    budget: BudgetPolicy = BudgetPolicy()
    locked_prompts: dict[str, str] = {}
    snapshot: ExecutionSnapshot | None = None
    affected_files: list[str] = []
    created_at: str = ""
    updated_at: str = ""
```

### PhaseRecord

```python
class PhaseRecord(BaseModel):
    phase: str
    status: PhaseStatus = PhaseStatus.PENDING
    output: str | None = None
    verdict: str | None = None
    token_estimate: int | None = None
    created_at: str = ""
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
    history: list[PhaseRecord] = []
    iteration_count: int = 0
    adapter_states: dict[str, Any] = {}
    snapshot: ExecutionSnapshot | None = None
    created_at: str = ""
```

### ExecutionSnapshot

```python
class ExecutionSnapshot(BaseModel):
    snapshot_id: str = ""
    created_at: str = ""
    graph_template: str = ""
    graph_hash: str = ""
    prompt_hashes: dict[str, str] = {}
    model_routing_hash: str = ""
    judge_schema_hash: str | None = None
    adapter_versions: dict[str, str] = {}
    ollama_models: dict[str, str] = {}
```

### WriteOp

```python
class WriteOp(BaseModel):
    target: str          # "task", "phase", "checkpoint", "memory"
    action: str          # "create", "update", "save"
    payload: dict[str, Any] = {}
    source_span: str = ""
```

---

## Indexing Models

### FileIndex

```python
class FileIndex(BaseModel):
    path: str
    language: str
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
    kind: SymbolKind
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    parent: str | None = None
    docstring: str | None = None
```

### ImportInfo

```python
class ImportInfo(BaseModel):
    source: str
    alias: str | None = None
    file_path: str = ""
    line: int = 0
    is_relative: bool = False
```

### DependencyGraph

```python
class DependencyGraph(BaseModel):
    files: dict[str, FileIndex] = {}
    import_edges: dict[str, list[str]] = {}
    dependents: dict[str, list[str]] = {}
    indexed_at: str | None = None
    file_count: int = 0
    symbol_count: int = 0
```

### ContextChunk

```python
class ContextChunk(BaseModel):
    file_path: str = ""
    language: str = ""
    content: str = ""
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
    include_patterns: list[str] = ["*.py", "*.js", ...]
    exclude_patterns: list[str] = ["*.pyc", ".git/*", ...]
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20
```

---

## Debate Models

### DebateTranscript

```python
class DebateTranscript(BaseModel):
    rounds: list[dict[str, str]] = []   # [{agent_role: response}, ...]
    final_verdict: str = ""
    agent_configs: list[dict] = []
    total_rounds: int = 0
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
    minority_reports: list[dict] = []
    collapse_signal: dict = {}
    residual_objections: list[str] = []
```

---

## File Formats

### JSONL Trace File (`data/traces/{id}.jsonl`)

```json
{"span_id": "abc", "phase": "Coding", "tool": "submit_output", "input": {...}, "output": {...}, "timestamp": "...", "duration_ms": 1234}
{"span_id": "def", "phase": "Testing", "tool": "get_next_action", "input": {...}, "output": {...}, "timestamp": "...", "duration_ms": 567}
```

### JSONL Engram File (`data/memory/engrams.jsonl`)

```json
{"content": "ImportError in auth module", "tags": ["error", "import", "auth"], "task_id": "abc123", "phase": "Coding", "timestamp": "..."}
```

### Checkpoint File (`data/checkpoints/{task_id}_v{N}.json`)

```json
{"task_id": "abc123", "phase": "Planning", "history": [...], "iteration_count": 2, "snapshot": {...}, "created_at": "..."}
```

---

## Exception Hierarchy

```python
class SDLCError(Exception): ...                        # Base
class ConfigError(SDLCError): ...                       # Configuration problems
class PhaseError(SDLCError): ...                        # Phase transition failures
class ValidationError(SDLCError): ...                   # Output validation failures
class BudgetExhaustedError(SDLCError): ...              # Budget ceiling hit
class CheckpointError(SDLCError): ...                   # Checkpoint save/restore failures
class StoreError(SDLCError): ...                        # Database failures
class RecoveryError(SDLCError): ...                     # Recovery escalation failures
class DriftError(SDLCError): ...                        # Architectural drift detected
class ToolError(SDLCError): ...                         # External tool failures
```
