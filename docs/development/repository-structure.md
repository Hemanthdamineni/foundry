# Repository Structure

> Complete file tree with module descriptions, layer classification, package boundaries, and configuration file inventory.

---

## Root Directory

```
Ai-Agent-Server/
├── foundry/                    # NPX installer package
│   ├── install/
│   │   └── install.js          # Postinstall hook: Python setup, MCP registration, skill linking
│   └── package.json
│
├── sdlc/                       # Python SDLC runtime (core)
│   ├── __init__.py
│   ├── config.py               # Settings, YAML loaders, path resolution
│   ├── exceptions.py           # Base error hierarchy
│   ├── log.py                  # Logging bootstrap, JSON formatter
│   ├── models.py               # All Pydantic data models (~310 lines)
│   ├── engine/                 # Domain logic (Layer 3)
│   ├── runtime/                # Infrastructure (Layer 4-5)
│   └── adapters/               # External integrations (Layer 4)
│
├── configs/                    # YAML configuration files
│   ├── prompts/                # Judge prompt templates
│   ├── model_routing.yaml      # Per-phase model assignment
│   ├── budget_policy.yaml      # Budget configuration
│   └── llm_config.yaml         # LLM provider configuration
│
├── graphs/                     # Phase graph definitions
│   └── feature.yaml            # SDLC lifecycle graph
│
├── data/                       # Runtime data (gitignored)
│   ├── sdlc.db                 # SQLite database
│   ├── checkpoints/            # Versioned checkpoint files
│   ├── traces/                 # JSONL trace files
│   ├── logs/                   # Application logs
│   ├── index/                  # Dependency graph + SHA cache
│   └── memory/                 # Engram JSONL files
│
├── docs/                       # This documentation
├── .agents/                    # Agent skill definitions
│   └── skills/foundry/
│       └── SKILL.md            # Foundry skill instructions
│
├── ARCHITECHTRE.md             # Raw architecture brainstorming
├── SKILLS.md                   # Raw skills brainstorming
├── MCPS.md                     # Raw MCP brainstorming
├── TODO.md                     # Implementation task list
└── pyproject.toml              # Python project configuration
```

---

## Engine Layer (`sdlc/engine/`)

The domain logic layer. No I/O, no persistence, no adapters. Pure business logic.

```
engine/
├── orchestrator.py             # OrchestratorFSM — phase state machine
├── phase_graph.py              # PhaseGraph — YAML graph parsing + validation
├── execution_policy.py         # ExecutionPolicy — budget + retry decisions
├── judge.py                    # JudgeEngine — LLM-based quality evaluation
├── judge_hierarchy.py          # MultiJudge — Tool, Semantic, Security, Integration judges
├── schema_checks.py            # SchemaChecks — deterministic section validation
├── debate_runtime.py           # DebateRuntime — 3-round multi-agent debate
├── consensus.py                # ConsensusEngine — vote synthesis + collapse detection
├── confidence_gate.py          # ConfidenceGate — vote normalization + thresholds
├── retry_policy.py             # RetryPolicy — failure classification + effectiveness
├── recovery_engine.py          # RecoveryEngine — 5-level escalation
├── replanner.py                # Replanner — stable work preservation
├── checkpoint.py               # CheckpointManager — basic checkpoint operations
├── enhanced_checkpoint.py      # EnhancedCheckpointManager — versioned chains
├── context_harvester.py        # ContextHarvester — pre-spec context gathering
├── drift_detector.py           # DriftDetector — architectural layer enforcement
├── prompt_registry.py          # PromptRegistry — versioned prompts with dedup
├── execution_runtime.py        # ExecutionRuntime — phase execution coordination
├── replay.py                   # ReplayEngine — trace/checkpoint replay
├── dependency_graph.py         # DependencyGraphEngine — code graph with edges
├── repository_indexer.py       # RepositoryIndexer — architecture summaries
├── hierarchical_graph.py       # HierarchicalGraph — multi-level task decomposition
├── integration_manager.py      # IntegrationManager — cross-module integration
├── progress_tracker.py         # ProgressTracker — task progress computation
├── regression_manager.py       # RegressionManager — regression detection
├── team_coordinator.py         # TeamCoordinator — multi-agent coordination
├── test_generator.py           # TestGenerator — automated test scaffolding
└── reviewer_debate.py          # ReviewerDebate — review-specific debate variant
```

### Layer Rule

Engine modules may import from `sdlc.models` and `sdlc.log`. They **must not** import from `sdlc.runtime` or `sdlc.adapters`. The DriftDetector enforces this at development time.

---

