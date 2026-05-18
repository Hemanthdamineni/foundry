# Execution & Validation

> How Foundry produces code, validates quality, manages tool interactions, and connects to external systems through the MCP protocol.

---

## MCP Server Architecture

### What It Is

Foundry's execution layer is an **MCP (Model Context Protocol) server** built on `FastMCP`. It exposes a set of tools that a host agent (e.g., OpenCode, Claude Desktop) can call to drive the SDLC lifecycle. The server is the bridge between the AI agent's natural language reasoning and the deterministic runtime.

### Server Bootstrap (Lifespan)

When the MCP server starts, the `lifespan` function initializes all subsystems in order:

```
1. Ensure data directories exist
2. Bootstrap structured logging
3. Load phase graph from YAML
4. Load model routing from YAML
5. Validate model routing covers all phases
6. Initialize SQLite store
7. Create ExecutionPolicy + OrchestratorFSM
8. Create CheckpointManager
9. (Optional) Initialize Acervo memory system
10. Create WriteQueue + WriteHandler
11. Build LLM providers (Ollama, OpenAI)
12. Resolve default provider + model router
13. Initialize JudgeEngine with routed provider
14. Initialize Tracer with retention enforcement
15. Initialize DebateRuntime with routed provider
16. Initialize IndexPipeline for workspace indexing
17. Run incremental index
18. Package everything into SDLCAppContext
19. Yield context → server is live
```

On shutdown:
```
1. Stop WriteQueue (drain pending writes)
2. Checkpoint SQLite store
3. Close store connection
```

### SDLCAppContext

Every tool call receives the shared application context:

```python
class SDLCAppContext:
    store: StoreBackend            # SQLite persistence
    checkpoint_mgr: CheckpointManager
    orchestrator: OrchestratorFSM  # Phase state machine
    policy: ExecutionPolicy        # Budget/retry decisions
    write_queue: WriteQueue        # Async write pipeline
    graph: PhaseGraph              # Phase graph definition
    model_routing: dict            # Phase → model mapping
    config: dict                   # Runtime config
    judge_engine: JudgeEngine      # Per-phase evaluation
    tracer: Tracer                 # Distributed tracing
    index_pipeline: IndexPipeline  # Workspace indexing
    debate_runtime: DebateRuntime  # Multi-agent debate
    acervo: Acervo | None          # Cross-task memory
    memory_adapter: MemoryAdapter  # Memory API
```

---

## MCP Tool Surface

### Core Lifecycle Tools

These tools drive the SDLC loop:

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `sdlc_create_task` | `description`, `mode` | `{task_id, status}` | Create a new SDLC task |
| `sdlc_get_next_action` | `task_id` | `{phase, model, prompt, context}` | Get what to do next |
| `sdlc_submit_output` | `task_id`, `phase`, `output` | `{accepted, next_phase, issues}` | Submit phase output for review |
| `sdlc_request_approval` | `task_id`, `phase`, `summary` | `{approved}` | Human-in-the-loop gate |

### Management Tools

| Tool | Purpose |
|---|---|
| `sdlc_get_status(task_id)` | Full task status with phase history |
| `sdlc_list_tasks(status?)` | List all tasks, optionally filtered |
| `sdlc_cancel_task(task_id)` | Cancel an active task |

### Debug Tools

| Tool | Purpose |
|---|---|
| `sdlc_get_trace(trace_id)` | Read trace spans |
| `sdlc_list_traces(task_id?)` | List available traces |
| `sdlc_get_summaries()` | Read trace summaries |
| `sdlc_enforce_retention()` | Trigger trace cleanup |

### Index Tools

| Tool | Purpose |
|---|---|
| `sdlc_index_repository(mode)` | Full or incremental workspace index |
| `sdlc_index_files(paths)` | Index specific files |
| `sdlc_get_dependency_context(file)` | Get dependency graph for a file |
| `sdlc_get_index_stats()` | Index statistics |

---

## The Submit Output Flow

`sdlc_submit_output` is the most complex tool — it's where all the subsystems converge:

