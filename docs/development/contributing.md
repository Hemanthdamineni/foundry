# Development Guide

> Repository structure, coding standards, debugging workflows, contributor onboarding, and development setup.

---

## Repository Structure

```
Ai-Agent-Server/
├── foundry/                      # NPX-installable package (user-facing)
│   ├── package.json              # npm package definition
│   ├── install/
│   │   └── install.js            # Postinstall hook (links skills, installs runtime)
│   ├── agents/                   # Agent configurations
│   └── skills/
│       └── sdlc/
│           ├── SKILL.md          # Skill instructions for host agent
│           └── prompts/          # Subagent prompt templates
│               ├── specs.txt
│               ├── plan.txt
│               └── tester.txt
│
├── sdlc/                         # Python runtime (the actual engine)
│   ├── __init__.py
│   ├── config.py                 # Settings, configuration loading
│   ├── models.py                 # All Pydantic data models (309 lines)
│   ├── exceptions.py             # Custom exception hierarchy
│   ├── log.py                    # Structured logging setup
│   │
│   ├── engine/                   # Orchestration + Reasoning
│   │   ├── orchestrator.py       # OrchestratorFSM — phase transitions (65 lines)
│   │   ├── orchestrator_runtime.py # OrchestratorAuthority — governance (161 lines)
│   │   ├── execution_policy.py   # Budget/retry/failure decisions (88 lines)
│   │   ├── phase_graph.py        # Phase graph loading + validation (124 lines)
│   │   ├── checkpoint.py         # Base checkpoint manager
│   │   ├── debate_runtime.py     # 3-round debate protocol (360 lines)
│   │   ├── consensus.py          # Consensus evaluation (286 lines)
│   │   ├── reviewer_debate.py    # Review-specific debate
│   │   ├── judge.py              # JudgeEngine — per-phase evaluation
│   │   ├── judge_hierarchy.py    # Multi-layer validation
│   │   ├── confidence_gate.py    # Confidence gating (178 lines)
│   │   ├── drift_detector.py     # Specification drift detection
│   │   ├── retry_policy.py       # 5-level escalation (177 lines)
│   │   ├── replanner.py          # Dynamic replanning (108 lines)
│   │   ├── recovery_engine.py    # Crash recovery
│   │   ├── dependency_graph.py   # Task decomposition DAG
│   │   ├── hierarchical_graph.py # Hierarchical task planning
│   │   ├── phase_contracts.py    # Phase I/O contracts
│   │   ├── context_harvester.py  # Context extraction
│   │   └── prompt_registry.py    # Versioned prompt management
│   │
│   ├── runtime/                  # State + Execution + Observability
│   │   ├── app.py                # FastMCP server + tool registration (661 lines)
│   │   ├── state_manager.py      # Persistent state files (202 lines)
│   │   ├── memory_store.py       # Structured retrieval (260 lines)
│   │   ├── enhanced_checkpoint.py # Versioned checkpoint chains (306 lines)
│   │   ├── rollback_manager.py   # Git-safe rollback (144 lines)
│   │   ├── execution_runtime.py  # Deterministic execution (248 lines)
│   │   ├── budget_controller.py  # Budget enforcement (294 lines)
│   │   ├── tool_gate.py          # Sequential validation gates (133 lines)
│   │   ├── tool_executor.py      # Reliable tool calls
│   │   ├── tracing.py            # JSONL distributed tracing (279 lines)
│   │   ├── dashboard.py          # Runtime telemetry
│   │   ├── write_queue.py        # Async write pipeline
│   │   ├── store_sqlite.py       # SQLite storage backend
│   │   ├── store_backend.py      # Storage backend protocol
│   │   ├── pipelines/
│   │   │   └── default.py        # Index pipeline
│   │   └── tools/
│   │       ├── task.py            # Task management tools
│   │       ├── phase.py           # Phase management tools (13,791 bytes)
│   │       └── debug.py           # Debug/trace tools
│   │
│   ├── adapters/                 # External integrations
│   │   ├── llm/                  # LLM providers (Ollama, OpenAI)
│   │   └── memory/              # Memory backends (Acervo)
│   │
│   ├── validators/               # Validation logic
│   │
│   ├── configs/                  # YAML configurations
│   │   ├── graphs/
│   │   │   └── feature.yaml
│   │   ├── model_routing.yaml
│   │   ├── llm_config.yaml
│   │   └── prompts/             # Judge prompt templates
│   │
│   └── graphs/                   # Phase graph definitions
│       └── feature.yaml
│
├── docs/                         # Technical documentation (you are here)
│   ├── architecture/
│   ├── orchestration/
│   ├── runtime/
│   ├── execution/
│   ├── development/
│   ├── roadmap/
│   └── brainstorming/            # Archived raw architecture drafts
│
├── ARCHITECTURE.md               # Architecture overview (entry point)
├── ROADMAP.md                    # Phased implementation plan
├── TODO.md                       # Implementation task tracking
├── package.json                  # Root package (maps npx to foundry)
└── .gitignore
```