## Runtime Layer (`sdlc/runtime/`)

Infrastructure services. I/O, persistence, MCP server, tool handlers.

```
runtime/
├── app.py                      # FastMCP server bootstrap + lifespan (~660 lines)
├── store_backend.py            # StoreBackend ABC — persistence abstraction
├── store_sqlite.py             # SqliteStore — WAL mode, BEGIN IMMEDIATE
├── tracing.py                  # Tracer — JSONL span recording
├── write_queue.py              # WriteQueue — async FIFO for state writes
├── budget_controller.py        # BudgetController — token/time/retry tracking
├── rollback_manager.py         # RollbackManager — safe rollback with protection
├── tool_gate.py                # ToolGate — ordered validation gate sequence
├── dashboard.py                # Dashboard — status display (optional)
├── pipelines/
│   └── default.py              # IndexPipeline — full/incremental/targeted indexing
└── tools/
    ├── phase.py                # Phase tools: get_next_action, submit_output, request_approval
    ├── task.py                 # Task tools: create, status, list, cancel
    └── debug.py                # Debug tools: traces, summaries, retention
```

### Layer Rule

Runtime modules may import from `sdlc.engine`, `sdlc.models`, and `sdlc.adapters`. They are the integration layer.

---

## Adapters Layer (`sdlc/adapters/`)

External tool integrations. Each adapter wraps one external tool behind the ToolAdapter protocol.

```
adapters/
├── base.py                     # ToolAdapter ABC + ToolCapability enum
├── llm/
│   ├── base.py                 # LLMProvider ABC
│   ├── providers.py            # OllamaProvider, OpenAIProvider
│   ├── routing.py              # ModelRouter — per-role model selection
│   └── _testing.py             # Test doubles for LLM providers
├── memory/
│   ├── acervo.py               # Acervo — JSONL engram storage
│   └── engram.py               # MemoryAdapter — ToolAdapter wrapper
└── tools/
    ├── ruff.py                 # Lint adapter
    ├── mypy.py                 # Type checking adapter
    ├── pytest.py               # Test execution adapter
    ├── bandit.py               # Security analysis adapter
    ├── semgrep.py              # Security scanning adapter
    ├── coverage.py             # Code coverage adapter
    ├── benchmarks.py           # Performance benchmarking adapter
    ├── tree_sitter.py          # AST parsing adapter
    └── graphify.py             # Graph visualization adapter
```

---

## Configuration Files

| File | Format | Purpose | Loaded By |
|---|---|---|---|
| `configs/model_routing.yaml` | YAML | Per-phase model + subagent | `settings.load_model_routing()` |
| `configs/budget_policy.yaml` | YAML | Budget defaults + profiles | `settings.load_budget_policy()` |
| `configs/llm_config.yaml` | YAML | Provider configurations | `settings.load_llm_config()` |
| `configs/prompts/*.txt` | Text | Judge prompt templates | `settings.load_all_judge_prompts()` |
| `graphs/feature.yaml` | YAML | Feature lifecycle graph | `settings.load_phase_graph()` |
| `pyproject.toml` | TOML | Python dependencies + build | pip/pixi |

### Environment Variables

All settings support env var override via `pydantic_settings`:

```
SDLC_DEBUG=true
SDLC_DB_PATH=data/sdlc.db
SDLC_CHECKPOINT_DIR=data/checkpoints
SDLC_TRACE_DIR=data/traces
SDLC_LOG_PATH=data/logs/sdlc.log
SDLC_LLM__DEFAULT_PROVIDER=ollama
SDLC_LLM__DEFAULT_MODEL=qwen3:8b
SDLC_LLM__PROVIDERS__OPENAI__API_KEY=sk-...
```

Nested delimiter: `__` (double underscore). Prefix: `SDLC_`.

---

## Data Directory Layout

```
data/                           # All runtime data (gitignored)
├── sdlc.db                     # SQLite: tasks, phase_history, checkpoints tables
├── checkpoints/
│   ├── {task_id}_chain.json    # Checkpoint chain metadata
│   └── {task_id}_v{N}.json     # Individual checkpoint versions
├── traces/
│   ├── {trace_id}.jsonl        # Span-level trace data
│   └── {trace_id}_summary.json # Aggregated trace summary
├── logs/
│   └── sdlc.log                # Rotating JSON log (10MB × 5 backups)
├── index/
│   ├── dependency_graph.json   # Full code dependency graph
│   └── sha_cache.json          # File content hashes for incremental indexing
├── memory/
│   └── engrams.jsonl           # Tagged memory entries
└── plugin_state/               # Adapter-specific state (reserved)
```