```
Host agent calls: sdlc_submit_output(task_id, "Coding", output)
│
├─ 1. Load task from store
│
├─ 2. Validate phase matches current task phase
│
├─ 3. Check budget (ExecutionPolicy.check_budget)
│      └─ If budget exceeded → return ABORT
│
├─ 4. Run JudgeEngine evaluation
│      ├─ Judge passes → continue
│      └─ Judge fails → increment iteration, return rejection
│
├─ 5. If debate is configured for this phase:
│      ├─ Run DebateRuntime.run_debate()
│      │   ├─ 3-round protocol
│      │   └─ ConsensusEngine evaluation
│      ├─ If consensus.passed → continue
│      └─ If consensus.failed → increment iteration, return rejection
│
├─ 6. Check max_iterations
│      ├─ Under limit → retry
│      └─ Over limit → abort or escalate
│
├─ 7. Create PhaseRecord with results
│
├─ 8. Write checkpoint via WriteQueue
│
├─ 9. Determine next phase via OrchestratorFSM.submit()
│
├─ 10. Create trace span
│
└─ 11. Return result:
       {
         "status": "accepted",
         "next_phase": "Testing",
         "judge_result": {...},
         "debate_transcript": {...}
       }
```

---

## Tool Gate System

### Purpose

The `ToolGate` enforces **sequential validation gates** — automated checks that must pass before a phase can advance. "Looks correct" is never acceptable when tools can verify correctness.

### Default Gate Sequence

```
LINT     (ruff)       → Code style and error detection
TYPES    (mypy)       → Static type checking
TESTS    (pytest)     → Unit/integration test execution
COVERAGE (coverage)   → Test coverage measurement
SECURITY (semgrep)    → Security vulnerability scanning
BENCHMARKS (benchmarks) → Performance regression detection
```

### Fail-Fast Semantics

Gates run in strict order. If a gate fails, all subsequent gates are **skipped**:

```python
def evaluate_sequence(results: list[GateResult]) -> GateSequenceResult:
    for r in results:
        if not r.passed and not r.skipped:
            return GateSequenceResult(passed=False, failed_at=r.gate)
    return GateSequenceResult(passed=True)
```

**Rationale:** There's no point running type-checking if linting found syntax errors. There's no point running security scans if tests are failing. Fail-fast saves time and produces actionable error messages.

### Phase-Specific Exceptions

Some phases don't need all gates. The tool gate supports **spec-aware exceptions**:

```python
tool_gate.add_exception("Specs", "tests")        # Specs don't need tests
tool_gate.add_exception("Specs", "coverage")      # ...or coverage
tool_gate.add_exception("Planning", "security")   # Plans don't need security scans

# At runtime:
gates = tool_gate.get_gates_for_phase("Specs")
# Returns: [("lint", "ruff"), ("types", "mypy"), ("security", "semgrep"), ("benchmarks", "benchmarks")]
```

### Gate Result Model

```python
class GateResult(BaseModel):
    gate: str              # Gate name ("lint", "tests", etc.)
    tool: str              # Tool used ("ruff", "pytest", etc.)
    passed: bool           # Whether the gate passed
    output: str = ""       # Tool stdout
    errors: str = ""       # Tool stderr
    duration_ms: float     # Execution time
    skipped: bool = False  # Skipped due to upstream failure
    skip_reason: str = ""  # Why it was skipped

class GateSequenceResult(BaseModel):
    passed: bool           # Overall pass/fail
    failed_at: str = ""    # First failing gate
    gates: list[GateResult]
    total_duration_ms: float
```

### Gate History

The tool gate maintains a history of all gate sequences for trend analysis:

```python
tool_gate.history
# [
#   {"passed": True, "failed_at": "", "passed_gates": ["lint", "types", "tests"], ...},
#   {"passed": False, "failed_at": "tests", "passed_gates": ["lint", "types"], ...},
# ]
```

---

## LLM Provider Architecture

### Provider Abstraction

All LLM interactions go through the `LLMProvider` interface:

```python
class LLMProvider(Protocol):
    async def generate(
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format: dict | None = None,
    ) -> str: ...
```

### Supported Providers

| Provider | Class | Default Model | Use Case |
|---|---|---|---|
| Ollama | `OllamaProvider` | `qwen3:8b` | Local inference, development |
| OpenAI | `OpenAIProvider` | `gpt-4o` | Cloud inference, production |

### Model Routing