---

## Development Setup

### Prerequisites

1. **Python 3.11+** — Runtime language
2. **Node.js 18+** — Package management and install scripts
3. **Ollama** — Local LLM inference (default provider)
4. **Git** — Version control and rollback support

### Local Development

```bash
# Clone the repository
git clone https://github.com/Hemanthdamineni/foundry.git
cd foundry

# Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Or with pixi:
pixi install

# Start Ollama (if not running)
ollama serve &
ollama pull qwen3:8b

# Run the MCP server directly
python -m sdlc
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=sdlc --cov-report=html

# Run specific subsystem tests
pytest tests/engine/
pytest tests/runtime/

# Type checking
mypy sdlc/

# Linting
ruff check sdlc/
ruff format --check sdlc/
```

---

## Coding Standards

### Python Style

1. **Type hints everywhere** — All function signatures must have complete type annotations
2. **Pydantic models** — All data structures are Pydantic `BaseModel` subclasses
3. **Async by default** — All I/O operations are async
4. **Structured logging** — Use `get_logger(name)` with `extra={}` dicts, never f-string messages
5. **Atomic writes** — All file persistence uses tmp+rename pattern
6. **No global mutable state** — All state flows through `SDLCAppContext`

### Module Boundaries

Every module has a single responsibility. Cross-cutting concerns are explicitly prohibited:

```python
# ✓ CORRECT — FSM only handles transitions
class OrchestratorFSM:
    def submit(self, current_phase, target=None) -> str: ...

# ✗ WRONG — FSM checking budgets
class OrchestratorFSM:
    def submit(self, current_phase, target=None) -> str:
        if self.budget_exceeded():  # ← Policy concern in FSM
            return "Done"
```

### Error Handling Patterns

```python
# Module-specific exceptions
class OrchestratorError(Exception): ...
class PhaseGraphError(Exception): ...
class DebateError(Exception): ...
class ConfigError(Exception): ...

# Retry-safe error handling in async code
try:
    result = await asyncio.wait_for(operation(), timeout=TIMEOUT_S)
except (TimeoutError, OSError, DebateError, RuntimeError) as e:
    log.warning("Operation failed", extra={"error": str(e), "attempt": attempt})
    if attempt < MAX_RETRIES:
        await asyncio.sleep(BACKOFF_BASE_S * (2 ** attempt))
```

### Model Design Patterns

```python
# All models derive from BaseModel
class MyRecord(BaseModel):
    id: str
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

# Enums use StrEnum for JSON serialization
class MyStatus(enum.StrEnum):
    ACTIVE = "active"
    DONE = "done"

# Optional fields use default factories, not None
class Config(BaseModel):
    items: list[str] = Field(default_factory=list)   # ✓
    items: list[str] | None = None                   # ✗ avoid
```

---

## Debugging Flows

### Debugging a Failed Phase Transition

```
1. Check task status:
   → sdlc_get_status(task_id) → Shows current_phase, history, iteration_count

2. Read trace:
   → sdlc_list_traces(task_id) → Get trace IDs
   → sdlc_get_trace(trace_id) → Read spans for the failing execution

3. Check judge verdict:
   → In trace spans, find tool="sdlc_submit_output"
   → metadata.judge_result shows why the judge rejected

4. Check debate transcript:
   → metadata.debate_transcript shows round-by-round responses
   → Check for sycophantic collapse signal
   → Check minority reports for dissenting views

5. Check budget:
   → budget_controller.get_stats() shows tokens/time/retry consumption
   → budget_controller.full_check(task_id, phase) lists violations
```

### Debugging a Stuck Task

```
1. Is the task active?
   → sdlc_get_status(task_id) → status should be "active"
   → If "stalled" → budget was exhausted

2. Is the retry policy stuck?
   → retry_policy.no_progress_detected(phase) → True means no progress
   → retry_policy.effectiveness_score(phase) → 0.0 means all retries failed

3. Can we escalate?
   → retry_policy.escalate(phase, current_level) → Next level or None

4. Can we rollback?
   → checkpoint_mgr.get_chain_info(task_id) → Shows versions + stable markers
   → rollback_manager.plan_rollback(...) → Shows what would be reverted
```

### Debugging State Corruption

```
1. Check state file integrity:
   → ls data/state/task_{id}.json → Does it exist?
   → cat data/state/task_{id}.json | python -m json.tool → Valid JSON?

2. Check checkpoint integrity:
   → ls data/checkpoints/{id}_chain.json → Chain metadata
   → ls data/checkpoints/{id}_v*.json → Individual versions

3. Recover from checkpoint:
   → checkpoint_mgr.restore_to_stable(task_id) → Get last stable state
   → Manually update task state to match

4. Nuclear option:
   → Delete data/state/task_{id}.json
   → Delete data/state/phase_{id}.json
   → Restore from last stable checkpoint
```

---

## Adding New Components

### Adding a New Engine Module

1. Create `sdlc/engine/my_module.py`
2. Define your Pydantic models at the top
3. Create a class with clear responsibility boundaries
4. Add logging: `logger = get_logger("engine.my_module")`
5. Export from `sdlc/engine/__init__.py`
6. Wire into `SDLCAppContext` in `app.py` if needed
7. Add tests in `tests/engine/test_my_module.py`

### Adding a New MCP Tool

1. Define the tool function in the appropriate `runtime/tools/*.py` file
2. Register it in `app.py`:
   ```python
   @app.tool()
   async def sdlc_my_tool(
       param: str,
       ctx: Context[Any, Any, Any] | None = None,
   ) -> dict[str, Any]:
       sdlc_ctx = _require_context(ctx)
       return await tools.my_tool(sdlc_ctx.store, param)
   ```
3. The tool automatically becomes available to the host agent
4. Add tracing if the operation is significant

### Adding a New Phase Graph

1. Create `sdlc/graphs/my_workflow.yaml`:
   ```yaml
   phases: [Phase1, Phase2, Phase3, Done]
   transitions:
     - { from: Phase1, to: Phase2 }
     - { from: Phase2, to: Phase3 }
     - { from: Phase3, to: Done }
   ```
2. Ensure all invariants: `Done` exists, all phases reachable, no `Done` outgoing
3. Add model routing for all new phases in `model_routing.yaml`
4. Create task with `mode="my_workflow"`

---

## Known Tradeoffs

### Design Tradeoffs

| Decision | Tradeoff | Rationale |
|---|---|---|
| Single-process | No parallelism across phases | Simplicity; no distributed coordination needed |
| SQLite store | Not suitable for concurrent access | Single-user local runtime; no multi-tenancy |
| JSON checkpoints | Grow linearly with task history | Simpler than database; atomic writes are easy |
| JSONL traces | Files accumulate over time | Retention policy handles cleanup; no external deps |
| In-memory retry state | Lost on crash | Checkpoints capture phase-level state; retry is fine-grained |
| YAML config | No runtime reconfiguration | Server restart is acceptable; avoids config mutation bugs |

### Technical Debt

| Debt | Impact | Priority |
|---|---|---|
| `ExecutionRuntime` not wired into main loop | Deterministic IDs and prompt locks not enforced in production | P0 — Phase 1 |
| `ToolGate` not wired into main loop | Validation gates are defined but not enforced during submit | P0 — Phase 1 |
| `BudgetController` runs alongside `ExecutionPolicy` | Two budget systems that should be unified | P1 — Phase 2 |
| `EnhancedCheckpointManager` parallel to `CheckpointManager` | Two checkpoint systems; enhanced should replace base | P1 — Phase 2 |
| `StateManager` separate from `SqliteStore` | Two persistence systems; should unify or clarify boundary | P2 — Phase 3 |
| No integration tests for full SDLC loop | Individual modules tested; end-to-end flow untested | P0 — Phase 1 |

---

## Runtime Guarantees and Limitations

### Guarantees

1. **Phase transitions are validated** — The FSM rejects invalid transitions
2. **Budget ceilings are hard** — When exceeded, tasks abort
3. **Checkpoints are atomic** — tmp+rename prevents partial writes
4. **Debate detects collapse** — Sycophantic agreement is flagged
5. **Rollback preserves stable work** — Completed phases are never reverted

### Limitations

1. **No real-time guarantees** — Phase execution takes as long as it takes
2. **No concurrent task execution** — Tasks run sequentially
3. **LLM quality is non-deterministic** — Same prompt can produce different outputs
4. **Recovery requires manual intervention** — The system identifies recovery points but doesn't auto-resume
5. **No authentication** — MCP protocol provides no auth; trust boundary is the local machine
6. **Index accuracy depends on language** — Only Python has deep symbol extraction; others are file-level