Different components can use different providers and models:

```python
class ModelRouter:
    routing_config = {
        "judge":            {"provider": "openai", "model": "gpt-4o"},
        "debate_agent":     {"provider": "ollama", "model": "qwen3:8b"},
        "debate_consensus": {"provider": "openai", "model": "gpt-4o"},
    }
    
    def route(self, role: str) -> tuple[LLMProvider, str]:
        # Returns (provider, model) for the given role
```

**Rationale:** Judges and consensus evaluation benefit from stronger models. Debate agents can use cheaper/faster local models since their outputs are aggregated through consensus.

### LLM Config

```yaml
# configs/llm_config.yaml
default_provider: ollama
default_model: qwen3:8b

providers:
  ollama:
    type: ollama
    base_url: http://localhost:11434
    timeout_s: 120
    default_model: qwen3:8b
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    timeout_s: 120
    default_model: gpt-4o

routing:
  judge_provider: default
  debate_agent_provider: default
  debate_consensus_provider: default
```

---

## Workspace Indexing

### Index Pipeline

The `IndexPipeline` maintains a structural index of the workspace for context-aware code generation:

```python
class IndexPipeline:
    # Capabilities:
    # 1. Full index — scan entire workspace
    # 2. Incremental index — scan only changed files (by mtime/hash)
    # 3. File-specific index — index specific files
    # 4. Dependency context — get import graph for a file
```

### What Gets Indexed

```python
class FileIndex(BaseModel):
    path: str
    language: str              # Detected language
    symbols: list[CodeSymbol]  # Classes, functions, methods, variables
    imports: list[ImportInfo]  # Import statements
    mtime: float               # Last modification time
    sha256: str                # Content hash
    size_bytes: int
```

```python
class CodeSymbol(BaseModel):
    name: str                  # Symbol name
    kind: SymbolKind           # module, class, function, method, variable, etc.
    file_path: str
    start_line: int
    end_line: int
    parent: str | None         # Enclosing symbol
    docstring: str | None
```

### Dependency Graph

The index builds a cross-file dependency graph:

```python
class DependencyGraph(BaseModel):
    files: dict[str, FileIndex]            # file_path → index
    import_edges: dict[str, list[str]]     # file → [files it imports]
    dependents: dict[str, list[str]]       # file → [files that import it]
```

### Index Configuration

```python
class IndexConfig(BaseModel):
    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: ["*.py", "*.js", "*.ts", ...]
    exclude_patterns: ["*.pyc", "__pycache__/*", ".git/*", "node_modules/*", ...]
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20
```

---

## MCP Integration Strategy

### Current Integration

Foundry currently runs as an MCP server that a host agent (OpenCode) connects to. The host agent provides:
- Filesystem access (read, write, list)
- Shell execution (run commands)
- Git operations (commit, branch, diff)
- Terminal interaction (run persistent processes)

Foundry provides:
- SDLC lifecycle management
- Structured validation and debate
- Checkpointing and recovery
- Budget enforcement
- Workspace indexing

### Tool Gateway Concept

The planned tool gateway will abstract all external tool access:

```
Orchestrator
    │
    ▼
Tool Router → Route to appropriate MCP/tool
    │
    ▼
Policy Check → Validate the operation is allowed
    │
    ▼
Tool Executor → Execute with timeout/retry/normalization
    │
    ▼
MCP Call → Actual external tool invocation
    │
    ▼
Output Validation → Verify the result is sane
```

**Benefits:**
- MCPs become **replaceable** — swap filesystem MCPs without touching orchestration
- **Vendor independence** — not locked to any specific MCP implementation
- **Centralized governance** — all external operations go through a single policy layer
- **Fallback support** — if one MCP fails, try another

### MCP Tiering

| Tier | MCPs | Integration Timing |
|---|---|---|
| **Tier 1** | filesystem, shell, git | Now (via host agent) |
| **Tier 2** | github, docker | Phase 1 (PR workflows, sandboxed execution) |
| **Tier 3** | postgres, playwright | Phase 3+ (persistent memory, research) |
| **Tier 4** | qdrant, brave-search | Phase 4+ (semantic retrieval) |
| **Tier 5** | jira, linear, slack | On-demand (enterprise requests only) |
