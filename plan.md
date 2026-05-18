# SDLC MCP Server for opencode — Implementation Plan

## Goal

Convert the AI Agent Server V3 (FastAPI + Continue bridge server) into an MCP server + opencode plugin system that runs as an opencode backend, preserving the deterministic phase graph, judge engine, parallel debate, and SQLite persistence, while leveraging opencode's native agents, subagents, skills, plugins, and tools.

## Integration Governance

Before any integration, ask:

```
What architectural weakness does this solve?
```

If the answer is unclear, do not integrate it.

The system is structured around 5 layers — reasoning, execution, validation, orchestration, persistence. An integration earns its place only if it strengthens one of these layers without compromising the others.

### Capability Classes, Not Tools

Instead of integrating specific tools (Ruff, Mypy, Docker, Git, Graphify), define a **ToolAdapter** interface:

```python
class ToolAdapter:
    name: str
    capability: str  # e.g. "lint", "typing", "testing", "code-graph", "sandbox"

    async def validate(self, task): ...
    async def execute(self, task): ...
    async def healthcheck(self): ...
```

Capability mapping:

| Tool | Capability |
|---|---|
| Ruff | lint |
| Mypy | typing |
| Pytest | testing |
| Graphify / Tree-sitter | code-graph |
| Docker / Firejail | sandbox |
| Prefect / Temporal | workflow |
| Git | versioning |

Tools implement `ToolAdapter`. The orchestrator talks to capabilities, not tools. This prevents integration entropy before it starts.

### Recommended Implementation Order

0. **Foundation** — project structure, pixi workspace, pyproject, tooling baseline, Pydantic models, config loader, logging bootstrap
1. **Core runtime** — orchestrator FSM + ToolAdapter interface + checkpoint system
2. **Deterministic validation** — lint, typing, testing, coverage, security
3. **Judge + review loop** — LLM judge, schema checks, prompt version locking, oscillation protection
4. **Observability** — structured logging, distributed tracing, trace retention
5. **Context intelligence** — code graph, Graphify, tree-sitter (memory deferred to Phase 7)
6. **Structured reasoning** — debate, consensus, judge (only after tracing + code graph exist)
7. **Agent config + skills** — opencode.json, SKILL.md, prompt files
8. **OAC context + plugin stack** — pattern library, third-party plugins
9. **Distributed execution** — parallelism, task DAGs, multi-worker (deferred until stable core)

## Architecture

```
opencode (user-facing)                     MCP Server (Python, stdio)
┌──────────────────────────────────┐      ┌────────────────────────────────┐
│ Layer 0: opencode Core            │      │                                │
│                                   │      │  Tools (sequence enforce):     │
│ Primary Agent: dev-sdlc           │──────▶  sdlc_create_task             │
│  model: qwen3:8b                 │ MCP   │  sdlc_get_next_action         │
│  prompt: from skill              │ stdio │  sdlc_submit_output           │
│  permission: edit=ask, bash=ask  │      │  sdlc_request_approval        │
│                                   │      │  sdlc_get_status              │
│  Hidden subagents (hidden:true): │      │  sdlc_list_tasks               │
│  ├── @specs    (qwen3:4b)       │      │  sdlc_cancel_task              │
│  ├── @plan     (qwen3:4b)       │      │                                │
│  ├── @code     (coder:3b)       │      │  Resources (on-demand):        │
│  ├── @review   (coder:7b)       │      │  sdlc://task/{id}/spec        │
│  ├── @tester   (qwen3:4b)       │      │  sdlc://task/{id}/plan        │
│  │                              │      │  sdlc://patterns/{name}       │
│  └── Hidden debate agents:      │      │  sdlc://phase-graph            │
│      ├── @debate-proposer       │      │                                │
│      ├── @debate-critic         │      │  Engine (hard enforced):        │
│      └── @debate-architect      │      │  ├── OrchestratorFSM           │
│                                   │      │  ├── PhaseGraph              │
│ Layer 1: opencode Plugin         │      │  ├── JudgeEngine (LLM-based)  │
│  .opencode/plugins/sdlc-enforcer │      │  ├── ConsensusEngine          │
│  ├── tool.execute.before → block│      │  └── SqliteStore              │
│  │   edits in wrong phase       │      │                                │
│  ├── tool.execute.after → sync  │      │  Adapters: ToolAdapter impls   │
│  │   state + auto-format        │      │  ├── tools/ (lint, typing...)  │
│  ├── event → session.idle      │      │  ├── models/ (Ollama)         │
│  │   + prompt() (no native     │      │  ├── execution/ (sandbox)     │
│  │   stop hook — PR #16598)   │      │  ├── vcs/ (git worktree)     │
│  └── compacting → inject SDLC  │      │  └── graph/ (Graphify)       │
│      anchor (intent, phases,   │      │                                │
│      files, decisions, next)   │      │  Observability:                │
│                                   │      │  ├── trace_id per phase     │
│                                   │      │  └── span propagation       │
│                                   │      │  Config:                      │
│ Layer 2: OAC Context             │      │  phase_graph.yaml             │
│  .opencode/context/project/     │      │  model_routing.yaml           │
│  ├── style.md, patterns.md      │      │  prompts/judge_*.txt          │
│  ├── testing.md, security.md    │      └────────────────────────────────┘
│  .opencode/context/sdlc/       │
│  ├── phase-guide.md             │      Layer 3: Installed Plugins
│  └── quality.md                 │      ├── kdco/background-agents
│                                   │      │   (parallel debate)
└──────────────────────────────────┘      ├── felixAnhalt/opencode-worktree
                                           │   (git isolation per task)
Runtime (standalone processes):            ├── oh-my-opencode
  ┌────────────┐  ┌──────────┐            │   (LSP, AST-Grep, Context7)
  │ Ollama     │  │ SQLite   │            └── @tarquinen/opencode-dcp
  │ (model     │  │ (WAL)    │                (dynamic context pruning)
  │  serving)  │  │          │
  └────────────┘  └──────────┘
```

## Key Decisions

### ToolAdapter First (Phase 0 over everything)

Build the abstraction layer (ToolAdapter interface + ToolCapability enum) before any plugin, tool, or server code. This prevents integration entropy — the contract comes first, implementations follow.

Rationale: Without ToolAdapter, each new integration (Ruff, Mypy, Graphify, Docker) adds ad-hoc coupling. With ToolAdapter, the orchestrator talks to capabilities, never tools.

### Plugin Enforcement Over Agent Permissions

MCP tools bypass agent permission filtering (opencode bug #23045). `tool.execute.before` throwing `Error` is the only reliable enforcement point for phase gates. Agent permissions in `opencode.json` are a secondary defense, not primary.

Rationale: Bug #23045 means edit/bash deny on a subagent can be circumvented via MCP tool calls. The plugin's `tool.execute.before` hook fires on every tool invocation regardless of subagent — cannot be bypassed.

### Plugin First Over Server First

Phase 1 builds the enforcer plugin before any server code. If enforcement doesn't work, the architecture has no teeth. The plugin is the gate; everything else depends on it.

Rationale: Without hard phase gates, the agent can edit files during Specs/Planning phases. The plugin is the only thing preventing this. Server-side validation is secondary — it catches phase mismatch on submit, but the plugin catches edit attempts in real-time.

### Stop Workaround Over Native Stop Hook

No native `stop` hook exists in opencode's plugin API (PR #16598/#16626 not merged). Use `event` hook + `session.idle` detection + `client.session.prompt()` to re-inject continuation messages.

Caveats: Visible user message in interactive mode; race condition in headless mode. Acceptable tradeoff until native stop lands.

Rationale: Without this workaround, the agent can stop mid-phase without submitting output, leaving the task in an inconsistent state. The workaround is imperfect but strictly better than no enforcement.

### Structured Anchored Compaction Over Default Compaction

Default opencode compaction loses SDLC state (task_id, current phase, files modified). Replace with `experimental.session.compacting` hook that injects a persistent anchor:

```
task_id, current_phase, phase_submitted, approval_pending
```

On restore, the agent calls `sdlc_get_next_action(task_id)` to resync.

Rationale: Without anchored compaction, long-running tasks lose phase context after a compact cycle. The agent would have to re-derive its state from conversation history, which is fragile.

### FastMCP Over Raw MCP SDK

Use `FastMCP` (from `mcp[cli]>=1.0.0`) instead of raw `Server` class. FastMCP provides:

- Decorator-based tool/resource/prompt registration
- Lifespan context for startup/shutdown
- Streamable HTTP transport for production
- Built-in CLI for dev testing

Rationale: Raw MCP SDK requires manual request routing, lifecycle management, and transport handling. FastMCP provides all of this declaratively, reducing boilerplate by ~60%.

### StoreBackend Abstraction Over SQLite

Persistence is wrapped behind a `StoreBackend` ABC — the rest of the system never imports `aiosqlite` directly:

```python
class StoreBackend(ABC):
    async def create_task(self, ...) -> Task
    async def get_task(self, task_id: str) -> Task | None
    async def save_phase_output(self, ...) -> None
    async def get_history(self, task_id: str) -> list[PhaseRecord]
    async def save_checkpoint(self, ...) -> None
    async def restore_checkpoint(self, task_id: str) -> Checkpoint | None
    ...
```

Two implementations:
- `store_sqlite.py` — SQLite (aiosqlite, WAL mode, busy_timeout, manual checkpoints)
- Future: `store_postgres.py` — asyncpg for Postgres

The rest of the system (OrchestratorFSM, tools, pipelines) imports `StoreBackend` only. SQLite-specific settings are in `store_sqlite.py` alone. This prevents tight coupling and allows swapping backends without rewriting orchestration logic.

### SQLite via aiosqlite With WAL Mode

Default StoreBackend implementation uses aiosqlite for async SQLite access with three non-negotiable settings:

- `WAL mode` — concurrent reads during writes
- `busy_timeout=5000` — 5s wait on lock contention
- `BEGIN IMMEDIATE` for all writes — prevents deadlock on concurrent phase transitions

Manual checkpoint management: `PRAGMA wal_checkpoint(TRUNCATE)` after every 100 writes to prevent WAL file growth.

Rationale: Async SQLite with WAL mode gives PostgreSQL-grade concurrency for a single-server workload without the operational overhead of a full database server.

### Judge Engine via Local Ollama, Not a Subagent

Judge decisions call Ollama directly from the MCP server using structured output (Ollama tool-calling API), rather than routing through an opencode subagent. This keeps judge logic deterministic and server-side.

Rationale: Routing judge calls through a subagent would add latency (context assembly, permission checks, tool overhead) and couple judge behavior to opencode's agent lifecycle. Direct Ollama calls from the MCP server are faster and more predictable.

### Consensus Engine Separated From Judge

`engine/consensus.py` is a separate module from `engine/judge.py`, not merged into it. Judge handles per-transition validation (pass/fail + reasons). Consensus handles debate synthesis (3+ agent outputs → weighted position). They compose: Judge validates first, then Consensus refines if debate ran.

Rationale: Merging them would couple prompt-based validation to debate aggregation. Separating them keeps each independently testable and replaceable.

### Bash Sandboxing Over Soft Allowlist

Application-level `bash_allowed_patterns` in `model_routing.yaml` can be bypassed by a sufficiently creative agent (e.g., command injection in a glob pattern). Replace with actual sandbox isolation:

- Linux: bubblewrap (flatpak-grade, user namespace + seccomp)
- macOS: sandbox-exec (experimental, PR #21538)

The sandbox adapter (`adapters/execution/sandbox.py`) implements `ToolAdapter` and wraps bash execution in the appropriate sandbox for the platform.

Rationale: A pattern allowlist is configuration, not enforcement. A determined agent can work around it. Sandboxing provides actual containment regardless of what command the agent constructs.

### Hidden Agent Pattern

All subagents (specs, plan, code, review, tester) and debate agents (debate-proposer, debate-critic, debate-architect) set `hidden: true`. Only the primary `dev-sdlc` agent appears in opencode's autocomplete.

Rationale: 8 visible agents pollute the command palette and confuse users. Hidden agents can still be spawned by the primary agent via `@mention` but never appear in suggestions.

### Prompt Versioning Locked at Task Creation

When prompt files change mid-task, the task uses the version locked at creation. Implementation: on `sdlc_create_task`, copy the contents of each prompt file into the task record. `sdlc_get_next_action` serves the stored text, not the live file.

Rationale: Without locking, a prompt edit while a task is in Progress can change the agent's behavior mid-execution, causing inconsistent outputs and making post-mortem analysis unreliable.

### Graphify as ToolAdapter, Not Core Layer

Graphify implements `ToolAdapter(code_graph)` — it's an adapter, not an architectural layer. This reflects the governance principle: "What weakness does it solve?" Context reduction via knowledge graph. Important, but it plugs into the adapter framework like any other capability.

Revised from earlier plans that placed Graphify as a core architecture layer. The ToolAdapter-first approach makes this distinction cleaner — Graphify is high-value but not structural.

### Parallel Debate via Existing Plugins (No Custom Debate Engine)

Avoid building a custom multi-agent debate system. Use one of two off-the-shelf opencode plugins:

- `kdco/background-agents` — parallel background task spawning per session
- `Erinable/opencode-group-discuss` — structured group discussion protocol

Selected at install time based on availability. The ConsensusEngine (`engine/consensus.py`) is format-agnostic and accepts synthesized positions from either plugin.

Rationale: Building a custom parallel debate engine is a significant effort with high maintenance cost. Both existing plugins are mature and maintained. The consensus engine consumes their output rather than managing agent lifecycle.

### Checkpoints Over Event Sourcing

Crash recovery uses point-in-time checkpoints (`engine/checkpoint.py`) rather than full event sourcing (replaying every transition). Checkpoint schema: `(task_id, phase, history, iteration_count, adapter_states)`.

Rationale: Event sourcing adds complexity (event store, replay logic, idempotency guarantees) that isn't justified for a single-server system. Checkpoints provide crash recovery with trivial complexity (write JSON, read JSON). If distributed execution is needed later, event sourcing can be added then.

### Observability as a Tracked Concern, Not an Afterthought

Structured logging is Phase 6, not buried in Phase 9 "Resilience." Both the MCP server and plugin write structured JSON logs from day one. Without observability, autonomous systems are impossible to debug.

Rationale: Most systems add observability after bugs become undebuggable. Placing it at Phase 6 (before agent config, before OAC context, before resilience hardening) ensures every phase transition, tool call, and model fallback is logged from the start of integration testing.

## Operational Semantics

### ExecutionSnapshot (Reproducibility Lock)

Prompt version locking copies prompt text into the task record. But model routing, graph templates, judge schemas, and adapter versions can also change mid-task. Lock everything at task creation:

```json
{
  "snapshot_id": "abc123@2026-05-17T12:34:56Z",
  "graph_template": "feature.yaml",
  "graph_hash": "sha256:...",
  "prompt_hashes": {
    "specs.txt": "sha256:...",
    "plan.txt": "sha256:...",
    "code.txt": "sha256:...",
    "review.txt": "sha256:...",
    "tester.txt": "sha256:..."
  },
  "model_routing_hash": "sha256:...",
  "judge_schema_hash": "sha256:...",
  "adapter_versions": {
    "ruff": "0.9.0",
    "mypy": "1.15.0",
    "pytest": "8.0.0"
  },
  "ollama_models": {
    "qwen3:8b": "digest:...",
    "qwen2.5-coder:7b": "digest:..."
  }
}
```

Stored in the task record alongside `prompt_version`. On `sdlc_get_next_action`, the task always gets the locked versions — never live files. This ensures byte-for-byte reproducibility of any task's execution environment.

### Artifact Lineage (Why Each File Changed)

The system tracks file modifications, but not _why_ they changed. Add lineage to every file modification record:

```json
{
  "file": "src/api/users.py",
  "action": "create" | "modify" | "delete",
  "reason": "Review R2 required pagination offset fix",
  "source_phase": "Coding",
  "source_span": "span_0x4f",
  "source_agent": "code",
  "depends_on": ["src/api/users.py", "src/db.py"],
  "related_decision": "Use cursor-based pagination over offset",
  "reverted_by": null
}
```

Stored as a JSON array in the task phase history. On each `sdlc_submit_output`, the agent must include a `lineage` block listing every file it touched and why. The plugin does NOT validate lineage (enforcement-only) — the MCP server's `submit_output` handler parses and stores it.

Uses:
- **Rollback**: given a phase, identify every file changed and its reason — revert selectively
- **Blame tracing**: answer "which agent/phase introduced this regression?"
- **Memory extraction**: Engram stores lineage entries as episodic memories with natural language reasons
- **Regression analysis**: compare lineage across tasks to detect patterns (e.g., "every code agent modifies db.py without tests")

Not enforced in MVP — stored as metadata. The lineage field is optional in `submit_output`. If absent, the phase history entry has `lineage: null`.

### FailureType Taxonomy

Autonomous systems need formal failure categories for adaptive retries, telemetry, and recovery policy:

```python
class FailureType(Enum):
    # Retryable — same action may succeed on retry
    RETRYABLE_MODEL = "model_timeout"         # Ollama hung, retry with backoff
    RETRYABLE_INFRA = "infra_transient"       # SQLite locked, process OOM, network glitch
    RETRYABLE_DEBATE = "debate_timeout"       # Agent didn't complete in time, retry round

    # Terminal — same action will always fail
    TERMINAL_VALIDATION = "validation_failed" # Schema check, lint, test failure
    TERMINAL_PHASE = "phase_mismatch"         # Agent in wrong phase, resync needed
    TERMINAL_SANDBOX = "sandbox_violation"    # bash command blocked by bubblewrap
    TERMINAL_DEPENDENCY = "dependency_gone"   # Model not pulled, adapter not installed
    TERMINAL_CONSENSUS = "consensus_stalemate"# Debate reached unrecoverable impasse

    # Orchestration — flow control, not errors
    ORCHESTRATION_CANCELLED = "cancelled"     # User or system cancelled the task
    ORCHESTRATION_LIMIT = "limit_reached"     # max_iterations, budget exhausted
    ORCHESTRATION_GATE = "gate_blocked"       # Approval pending, phase gate active
```

Every `sdlc_submit_output` rejection, tool.execute.before block, and debate failure maps to a `FailureType`. The orchestrator uses the category to decide: retry with backoff, escalate to user, or abort task.

### Budget Policy (Per-Graph-Template)

Prevents unbounded compute consumption on bad tasks. Defined in `config/budget_policy.yaml`:

```yaml
# Per-graph-template budget limits
feature:
  max_total_tokens: 100000       # Approximate, tracked via len(text) * ratio
  max_review_cycles: 8           # Same as SDLC_MAX_ITERATIONS default
  max_debate_rounds: 3           # Fixed protocol
  max_runtime_minutes: 60        # Wall-clock timeout from task creation
  fallback_depth: 2              # Max model fallback chain length
  max_debate_budget_tokens: 15000 # Tokens per task across all debate rounds

bugfix:
  max_total_tokens: 50000
  max_review_cycles: 4
  max_debate_rounds: 0           # Bugfixes skip debate
  max_runtime_minutes: 30
  fallback_depth: 2
  max_debate_budget_tokens: 0

research:
  max_total_tokens: 30000
  max_review_cycles: 2
  max_debate_rounds: 3
  max_runtime_minutes: 20
  fallback_depth: 1
  max_debate_budget_tokens: 10000
```

Enforcement: `ExecutionPolicy` checks budget before each phase transition. If `max_total_tokens` or `max_runtime_minutes` exceeded, returns `abort` — the FSM never sees budget logic. The trace records the budget position at termination.

### ExecutionPolicy (Separate From OrchestratorFSM)

OrchestratorFSM answers one question: `what phase comes next?` ExecutionPolicy answers: `should we proceed, retry, or abort?` This prevents OrchestratorFSM from becoming a god object.

```python
class ExecutionPolicy:
    """
    Policy decisions, not state machine logic.
    FSM calls Policy; Policy never calls FSM.
    """
    async def check_budget(self, task: Task, budget: BudgetPolicy) -> Decision
    async def classify_failure(self, error: SDLCError) -> FailureType
    async def decide_retry(self, failure: FailureType, attempt: int) -> RetryAction
    async def should_escalate(self, task: Task, history: list[PhaseRecord]) -> bool
```

FSM → Policy flow:
```
sdlc_submit_output:
  1. FSM: validate phase match
  2. Policy: check budget  → over? → abort("budget_exhausted")
  3. Policy: classify failure → terminal? → abort(reason)
  4. Policy: decide retry → retry? → increment attempt, return retry action
  5. FSM: advance to next phase (only if Policy says proceed)
```

This split ensures:
- FSM stays testable: given a phase + decision, what's next?
- Policy stays replaceable: swap budget rules, failure mappings, retry strategies without touching state machine
- Telemetry is clean: policy decisions logged independently of state transitions

Implementation: `engine/execution_policy.py`. Receives `BudgetPolicy`, `FailureType` mappings, and task history. Returns `Decision { action: "proceed" | "retry" | "abort" | "escalate", reason: str }`.

### WriteQueue (Serialized Persistence)

Parallel debate + traces + checkpoints + validation fanout create write pressure on SQLite. Even with WAL mode, concurrent writers can deadlock or degrade. Solution: a single async persistence worker.

```python
class WriteQueue:
    """
    Single-worker serialized writer. Enqueue from any coroutine.
    Worker drains FIFO sequentially. WAL mode handles reads concurrently.
    """
    async def enqueue(self, op: WriteOp) -> None           # non-blocking
    async def flush(self) -> None                          # wait until queue empty
    async def checkpoint(self) -> None                     # trigger wal_checkpoint after drain

class WriteOp:
    target: Literal["task", "trace", "checkpoint", "phase_output", "memory", "delegation"]
    action: Literal["create", "update", "delete"]
    payload: dict
    source_span: str  # for trace lineage
```

Pattern:
- Writers enqueue `WriteOp` — never block on I/O
- Single background worker drains FIFO, writes to StoreBackend
- Reads bypass the queue (WAL mode handles concurrent reads)
- `checkpoint()` drains queue first, then runs `PRAGMA wal_checkpoint(RESTART)`

This prevents deadlocks, guarantees write ordering, and makes recovery trivial (replay unconsumed queue on restart). Implementation: `runtime/write_queue.py`.

### Bubblewrap Network Isolation Risk

Current plan: `--share-net` restricted to localhost:11434 for Ollama. This blocks external egress but localhost is not inherently safe:

- Docker socket (`/var/run/docker.sock`) — if bind-mounted or available, the agent could control Docker
- Local databases — Postgres, MySQL, Redis on default ports
- SSH agents (`$SSH_AUTH_SOCK`) — key extraction risk
- Internal APIs — any service listening on localhost

Acceptable for now: the default bubblewrap config does NOT bind-mount the Docker socket, does NOT forward SSH agent, and only exposes the project workspace. But this must be audited as the system matures.

Future recommendation: **dedicated network namespace** per task — not just localhost filtering. Use `--unshare-net` completely and route Ollama traffic through a local proxy Unix socket that bridges to the host network. This eliminates all localhost attack surface except the explicitly proxied Ollama connection. The `adapters/execution/sandbox.py` should accept a `network_isolation: "localhost" | "netns" | "none"` parameter, defaulting to `"localhost"` for MVP and `"netns"` for production.

## Research Corrections & Additions

Findings from 6 batches of web searches that update or expand the plan:

### Corrections to Existing Plan

1. **No native `stop` hook** — The plan's `stop: async (input) => {...}` hook doesn't exist in the opencode plugin API (confirmed via GitHub issues #12472). Workaround must use `event` hook + `session.idle` detection + `client.session.prompt()`. Caveats: visible user message in interactive mode; race condition in `opencode run` headless mode. PR #16598/#16626 (`session.stopping`) not merged yet — cannot rely on it. Plugin code above has been updated accordingly.

2. **FastMCP specifics confirmed** — `from mcp.server.fastmcp import FastMCP` with composed lifespans via `|` operator, `Depends()` for dependency injection, `CurrentContext` for request-scoped state, `ToolError` for error reporting. Type hints auto-generate JSON Schema. `fastmcp run` CLI manages dependencies via `uv` with auto-reload on save. These are now reflected in the runtime implementation plan.

3. **SQLite WAL requires manual checkpoints** — `PRAGMA wal_checkpoint(RESTART)` must be scheduled periodically (e.g., via `asyncio` background task or after every 100 writes), or the WAL file grows unbounded. The plan already specifies `PRAGMA wal_checkpoint(TRUNCATE)` — changed to `RESTART` for better concurrency (doesn't block readers).

4. **Ollama API limitation** — `format` (structured JSON output via grammar-based sampling) and `tools` (tool calling) are mutually exclusive in the Ollama API. Judge pattern: use `format=<verdict_schema>` with `temperature=0`, parse result with Pydantic. Do NOT use the `tools` parameter for judge calls. Only use `tools` for debate synthesis calls.

5. **Graphify has native opencode installer** — `graphify opencode install` creates `.opencode/plugins/graphify.ts` + updates `AGENTS.md` automatically. Three-pass pipeline: Tree-sitter AST → whisper → LLM semantic extraction. NetworkX + Leiden clustering for community detection. MCP server mode: `graphify mcp serve --port 7812`. Re-runs only process changed files via SHA256 cache. The plan should reference this installer rather than building Graphify integration from scratch.

6. **MCP process leak known (issue #26714)** — MCP server processes can leak if opencode crashes without cleanup. Mitigation: wrap MCP server in a pidfile + systemd user service or manage via `opencode`'s managed child process feature. Documented in safety section.

### Tier 1 Additions (Include Now)

#### 1. Anchored Structured Compaction (Factory.ai Pattern)

Replace the basic state injection with a structured anchor containing five sections:

```
## SDLC Session Anchor
## Intent         — task description / goal
## Current State  — task_id, phase, phase_submitted, approval_pending
## Files Modified  — per-phase file list
## Decisions Made — key decisions recorded during phase
## Next Steps     — resume instructions
## Token Budget   — compaction timestamp, only newly-dropped spans processed
```

Only process newly-dropped spans. If an anchor already exists, merge — don't duplicate. The plugin code above already implements this pattern.

Impact: Prevents context drift across multiple compaction cycles. Without this, long-running SDLC tasks lose track of what's been decided and what files were modified.

#### 2. Observability Tracing

Add distributed tracing to every tool call and MCP request:

```
Every tool.execute.before/after:
  trace_id: string      — generated once per task
  parent_span_id: string — links to calling phase / subagent
  span_id: string       — unique per tool call

Store traces in data/traces/ as JSONL:
  { trace_id, span_id, parent_span_id, phase, tool, duration_ms, timestamp, error? }

After task completion: run trace analysis — answer "why did this tool call fail?" with causal chain.

Trace retention policy (mandatory — autonomous loops grow traces exponentially):
```
keep:
  errors:                   forever (symlink to data/traces/errors/)
  successful traces:        7 days
  compacted summaries:      permanently (1 line per task: phases, duration, token_estimate)
  raw spans (no errors):    30 days

Enforcement:
  Background job runs daily. Scans data/traces/ by trace file mtime + error flag.
  Files tagged with error=true in first span are hardlinked to data/traces/errors/.
  Successful traces older than 7d: delete.
  Raw spans older than 30d without errors: delete.
  Compacted summary written to data/traces/summaries.jsonl on task completion.
```
```

Implementation: `trace_id` generated on `sdlc_create_task`. Plugin injects `trace_id` + `parent_span_id` into `tool.execute.before` context. MCP server propagates spans across tool calls. Pattern inspired by OpenTelemetry but deliberately simpler (JSONL files, no collector daemon).

#### 3. Cross-Task Memory (Engram / Acervo MCP) — Deferred to Phase 7

Persistent knowledge graph across tasks using existing MCP servers. **Deliberately deferred to Phase 7** — memory contamination is dangerous before stable traces, lineage, and context retrieval exist. Design documented here for reference; implementation starts in Phase 7.

- **Engram** (`@joshnuss/mcp-engram`): Episodic memory — stores task outcomes, decisions, and file-change patterns as retrievable memories.
- **Acervo**: Semantic memory — embeddings-based retrieval of past phase outputs.

Integration (when implemented in Phase 7): Add as optional MCP servers in `opencode.json`. The `@plan` subagent queries Engram for "how did we solve this before?" before generating a plan. The judge queries Acervo for "are we repeating a mistake from last task?"

Architectural weakness solved: Every SDLC task starts from zero knowledge of previous tasks. Cross-task memory makes the second run on a project faster by surfacing past decisions, code patterns, and failure modes.

**Critical guard: memory confidence decay + project-scoped retrieval.** Without filtering, memory becomes contamination:
- Every memory carries a `confidence` score [0-1] and `created_at` timestamp
- On retrieval, confidence decays linearly: `effective_confidence = confidence * (1 - (days_since_creation / decay_window_days))`
- Decay window defaults to 30 days (configurable via `SDLC_MEMORY_DECAY_DAYS`)
- Retrieval is scoped to the current project directory — memories from other projects are never surfaced
- Memories below `effective_confidence < 0.15` are filtered out entirely (stale knowledge is worse than no knowledge)
- Implemented in `adapters/memory/engram.py` and `adapters/memory/acervo.py` — both wrap the MCP server calls with decay + scoping logic

#### 4. CI/CD Integration

After the SDLC task completes (Done phase), optionally:
- Auto-create a GitHub/GitLab PR with the worktree branch
- PR description includes phase history summary from `sdlc_get_status`
- Link to trace file for post-mortem analysis

Implementation: `adapters/vcs/github.py` tool adapter. Called by orchestrator after Done phase if `CI=true` env var is set. Not a core feature — opt-in.

### Tier 2 Additions (Post-Launch)

1. **Structured Debate Memory (SAMEP/MMP)** — Each debate agent output carries structured metadata: `{ claim, source_agent, responds_to, evidence_refs }`. ConsensusEngine uses this for provenance-aware synthesis instead of raw text merging. Reduces sycophantic collapse (20% base rate → 3-5% with structured memory).

2. **ACON Self-Improving Compaction** — After each task completes, compare tool calls before vs after compaction. If compaction caused re-reads (agent re-read a file it had already seen), update the compaction prompt to include that context pre-emptively in the next run.

3. **Cost Optimization with Tiered Model Routing** — Multi-model routing within a single phase: use small model (qwen3:1.7b) for initial draft, large model (qwen3:8b) for final review within the same phase. Implement via sub-spans within the phase graph.

### Tier 3 (Experimental / Deferred)

1. **E-mem Intent Routing** — Dynamic phase transitions based on task intent instead of fixed phase graph. Risk: replaces deterministic enforcement with probabilistic routing (violates priority #1).

2. **BATS Graduated Compression** — Four token budget regimes with progressive compression aggressiveness. Complex to tune per codebase.

3. **LTS Shared Memory** — RL-trained relevance filter for parallel agent outputs. Research-stage, no production implementation found.

4. **Multi-Modal Input** — Diagram/screenshot/whiteboard understanding. Increases instability, needs different model capabilities.

5. **Self-Modifying Prompts** — Prompts that rewrite themselves based on task outcomes. High instability risk. Explicitly warned against by governance principle.

## Next Steps

0. **Phase 0** — Foundation: Project structure, pixi workspace, pyproject, Ruff/Mypy/Pytest config, pre-commit, typing baseline, Pydantic models, logging bootstrap, config loader, environment handling. No business logic.
1. **Phase 1** — Enforcement Spine: ToolAdapter interface, plugin gates (single event handler, enforcement-only), OrchestratorFSM, Checkpoint, StoreBackend + SQLite, basic MCP tools, graph templates, model_routing. Prove deterministic enforcement works.
2. **Phase 2** — Deterministic Validation: Ruff, Mypy, Pytest adapters, ValidationRunner, per-transition schema_checks. Prove autonomous correction loop works.
3. **Phase 3** — Judge + Review Loop: JudgeEngine with 3-stage gate (phase match → deterministic preconditions → LLM judge), prompt version locking, infinite loop protection. No debate yet.
4. **Phase 4** — Observability: Structured logging, distributed tracing (trace_id → parent_span_id → span_id), JSONL trace storage, causal analysis. Before debate — traces needed to debug debate.
5. **Phase 5** — Context Intelligence: Graphify (knowledge graph, 71.5x reduction), Tree-sitter (AST queries). Graph context before debate improves quality. Memory (Engram/Acervo) deferred to Phase 7.
6. **Phase 6** — Structured Debate: 3-round deliberation protocol, ConsensusEngine with minority reports + residual objections + sycophantic collapse guard, debate agent prompts. After tracing + code graph exist.
7. **Phase 7** — Memory (Cross-Task): Engram (episodic) + Acervo (semantic) with confidence decay + project scoping. Only after stable traces, lineage, and context retrieval.
8. **Phase 8** — Agent Config + Skills: opencode.json (9 agents, all hidden except primary), 8 prompt files, SKILL.md.
9. **Phase 9** — OAC Context + Plugin Stack: Pattern library files, oh-my-opencode, background-agents, worktree, DCP.
10. **Phase 10** — Resilience: Bubblewrap sandbox, MCP process leak protection, CI/CD auto-PR, orphan cleanup.
11. **Phase 11** — End-to-end test: Full SDLC walkthrough with all verification checks.

## Project Structure

```
sdlc-mcp/
├── engine/                              # Core orchestration (Python)
│   ├── __init__.py
│   ├── orchestrator.py                  # OrchestratorFSM — phase transitions only (what comes next?)
│   ├── execution_policy.py              # ExecutionPolicy — should we proceed/retry/abort? budget + failure routing
│   ├── phase_graph.py                   # PhaseGraph + TransitionValidator (loads graph templates)
│   ├── judge.py                         # JudgeEngine (LLM-based, Ollama format=)
│   ├── consensus.py                     # ConsensusEngine — 3-round debate synthesis + scoring
│   ├── debate_runtime.py                # DebateRuntime — scheduling, timeouts, retries, cancellation
│   ├── schema_checks.py                 # Per-transition deterministic preconditions
│   ├── checkpoint.py                    # Checkpoint system — save/restore execution state
│   └── llm.py                           # Ollama HTTP client (httpx)
│
├── adapters/                            # ToolAdapter implementations (Python)
│   ├── __init__.py
│   ├── base.py                          # ToolAdapter ABC, ToolCapability enum
│   ├── tools/
│   │   ├── ruff.py                      # lint capability
│   │   ├── mypy.py                      # typing capability
│   │   ├── pytest.py                    # testing capability
│   │   ├── graphify.py                  # code-graph capability (knowledge graph)
│   │   └── tree_sitter.py               # code-graph capability (AST queries)
│   ├── models/
│   │   └── ollama.py                    # Model routing + fallback chains
│   ├── execution/
│   │   └── sandbox.py                   # bubblewrap sandbox
│   ├── memory/
│   │   ├── engram.py                    # Episodic memory adapter
│   │   └── acervo.py                    # Semantic memory adapter
│   └── vcs/
│       ├── git.py                       # Worktree + commit patterns
│       └── github.py                    # CI/CD PR creation
│
├── runtime/                             # MCP server facade + pipelines (Python)
│   ├── __init__.py
│   ├── __main__.py                      # Entry: python -m sdlc
│   ├── app.py                           # FastMCP init + tool/resource registration
│   ├── tools/
│   │   ├── task.py                      # create_task, get_status, list, cancel
│   │   ├── phase.py                     # get_next_action, submit_output
│   │   ├── approval.py                  # request_approval (OAC gate)
│   │   └── debug.py                     # introspection
│   ├── resources/
│   │   ├── spec.py                      # sdlc://task/{id}/spec
│   │   ├── plan.py                      # sdlc://task/{id}/plan
│   │   ├── patterns.py                  # sdlc://patterns/{name}
│   │   └── phase_graph.py               # sdlc://phase-graph
│   ├── pipelines/
│   │   └── default.py                   # Standard execution pipeline (validate → execute → check)
│   ├── store_backend.py                 # StoreBackend ABC (SQLite/Postgres swap)
│   ├── store_sqlite.py                  # SQLite StoreBackend implementation (aiosqlite, WAL)
│   ├── tracing.py                       # trace_id + span_id propagation, JSONL trace storage
│   └── logging.py                       # Structured JSON logging
│
├── validators/                          # Deterministic validation (Python)
│   ├── __init__.py
│   └── deterministic/
│       ├── runner.py                    # Runs ruff, mypy, pytest via adapters
│       └── results.py                   # Aggregated validation report
│
├── agents/                              # Agent definitions (opencode JSON config)
│   ├── opencode.json                    # Primary agent + subagent definitions
│   ├── opencode.jsonc                   # Plugin + oh-my-opencode config
│   └── AGENTS.md                        # Project rules
│
├── graphs/                              # Per-task-type phase graph templates
│   ├── feature.yaml                     # Full SDLC (default)
│   ├── bugfix.yaml                      # Skip Planning
│   ├── refactor.yaml                    # Skip Specs
│   ├── research.yaml                    # No Coding/Testing
│   └── docs.yaml                        # Documentation only
│
├── .opencode/
│   ├── plugins/
│   │   └── sdlc-enforcer.ts             # Phase enforcement + lifecycle hooks (enforcement only)
│   ├── skills/
│   │   └── sdlc/
│   │       ├── SKILL.md                 # Primary agent loop protocol
│   │       └── prompts/
│   │           ├── specs.txt
│   │           ├── plan.txt
│   │           ├── code.txt
│   │           ├── review.txt
│   │           ├── tester.txt
│   │           ├── debate-proposer.txt
│   │           ├── debate-critic.txt
│   │           └── debate-architect.txt
│   └── context/
│       ├── project/
│       │   ├── style.md                 # Coding style (OAC patterns)
│       │   ├── patterns.md              # Architecture patterns
│       │   ├── testing.md               # Test requirements
│       │   └── security.md              # Security requirements
│       └── sdlc/
│           ├── phase-guide.md           # Phase outputs defined
│           └── quality.md               # Definition of done
│
├── config/
│   ├── model_routing.yaml               # Phase → subagent mapping (shared across templates)
│   ├── budget_policy.yaml               # Per-graph-template token/cycle/runtime limits
│   └── prompts/
│       ├── judge_specs_to_planning.txt
│       ├── judge_planning_to_coding.txt
│       ├── judge_coding_to_review.txt
│       └── judge_review_to_testing.txt
│
├── pyproject.toml                       # Python dependencies
├── package.json                         # oh-my-opencode + JS plugins
├── pixi.toml                            # Development tasks
├── data/
│   ├── sdlc.db                          # SQLite database (WAL mode, via StoreBackend)
│   ├── checkpoints/                     # Checkpoint snapshots
│   ├── logs/
│   │   ├── sdlc.log                     # MCP server structured logs
│   │   └── plugin.log                   # Plugin structured logs
│   ├── traces/                          # JSONL trace files (trace_id per task)
│   └── delegations/                     # Background agent results
└── README.md
```

## Plugin: sdlc-enforcer.ts (The Enforcement Layer)

Runs inside opencode and provides hard enforcement no prompt can bypass.

```typescript
import type { Plugin } from "@opencode-ai/plugin"

interface SDLCSessionState {
  taskId: string | null
  currentPhase: string | null
  phaseSubmitted: boolean
  filesModified: string[]
  approvalPending: boolean
}

const sessions = new Map<string, SDLCSessionState>()

function getState(sessionId: string): SDLCSessionState {
  if (!sessions.has(sessionId)) {
    sessions.set(sessionId, {
      taskId: null, currentPhase: null,
      phaseSubmitted: false, filesModified: [], approvalPending: false
    })
  }
  return sessions.get(sessionId)!
}

export const SDLCEnforcer: Plugin = async ({ client }) => {
  return {

    // Single event handler: switch on event type.
    // Plugin scope: enforcement-only. State persistence, formatting, tracing = server-side.
    event: async ({ event }) => {
      const sessionId = (event as any).session_id
      if (!sessionId) return

      switch (event.type) {
        case "session.created":
          sessions.set(sessionId, {
            taskId: null, currentPhase: null,
            phaseSubmitted: false, filesModified: [], approvalPending: false
          })
          // Restore from disk (server wrote last known state)
          try {
            const stored = JSON.parse(
              await Bun.file(SDLC_PLUGIN_STATE_PATH).text()
            )
            const saved = stored[sessionId]
            if (saved) Object.assign(sessions.get(sessionId)!, saved)
          } catch {}
          break

        case "session.deleted":
          sessions.delete(sessionId)
          break

        // Stop workaround: no native stop hook (PR #16598).
        // session.idle + client.session.prompt() re-injects continuation.
        case "session.idle": {
          const state = sessions.get(sessionId)
          if (!state || !state.currentPhase || state.currentPhase === "Done") return
          if (state.phaseSubmitted) return
          await client.session.prompt({
            sessionID: sessionId,
            parts: [{
              type: "text",
              text: `[SDLC Enforcer] You are in ${state.currentPhase} phase ` +
                    `but have not called sdlc_submit_output. Complete and submit first.`
            }]
          })
          break
        }
      }
    },

    // Hard enforcement gates. Server handles formatting, tracing, state persistence.
    "tool.execute.before": async (input) => {
      const state = getState(input.sessionID)
      const tool = input.tool

      // Gate 1: Block file edits outside Coding/Testing phases
      if ((tool === "edit" || tool === "write") && state.currentPhase) {
        const allowed = ["Coding", "Testing", null]
        if (!allowed.includes(state.currentPhase)) {
          throw new Error(
            `SDLC Phase Gate: File edits blocked in ${state.currentPhase}. ` +
            `Submit your output via sdlc_submit_output first.`
          )
        }
      }

      // Gate 2: Block edits/bash if approval pending
      if (state.approvalPending &&
          (tool === "edit" || tool === "write" || tool === "bash")) {
        throw new Error(
          `SDLC Approval Gate: Awaiting user approval. ` +
          `Call sdlc_request_approval first.`
        )
      }
    },

    // Minimal session sync only. Auto-formatting, tracing, decisions = server-side.
    "tool.execute.after": async (input) => {
      const state = getState(input.sessionID)
      const tool = input.tool
      const result = input.result as string | undefined
      if (!result) return

      try {
        const parsed = JSON.parse(result)

        if (input.args?.tool === "sdlc_get_next_action") {
          if (parsed.phase) { state.currentPhase = parsed.phase; state.phaseSubmitted = false }
          if (parsed.task_id) { state.taskId = parsed.task_id }
          if (parsed.requires_approval) { state.approvalPending = true }
        }

        if (input.args?.tool === "sdlc_request_approval") {
          if (parsed.approved) { state.approvalPending = false }
        }

        if (input.args?.tool === "sdlc_submit_output") {
          if (parsed.accepted) {
            state.phaseSubmitted = true
            state.currentPhase = parsed.next_phase
            state.filesModified = []
          }
        }
      } catch {}
    },

    // Factory.ai-style anchored compaction: inject structured anchor.
    // Only processes newly-dropped spans; merges into existing anchor.
    "experimental.session.compacting": async (input, output) => {
      const state = getState(input.sessionID)
      if (!state.taskId && !state.currentPhase) return

      const existingIdx = output.context.findIndex(
        c => typeof c === "string" && c.startsWith("## SDLC Session Anchor"))
      const anchor = `## SDLC Session Anchor (CRITICAL)
## Current State
- task_id: ${state.taskId}
- current_phase: ${state.currentPhase}
- phase_submitted: ${state.phaseSubmitted}
- approval_pending: ${state.approvalPending}
## Next Steps
1. Call sdlc_get_next_action(task_id="${state.taskId}") to resync
2. Continue from the returned phase
3. Do NOT restart from Chatting
`
      if (existingIdx >= 0) {
        output.context[existingIdx] = anchor  // replace, don't append
      } else {
        output.context.push(anchor)
      }
    },
  }
}
export default SDLCEnforcer
```

## MCP Tools

### sdlc_create_task

- **Input**: `description: string`, `mode?: "auto" | "full"`
- **Output**: `task_id: string`, `initial_phase: string`
- **Logic**: Creates SQLite record, LLM complexity check in auto mode. Initializes `iteration_count: 0` and `max_iterations` from env (default 8).
- **Config validation**: On startup, server validates that `phase_graph.yaml` has no dead-end phases other than Done, model_routing covers all phases, and judge prompt files exist for each transition.

### sdlc_get_next_action (KEY TOOL)

- **Input**: `task_id: string`
- **Output**: `{ task_id, phase, subagent, prompt, context: { task_description, previous_outputs, relevant_files }, constraints: { must_produce, must_not_do, bash_allowed_patterns: string[] }, requires_approval: bool }`
- **Logic**: Looks up current phase from store, maps to subagent + prompt via model_routing.yaml, returns everything the agent needs to execute. If primary model in model_routing is unavailable, returns first available model from `fallback_models` chain.

### sdlc_submit_output (SEQUENCE GATE)

- **Input**: `task_id: string`, `phase: string`, `output: string` (max 1MB, truncated server-side)
- **Output** (accept): `{ accepted: true, next_phase: string, reason: string, iteration_count: number }`
- **Output** (reject): `{ accepted: false, error: "Phase mismatch: expected X, got Y", hint: "Call sdlc_get_next_action to resync" }`
- **Logic**: Three-stage gate before advancing:
  1. **Phase match** — HARD gate: rejects immediately if caller phase ≠ stored phase
  2. **Deterministic preconditions** — Per-transition structural checks (see below), rejects with specific missing artifacts
  3. **LLM Judge** — Only runs if deterministic preconditions pass. Evaluates quality via per-transition prompt file
  On accept: saves output, advances phase in store, increments `iteration_count`. If `iteration_count >= max_iterations` and next phase would create a Review→Coding cycle, forces transition to Done.

#### Deterministic Preconditions (Before LLM Judge)

| Transition | Structural Checks | Artifact Checks |
|---|---|---|
| Specs → Planning | Output has `## Requirements`, `## Scope`, `## Constraints` sections | N/A (no code yet) |
| Planning → Coding | Output has `## Implementation Plan`, `## File Changes`, `## Risks` sections | N/A (design phase) |
| Coding → Review | Output mentions specific files modified | Files exist on disk, parsed by tree-sitter without errors |
| Review → Testing | Output has `## Issues Found`, `## Severity`, `## Must Fix` sections | All `Must Fix` issues have corresponding test stubs |
| Testing → Done | Output has `## Test Results`, `## Coverage`, `## Failed` sections | All tests pass (exit code 0), coverage ≥ threshold |

If any check fails: `{ accepted: false, error: "Missing required section: ## Risks", hint: "Ensure your output includes all required sections" }`

The LLM judge never runs until deterministic preconditions pass.

### sdlc_request_approval (OAC GATE)

- **Input**: `task_id: string`, `phase: string`, `summary: string`
- **Output**: `{ approved: bool, feedback: string }`
- **Logic**: Presents plan summary to user, waits for explicit approval. Plugin blocks all file edits until this returns approved.

### sdlc_get_status

- **Input**: `task_id: string`
- **Output**: `{ task_id, phase, history: [...], iteration_count: number, estimated_progress: string (e.g. "35%"), created_at, updated_at }`
- **Progress**: Calculated as `((phase_index + 1) / total_phases) * 100`

### sdlc_list_tasks

- **Input**: `status?: string`
- **Output**: `{ tasks: [ {task_id, phase, description, created_at} ] }`

### sdlc_cancel_task

- **Input**: `task_id: string`
- **Output**: `{ success: boolean, cancelled_debate_agents: number }`
- **Logic**: Cancels task in store. If background debate agents are running (tracked in store), sends cancellation signal. Returns count of cancelled agents.

## MCP Resources (on-demand, agent-read)

| URI | Content | When Used |
|---|---|---|
| `sdlc://task/{id}/spec` | Full spec text from phase_history | @plan loads before planning |
| `sdlc://task/{id}/plan` | Full plan text from phase_history | @code loads before implementing |
| `sdlc://patterns/{name}` | Pattern content from `.opencode/context/project/` | @code loads project patterns |
| `sdlc://phase-graph` | phase_graph.yaml as JSON | Debug/introspection |

## Parallel Debate (Deliberation Protocol, Not Opinion Generation)

Debate follows a structured multi-round protocol based on DCI (Deliberation via Typed Epistemic Acts) and ControlMAD findings. This prevents the common failure mode where parallel opinion generation collapses into averaging.

### Protocol

```
Round 1 (parallel, independent):
  @debate-proposer (qwen3:4b,   temp:0.6)  "Defend this. Find strengths. Assign confidence [0-1]."
  @debate-critic   (deepseek-r1, temp:0.7)  "Attack this. Find weaknesses. Assign confidence [0-1]."
  @debate-architect(qwen3:4b,   temp:0.4)  "Analyze structure. Risks? Assign confidence [0-1]."

  Each agent outputs: { position, confidence, evidence_refs }

  → All outputs logged to ConsensusEngine

Round 2 (cross-exposure, structured response):
  Each agent receives the other two outputs. Must respond structurally:
  @debate-proposer: "On {critic's concern X}: counter-argument is..."
  @debate-critic:   "On {proposer's claim Y}: weakness remains because..."
  @debate-architect: "On {disagreement between proposer and critic}: structural resolution is..."

  → Minority reports extracted: positions that differ from majority by >0.3 confidence
  → Contradictions flagged: claims where proposer and critic directly conflict

Round 3 (residual objection extraction):
  Each agent lists unresolved disagreements:
  "I still disagree with {agent} on {topic} because {reason}"
  These become residual objections — surfaced to the judge but not blockading.

ConsensusEngine (server-side):
  Input: all 3 rounds of structured positions + minority reports + residual objections
  Output: {
    synthesized: "merged position with provenance weighting",
    confidence: 0-1 (calibrated by agreement strength),
    minority_report: ["proposer's dissenting view on X"],
    residual_objections: ["critic maintains concern about Y"],
    stalemate: true|false  (true = unresolvable → escalate to judge)
  }

  Weighting (per ControlMAD findings):
    - Validity-aligned reasoning weighted higher than confident-but-unsupported
    - Diversity-preserving: minority positions included in output, not averaged away
    - Sycophantic collapse guard: if all 3 agents converge to identical position,
      ConsensusEngine checks confidence correlations — if suspicious (>0.95),
      flags for judge review
```

### DebateRuntime (Orchestration, Separate From ConsensusEngine)

ConsensusEngine handles reasoning (synthesis, weighting, minority reports). DebateRuntime handles operational concerns:

```python
class DebateRuntime:
    """
    Stateless scheduler that manages debate agent lifecycle.
    ConsensusEngine is pure logic — DebateRuntime is pure orchestration.
    """
    async def schedule_round(agents: list[str], phase: str) -> list[DebateOutput]
    async def handle_timeout(agent: str, timeout_s: int) -> None
    async def retry_failed(agent: str, max_retries: int = 2) -> DebateOutput | None
    async def cancel_all(task_id: str) -> int  # returns count of cancelled
    async def cleanup_stale(delay_s: int = 300) -> int
```

Key behaviors:
- **Timeouts**: each agent gets `DEBATE_ROUND_TIMEOUT` (default 60s). If agent hangs, mark as `did_not_complete`, continue without them. Never block the parent phase on one hung agent.
- **Retries**: transient failures (Ollama timeout, connection reset) retry up to 2 times with 5s backoff. Terminal failures (model not found, permission denied) surface immediately.
- **Partial completion**: if 2 of 3 agents complete, proceed with partial synthesis. The minority report flags the missing position as `absent`. Only abort if 0 of 3 complete.
- **Cancellation semantics**: `cancel_all()` sets a shared `Atomic[bool]` flag. Each agent checks this flag before starting a round. If set, returns `{ cancelled: true }` immediately.
- **Stale cleanup**: background task runs every 5 minutes, cleans up agent processes that completed but were never collected (orphaned by parent crash).

Implementation: `engine/debate_runtime.py`. Standalone from `engine/consensus.py`. The debate tool in the MCP server calls DebateRuntime, then passes results to ConsensusEngine.

## Phase Graph Templates

Instead of a single phase graph, the system uses per-task-type graph templates. Task creation selects the template via `sdlc_create_task(mode=)`. This preserves determinism without probabilistic intent routing.

### Graph Templates

```
graphs/
  feature.yaml     (default)  Specs → Planning → Coding → Review → Testing → Done
  bugfix.yaml                 Specs → Coding → Review → Testing → Done
  refactor.yaml               Planning → Coding → Review → Testing → Done
  research.yaml               Specs → Planning → Review → Done
  docs.yaml                   Specs → Coding → Review → Done
```

### feature.yaml (Default)

```
Chatting ──> Specs ──> Planning ──> Coding ──> Review ──> Testing ──> Done
                                         ↑          │
                                         └──────────┘  (changes required)
   Chatting → Done (small talk)
   Chatting → Coding (simple prompts, no Planning needed)
```

### bugfix.yaml

```
Chatting ──> Specs ──> Coding ──> Review ──> Testing ──> Done
                               ↑          │
                               └──────────┘
```

Skips Planning — bugfixes go straight from spec to implementation.

### refactor.yaml

```
Chatting ──> Planning ──> Coding ──> Review ──> Testing ──> Done
                                      ↑          │
                                      └──────────┘
```

Skips Specs — refactoring has no new requirements.

### research.yaml

```
Chatting ──> Specs ──> Planning ──> Review ──> Done
```

No Coding or Testing — research produces findings, not code.

### docs.yaml

```
Chatting ──> Specs ──> Coding ──> Review ──> Done
```

Documentation-only tasks skip Planning and Testing.

### Graph Template Rules

- All templates share the same enforcement hooks (plugin gates don't change)
- All templates share the same model routing (model_routing.yaml maps phase → subagent regardless of template)
- Task creation: `sdlc_create_task(description, mode="feature" | "bugfix" | "refactor" | "research" | "docs")`
- Mode defaults to `"feature"` if unspecified
- Graph templates are validated at startup: no dead ends, all phases reachable, all phases map to model_routing entries

## Model / Subagent Routing

```yaml
phases:
  Specs:
    subagent: specs
    model: qwen3:4b
    fallback_models: [qwen3:1.7b, llama3.2:3b]
    edit: deny
    bash: deny

  Planning:
    subagent: plan
    model: qwen3:4b
    fallback_models: [qwen3:1.7b, deepseek-r1:1.5b]
    edit: deny
    bash: deny
    debate: true

  Coding:
    subagent: code
    model: qwen2.5-coder:3b
    fallback_models: [qwen2.5-coder:1.5b, llama3.2:3b]
    edit: allow
    bash: allow
    bash_allowed_patterns: ["test", "build", "lint", "format", "install", "npm *", "pip *", "pixi *"]

  Review:
    subagent: review
    model: qwen2.5-coder:7b
    fallback_models: [qwen2.5-coder:3b, qwen3:4b]
    edit: deny
    bash: deny
    debate: true

  Testing:
    subagent: tester
    model: qwen3:4b
    fallback_models: [llama3.2:3b]
    edit: allow
    bash: allow
    bash_allowed_patterns: ["test", "pytest *", "npm test *", "pixi run test*"]

  Done: {}
```

## SKILL.md (Primary Agent — Short, Stable)

```markdown
# SDLC Orchestrator

You manage a software development lifecycle via MCP tools.
The MCP server decides what happens next. You execute.

## Your Loop

### 1. Create Task
→ sdlc_create_task(description, mode="full")
→ Save task_id

### 2. Get Next Action
→ sdlc_get_next_action(task_id)
Returns: subagent, prompt, context, constraints, requires_approval

### 3. Handle Approval Gate (if requires_approval=true)
Present to user: "Here is the plan. Do you approve?"
→ sdlc_request_approval(task_id, phase, summary)
Wait for user response.

### 4. Delegate to Subagent
Spawn @<subagent> with the prompt+context from MCP.
Collect the full output.

### 5. Submit
→ sdlc_submit_output(task_id, phase, output)

If rejected (accepted:false), call sdlc_get_next_action to resync.

### 6. Repeat
If next_phase == "Done": summarize and stop.
Else: go to Step 2.

## Your Direct Responsibilities
- Git commits after Coding phase completes
- Progress updates to user
- Handling user interruptions gracefully

## What You Never Do
- Edit code yourself
- Make phase transition decisions
- Tell subagents what phase comes next
```

## opencode.json

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcpServers": {
    "sdlc-orchestrator": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "sdlc"],
      "env": {
        "SDLC_DB_PATH": "./data/sdlc.db",
        "SDLC_PLUGIN_STATE_PATH": "./data/plugin_state.json",
        "SDLC_CONFIG_DIR": "./config",
        "SDLC_LOG_PATH": "./data/sdlc.log",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "SDLC_JUDGE_MODEL": "qwen3:8b",
        "SDLC_MAX_ITERATIONS": "8",
        "SDLC_BASH_ALLOWED_PATTERNS": "test, build, lint, format, install, git"
      }
    }
  },
  "instructions": [
    "AGENTS.md",
    ".opencode/context/project/style.md",
    ".opencode/context/project/patterns.md"
  ],
  "agent": {
    "dev-sdlc": {
      "mode": "primary",
      "model": "ollama/qwen3:8b",
      "temperature": 0.25,
      "prompt": "{file:.opencode/skills/sdlc/SKILL.md}",
      "permission": {
        "edit": "ask",
        "bash": "ask",
        "task": { "specs": "allow", "plan": "allow", "code": "allow",
                  "review": "allow", "tester": "allow" }
      }
    },
    "specs": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen3:4b", "temperature": 0.3,
      "prompt": "{file:.opencode/skills/sdlc/prompts/specs.txt}",
      "permission": { "edit": "deny", "bash": "deny", "glob": "allow", "grep": "allow", "read": "allow" }
    },
    "plan": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen3:4b", "temperature": 0.4,
      "prompt": "{file:.opencode/skills/sdlc/prompts/plan.txt}",
      "permission": { "edit": "deny", "bash": "deny", "glob": "allow", "grep": "allow", "read": "allow",
                      "task": { "debate-proposer": "allow", "debate-critic": "allow",
                                "debate-architect": "allow", "*": "deny" } }
    },
    "code": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen2.5-coder:3b", "temperature": 0.2,
      "prompt": "{file:.opencode/skills/sdlc/prompts/code.txt}",
      "permission": { "edit": "allow", "bash": "allow" }
    },
    "review": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen2.5-coder:7b", "temperature": 0.3,
      "prompt": "{file:.opencode/skills/sdlc/prompts/review.txt}",
      "permission": { "edit": "deny", "bash": "deny", "glob": "allow", "grep": "allow", "read": "allow",
                      "task": { "debate-proposer": "allow", "debate-critic": "allow",
                                "debate-architect": "allow", "*": "deny" } }
    },
    "tester": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen3:4b", "temperature": 0.1,
      "prompt": "{file:.opencode/skills/sdlc/prompts/tester.txt}",
      "permission": { "edit": "allow", "bash": "allow", "glob": "allow", "grep": "allow", "read": "allow" }
    },
    "debate-proposer": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen3:4b", "temperature": 0.6,
      "prompt": "{file:.opencode/skills/sdlc/prompts/debate-proposer.txt}",
      "permission": { "read": "allow", "glob": "allow", "grep": "allow" }
    },
    "debate-critic": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/deepseek-r1:1.5b", "temperature": 0.7,
      "prompt": "{file:.opencode/skills/sdlc/prompts/debate-critic.txt}",
      "permission": { "read": "allow", "glob": "allow", "grep": "allow" }
    },
    "debate-architect": {
      "mode": "subagent", "hidden": true,
      "model": "ollama/qwen3:4b", "temperature": 0.4,
      "prompt": "{file:.opencode/skills/sdlc/prompts/debate-architect.txt}",
      "permission": { "read": "allow", "glob": "allow", "grep": "allow", "mcp": "allow" }
    }
  }
}
```

## Dependencies

### Python (pyproject.toml — root workspace)

```toml
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "aiosqlite>=0.20.0",
]
```

### JavaScript (package.json)

```json
{
  "name": "sdlc-opencode-config",
  "dependencies": {
    "oh-my-opencode": "latest",
    "@tarquinen/opencode-dcp": "latest"
  }
}
```

### OCX Extensions (installed via `ocx add`)

```bash
ocx add kdco/background-agents
ocx add felixAnhalt/opencode-worktree-session
```

## What Gets Dropped from Original Server

| Original File | Reason |
|---|---|
| `latest/src/server.py` | No HTTP server needed |
| `latest/src/orchestrator.py` | Logic moves to MCP tools + SKILL.md |
| `latest/src/upstream.py` | Replaced by `engine/llm.py` |
| `latest/src/protocol.py` | No SSE streaming |
| `latest/src/sse.py` | No SSE |
| `latest/src/prefetch.py` | No OPT VRAM management |
| `latest/src/smalltalk.py` | Not applicable |
| `latest/src/nightly.py` | Not applicable |
| `latest/src/continue_bridge.py` | No Continue bridge needed |
| `latest/src/event_bus.py` | Internal pub/sub, optional |
| `latest/src/logging_*.py` | Simplified |
| `latest/src/config.py` | Rewritten (67 → ~25 vars) |
| `latest/src/contracts.py` | Rewritten |
| `latest/prompt_contracts.yaml` | Replaced by `.opencode/skills/sdlc/prompts/*.txt` |
| `latest/src/engine/debate_coordinator.py` | Replaced by parallel background debate agents |

## What Gets Rewritten

| New File | Inspired By |
|---|---|
| `engine/phase_graph.py` | `latest/src/transition.py` |
| `engine/judge.py` | `latest/src/judge.py` |
| `engine/consensus.py` | New — debate synthesis |
| `engine/checkpoint.py` | New — crash recovery |
| `runtime/store.py` | `latest/src/store.py` |
| `runtime/schemas.py` | `latest/src/schemas.py` |
| `runtime/config.py` | `latest/src/config.py` |
| `engine/llm.py` | `latest/src/upstream.py` (simpler) |
| `adapters/base.py` | New — ToolAdapter ABC |
| `validators/deterministic/runner.py` | New — aggregated validation |

## Build Order

### Phase 0 — Foundation

Establish clean project structure, Python workspace, tooling baseline, typed configuration, and deterministic development environment. No business logic — this phase exists so Phase 1 doesn't start with ad-hoc scaffolding.

Files: `pyproject.toml`, `pixi.toml`, `src/sdlc/__init__.py`, `src/sdlc/config.py`, `src/sdlc/logging.py`, `src/sdlc/exceptions.py`, `src/sdlc/models.py`, `tests/__init__.py`, `tests/conftest.py`, `.pre-commit-config.yaml`, `setup.cfg` (mypy config), `data/`, `graphs/`, `.opencode/`
Test: `pixi run lint && pixi run typecheck && pixi run test` all pass. `python -c "from sdlc import config; print(config.settings)"` loads without error.
Key details:
- Python 3.12+, async-first design.
- `pyproject.toml`: ruff (all rules), mypy (strict), pytest + pytest-asyncio, dev dependencies.
- `pixi.toml`: tasks for `lint`, `typecheck`, `test`, `all`, `clean`.
- Pydantic `BaseSettings` for config (YAML + env var overrides). `Settings` model loads from `config/` directory.
- `logging.py`: structured JSON logging with `structlog` or standard library `logging` + JSON formatter. Bootstrap function called once at startup.
- `exceptions.py`: `SDLCError` base class with `FailureType` taxonomy. All server exceptions inherit from this.
- `models.py`: type definitions for shared state (Task, PhaseRecord, Checkpoint, BudgetPolicy, etc.) using Pydantic. Only data shapes — no business logic.
- `conftest.py`: pytest fixtures for temp directories, mock StoreBackend, sample phase graphs.
- `.pre-commit-config.yaml`: ruff + mypy on commit.
- Directory structure matches `sdlc/` project root from architecture. No code in Phase 0 that references MCP, FSM, adapters, or orchestration.
- TODO markers allowed for imports/exports that will be filled in future phases (e.g., `# TODO: Phase 1 — import orchestrator`).

### Phase 1 — Enforcement Spine
Prove deterministic enforcement works. No debate, no Graphify, no memory, no tracing.

Files: `adapters/base.py`, `engine/orchestrator.py`, `engine/execution_policy.py`, `engine/phase_graph.py`, `engine/checkpoint.py`, `runtime/store_backend.py`, `runtime/store_sqlite.py`, `runtime/write_queue.py`, `runtime/__main__.py`, `runtime/app.py`, `runtime/tools/task.py`, `runtime/tools/phase.py`, `graphs/feature.yaml`, `.opencode/plugins/sdlc-enforcer.ts`, `config/model_routing.yaml`
Test: Open opencode, create a task, advance through phases, verify plugin blocks edits in Specs. Kill server mid-phase, restart, verify checkpoint restore.
Key details:
- `ToolAdapter` ABC with `validate`, `execute`, `healthcheck`. Zero implementations yet — contract only.
- **`OrchestratorFSM` only answers**: "what phase comes next?" Never sees budgets, retries, or failure classification. Keeps FSM testable and simple.
- **`ExecutionPolicy`** answers: "should we proceed, retry, or abort?" Receives `BudgetPolicy`, `FailureType` mappings, task history. Returns `Decision { action, reason }`.
- **`WriteQueue`**: single-worker serialized writer. All persistence (tasks, traces, checkpoints, phase outputs) enqueues `WriteOp`. Worker drains FIFO. Reads bypass queue via WAL mode. `checkpoint()` drains first then runs `PRAGMA wal_checkpoint(RESTART)`.
- `Checkpoint` snapshots to `data/checkpoints/` as JSON. Restore on server restart.
- `StoreBackend` ABC + `store_sqlite.py` with aiosqlite, WAL mode, `busy_timeout=5000`, `BEGIN IMMEDIATE`, manual `wal_checkpoint(RESTART)`.
- `sdlc-enforcer.ts`: single `event` handler (session.created/deleted/idle), `tool.execute.before` (hard phase + approval gates), `tool.execute.after` (minimal sync), `experimental.session.compacting` (anchored state injection). **Enforcement only** — no formatting, no tracing, no decision recording.
- Plugin state persisted per-session in `data/plugin_state/<session>.json` with atomic `rename()` writes.
- `graphs/feature.yaml` as default template. Others added later.
- `sdlc_create_task(description, mode="feature")` selects graph template. `sdlc_get_next_action` and `sdlc_submit_output` drive transitions.
- Config validation on startup: graph template validity, model_routing coverage, Ollama ping.
- MCP server runs via `python -m sdlc` (FastMCP, stdio transport).
- Testing: Unit test ToolAdapter ABC, phase graph validation, ExecutionPolicy budget checks, WriteQueue drain ordering. Integration test with opencode against temp project.

### Phase 2 — Deterministic Validation
Add real enforcement power — lint, typing, testing adapters + schema checks + validation runner.

Files: `adapters/tools/ruff.py`, `adapters/tools/mypy.py`, `adapters/tools/pytest.py`, `validators/deterministic/runner.py`, `validators/deterministic/results.py`, `engine/schema_checks.py`
Test: Run each adapter against known-good and known-bad files. Run combined `ValidationRunner`. Test schema_checks against outputs with missing sections.
Key details:
- Each adapter implements `ToolAdapter` — `RuffAdapter(lint)`, `MypyAdapter(typing)`, `PytestAdapter(testing)`.
- `ValidationRunner` runs adapters in parallel via `asyncio.gather`, aggregates into `ValidationReport { passed, results: [{ adapter, severity, message, location }] }`.
- `schema_checks.py` defines per-transition deterministic preconditions (required sections, artifact existence). Used by `sdlc_submit_output` before LLM judge.
- `OrchestratorFSM.update()` calls `ValidationRunner` during Review phase, runs schema_checks on every `submit_output`.
- Testing: pytest with sample files that pass/fail each tool. Parametrized schema checks per transition type.

### Phase 3 — Judge + Review Loop
Add LLM-based transition evaluation, but ONLY after deterministic loop stability is proven.

Files: `engine/judge.py`, `config/prompts/judge_*.txt`, `engine/orchestrator.py` (update submit_output pipeline)
Test: Run judge on sample outputs from Phase 2. Verify transitions match phase_graph. Verify deterministic preconditions reject before LLM runs. Verify ExecutionSnapshot locks work.
Key details:
- Three-stage gate: phase match → deterministic preconditions (schema_checks) → LLM Judge
- **ExecutionSnapshot** captured at task creation: graph_hash, prompt_hashes, model_routing_hash, judge_schema_hash, adapter_versions, ollama_model_digests. Task always executes against locked versions — never live files.
- Every rejection maps to a `FailureType` category: `RETRYABLE_MODEL`, `TERMINAL_VALIDATION`, `PHASE_MISMATCH`, etc. Orchestrator uses category for retry/abort decisions.
- `JudgeEngine` loads per-transition prompt files, calls Ollama with `format=<verdict_schema>` (NOT `tools`), temperature=0. Returns `{ pass: bool, reasons: string[] }`.
- Falls back to generic hardcoded prompt if prompt file missing.
- Prompt version locking: prompts copied into task record at creation time — mid-task edits don't affect running tasks.
- Infinite loop protection: `max_iterations` (default 8). At 80% threshold, `oscillation_warning: true`. On exceed, forces Done.
- No debate yet. Review → Coding loop is controlled by judge alone.
- Testing: pytest parametrized per transition type — sample outputs, empty output, garbage output, boundary values.

### Phase 4 — Observability
Add structured logging and distributed tracing. Placed before debate — traces are essential for debugging debate instability.

Files: `runtime/logging.py`, `runtime/tracing.py`, `data/logs/`, `data/traces/`, `runtime/tools/debug.py`
Test: Run a full task via integration test, verify every phase transition and tool call is logged as structured JSON. Query trace file by trace_id, verify parent-child span relationships.
Key details:
- MCP server writes JSON lines to `data/logs/sdlc.log`. Plugin writes to `data/logs/plugin.log`.
- Log schema: `{ timestamp, level, event, task_id?, phase?, duration_ms?, model?, token_estimate? }`.
- Distributed tracing: `trace_id` (per task) → `parent_span_id` (phase/subagent) → `span_id` (per tool call).
- Traces stored in `data/traces/` as JSONL. Post-task causal analysis by `trace_id`.
- Pattern: OpenTelemetry-inspired but simpler (JSONL files, no collector, no sampling).
- **Trace retention policy**: errors → forever (hardlinked to `data/traces/errors/`), successful traces → 7d, compacted summaries → permanently (`data/traces/summaries.jsonl`), raw spans without errors → 30d. Daily background job enforces limits.
- `sdlc_get_status` returns progress, phase timing, token estimates.

### Phase 5 — Context Intelligence
Graphify and tree-sitter — now the system can understand the codebase it's modifying. Cross-task memory (Engram/Acervo) deliberately deferred to Phase 7: memory contamination is dangerous before stable traces, lineage, and context retrieval exist.

Files: `adapters/tools/graphify.py`, `adapters/tools/tree_sitter.py`, `runtime/pipelines/default.py` (update)
Test: Feed a codebase to Graphify, verify dependency graph. Run tree-sitter query, verify AST matches.
Key details:
- **Graphify**: `graphify opencode install` first, then wrap as `GraphifyAdapter(code_graph)`. 3-pass AST+whisper+LLM. Leiden clustering. 71.5x token reduction. MCP server mode on port 7812. SHA256 change cache.
- **Tree-sitter**: 305+ languages via `tree-sitter-language-pack`. Syntax-aware chunking (never splits a function). Incremental re-parsing.
- All implement `ToolAdapter`. Default pipeline fetches dependency graph before Coding phase.
- Memory adapters (`adapters/memory/engram.py`, `adapters/memory/acervo.py`) are NOT built here — deferred to Phase 7.
- Testing: Integration test with multi-file project. Graphify dependency graph matches expected structure.

### Phase 6 — Structured Debate
Debate placed after observability and code graph exist. Without traces + graph context, debate quality is shallow and difficult to debug.

Files: `engine/consensus.py`, `engine/debate_runtime.py`, `.opencode/skills/sdlc/prompts/debate-{proposer,critic,architect}.txt`, `agents/opencode.json` (add debate agent stubs)
Test: Run 3-round debate with mock agents. Verify minority reports extracted, residual objections surfaced, sycophantic collapse detected. Verify DebateRuntime handles timeouts, retries, and partial completion.
Key details:
- **DebateRuntime** (separate from ConsensusEngine): manages scheduling, timeouts (60s per agent), retries (2 with 5s backoff), cancellation, partial completion (proceed if ≥2 of 3 agents complete), stale cleanup (every 5min).
- 3-round protocol: parallel independent (Round 1) → cross-exposure structured response (Round 2) → residual objection extraction (Round 3).
- **ConsensusEngine** (pure logic, no orchestration): produces `{ synthesized, confidence, minority_report, residual_objections, stalemate }`.
- Weighting: validity-aligned reasoning > confident-but-unsupported. Diversity-preserving: minority positions included, not averaged away.
- Sycophantic collapse guard: >0.95 confidence correlation across all 3 agents → flag for judge review.
- Agents spawned via `kdco/background-agents` (or `Erinable/opencode-group-discuss` based on availability).
- All debate agents `hidden: true`.
- Budget enforcement: `config/budget_policy.yaml` limits debate rounds and tokens per graph template. Bugfix templates skip debate entirely (`max_debate_rounds: 0`).
- Testing: pytest with controlled input — verify minority reports appear, verify stalemate flag triggers at confidence threshold, verify timeout doesn't block parent phase.

### Phase 7 — Memory (Cross-Task)
Engram (episodic) + Acervo (semantic) with confidence decay + project scoping. Deliberately deferred until Phase 7 — noisy memory contamination is dangerous early. Only built after stable traces, lineage, context retrieval, and orchestration exist.

Files: `adapters/memory/engram.py`, `adapters/memory/acervo.py`, `runtime/pipelines/default.py` (update)
Test: Store memory, retrieve with project-scoped query, verify confidence decay filters old entries. Verify no cross-project contamination.
Key details:
- **Cross-task memory (optional)**: Engram (episodic) + Acervo (semantic). `@plan` queries before planning: "How did we solve this before?" Judge queries: "Are we repeating a mistake?"
- **Memory guards**: `effective_confidence = confidence * (1 - (days / decay_window))`. Project-scoped retrieval only. Filter below 0.15 confidence.
- Both implement `ToolAdapter`. Called from default pipeline if memory servers are configured.
- Not enabled by default — opt-in via config flag `memory_enabled: true`.
- Testing: store + retrieve + verify decay filters old memories. Verify project-scoped isolation.

### Phase 8 — Agent Config + Skills
Wire opencode agent definitions, skill file, and all 8 prompt files.

Files: `agents/opencode.json`, `agents/opencode.jsonc`, `.opencode/skills/sdlc/SKILL.md`, `.opencode/skills/sdlc/prompts/*.txt`
Test: Open opencode, give trivial task, watch Chatting → Specs → Planning → Coding flow.
Key details:
- 9 agents: 1 primary (dev-sdlc), 5 phase subagents, 3 debate agents. All hidden except primary.
- Permission model per subagent: @code allows edit/bash, @plan allows only read/grep/glob/background-agents.
- Prompt files versioned in git. Locked at task creation (`prompt_version: git_hash`).
- SKILL.md: short, stable, focused on the MCP tool loop.
- Testing: Create temp project with these configs, run opencode, verify skill loads and permissions apply.

### Phase 9 — OAC Context + Plugin Stack
Pattern library files and third-party plugin installation.

Files: `.opencode/context/project/*.md`, `.opencode/context/sdlc/*.md`, oh-my-opencode, background-agents, worktree, DCP installation
Test: Verify Context7 fetches live docs. Verify worktree creates `sdlc/<task_id>-<slug>` branch. Verify DCP prunes context between phases.
Key details:
- Context files: style.md, patterns.md, testing.md, security.md (project-level), phase-guide.md, quality.md (sdlc-level).
- Third-party: oh-my-opencode (LSP, AST-Grep, Context7), kdco/background-agents (parallel debate), felixAnhalt/opencode-worktree (git isolation), @tarquinen/opencode-dcp (dynamic context pruning).
- Worktree branch format: `sdlc/<task_id>-<slug>`.

### Phase 10 — Resilience
Production hardening — sandboxing, crash recovery hardening, MCP process leak protection.

Files: `adapters/execution/sandbox.py`, `adapters/vcs/github.py`, `engine/orchestrator.py` (hardening)
Test: Kill server mid-phase → restart → verify checkpoint restore. Force 6 Review→Coding cycles → verify 7th returns Done. Verify bubblewrap blocks egress to internet (only localhost:11434).
Key details:
- **Bubblewrap sandbox**: `--unshare-all`, `--ro-bind /usr`, `--bind /workspace`, localhost-only `--share-net`, env sanitization. No root daemon.
  - **Filesystem policy tiers**: sandbox config accepts three path tiers (prevents agents from deleting repo internals or mutating hidden infrastructure):
    ```yaml
    sandbox:
      readonly_paths:    ["/usr", "/etc", "/nix/store", "/opt"]
      writable_paths:    ["/workspace/src", "/workspace/tests", "/workspace/data"]
      denied_paths:      ["/workspace/.git", "/workspace/data/plugin_state", "/workspace/data/traces"]
    ```
    Bubblewrap translates these to `--ro-bind`, `--bind`, and omission (not mounted = inaccessible).
    Enforcement: `adapters/execution/sandbox.py` accepts `filesystem_policy` parameter. Default policy grants read-write to workspace/src and tests, read-only to system paths, denies access to .git and data/ directories.
  - **Network risk note**: localhost-only is NOT inherently safe — Docker socket, local DBs, SSH agents, and internal APIs are all reachable. MVP accepts this risk (Docker socket and SSH agent are NOT bind-mounted). Future: `adapters/execution/sandbox.py` should support `network_isolation: "netns"` mode using `--unshare-net` with a Unix socket proxy for Ollama traffic.
- **MCP process leak**: PID file at `data/sdlc.pid`, stale PID cleanup. systemd user service.
- **CI/CD (optional)**: `adapters/vcs/github.py` auto-creates PR with phase history after Done if `CI=true`.
- Infinite loop protection hardened with `max_iterations` and oscillation warning at 80%.
- Orphaned agent cleanup: cancellation flag read by debate agents before each round.

### Phase 11 — End-to-End
Full run: "Build a REST API endpoint that returns paginated user list"

Verify:
- Plugin state survives opencode restart
- Approval gate fires before @code starts
- Plugin blocks edit calls in Specs phase (single event handler, no duplicates)
- Enforcement-only plugin: no formatting, tracing, or decision recording in plugin code
- Phase transitions follow selected graph template (feature.yaml by default)
- Graph template selection: feature, bugfix, refactor, research, docs all produce correct phase sequences
- Deterministic preconditions on every submit_output: missing sections rejected before LLM runs
- Deterministic validation runs during Review (ruff, mypy, pytest)
- Judge runs only after preconditions pass; structured output via Ollama `format=`
- 3-round debate: parallel (R1) → cross-exposure (R2) → residual extraction (R3) with minority reports
- Sycophantic collapse guard: 3 agents with identical positions flagged
- @code loads dependency graph + pattern context automatically
- Cross-task memory (if Phase 7 enabled): run two tasks, verify @plan queries Engram/Acervo on second run, memory decay filters old entries
- Compaction preserves structured anchor (state, decisions, next steps) across multiple compact cycles
- Trace files in `data/traces/` contain trace_id → parent_span_id → span_id chains
- Observability logs contain all expected events (phase transitions, model fallbacks, tool calls)
- Checkpoint recovery: kill server mid-Review, restart, verify it resumes
- Bubblewrap sandbox: verify egress blocked (only localhost:11434 allowed)
- CI/CD: verify PR auto-created when `CI=true`, with phase history in description
- Done state reached, branch committed

## One-Command Install (Target State)

```bash
pip install -e . && \
npm install && \
ocx add kdco/background-agents && \
ocx add felixAnhalt/opencode-worktree-session && \
python -m sdlc init && \
opencode
```

---

## Resilience & Recovery

### Plugin State Persistence (One File Per Session, Atomic Writes)

The plugin's `Map<string, SDLCSessionState>` is in-memory and dies on opencode restart. Use one file per session — never a single JSON blob (concurrent write corruption risk).

```
Plugin state directory: data/plugin_state/
  <session_id>.json       ← one file per session
  <session_id>.json.tmp   ← temp file during atomic write

Plugin lifecycle:
  session.created → read state from data/plugin_state/<session_id>.json (if exists)
  tool.execute.after (on sdlc_*) → atomic write:
    1. Write to <session_id>.json.tmp
    2. rename() to <session_id>.json  (atomic on same filesystem)
  session.deleted → unlink(<session_id>.json)

State file format (JSON per session):
{
  "taskId": "abc123",
  "currentPhase": "Coding",
  "phaseSubmitted": false,
  "approvalPending": false,
  "filesModified": ["src/api.py"],
  "updatedAt": "2026-05-17T12:34:56Z"
}
```

On restart: plugin reads all `.json` files in `data/plugin_state/`, restores active sessions. If MCP server is also down, sessions sit in "stale" state until `sdlc_get_next_action` resyncs.

Locking: not needed — each session has its own file, and only the owning session writes to it. The `rename()` atomic write guarantees partial-write immunity even on crash.

### MCP Server Crash Mid-Phase

If the agent calls `sdlc_get_next_action` and the MCP server is down:

```
Skill instruction to agent:
  Retry with exponential backoff: 3s, 9s, 27s (3 attempts)
  If all fail: report to user, "SDLC server is down. Run `python -m sdlc` to restart."
  Do NOT proceed without MCP guidance.
```

MCP server should be configured as a systemd user service or launched as an opencode managed child process (opencode restarts it).

### Model Fallback Chains

When `model_routing.yaml` specifies a primary model and it's unavailable (not pulled, Ollama down):

```
sdlc_get_next_action logic:
  1. Try primary model (e.g., qwen2.5-coder:3b)
  2. If HTTP 404 / not found → try fallback_models[0] (e.g., qwen2.5-coder:1.5b)
  3. If also unavailable → try fallback_models[1]
  4. If none available → return error with hint:
     "None of the configured models for Coding are available.
      Run: ollama pull qwen2.5-coder:3b"
```

The response from `get_next_action` includes the actual model being used so the agent knows.

### Orphaned Background Agent Cleanup

If a task is cancelled mid-debate, 3 parallel debate agents may still be running:

```
sdlc_cancel_task:
  1. Mark task as cancelled in store
  2. Set cancellation_flag for each active_debate_agent
  3. Debate agents check this flag before each round:
     if cancelled: return { cancelled: true } and exit

Plugin event handler (session.idle) also checks:
  If task is cancelled, don't force continuation.

Background agents plugin (kdco/background-agents) supports:
  .cancelAll() for the session — call on cancel.
```

---

## Safety & Guardrails

### Bash Command Allowlist

Not all bash commands are safe during @code phase. Each phase in `model_routing.yaml` can specify `bash_allowed_patterns`:

```yaml
Coding:
  subagent: code
  model: qwen2.5-coder:3b
  bash: allow
  bash_allowed_patterns:
    - "npm *"
    - "pip *"
    - "pixi *"
    - "test"
    - "build"
    - "lint"
    - "format"
    - "install"
    - "git *"
    - "python *"
    - "pytest *"
    - "ruff *"
    - "prettier *"
    - "mkdir *"
    - "cp *"
    - "mv *"
    - "rm *"
    - "cat *"
    - "echo *"
    - "which *"
    - "ls *"
    - "pwd"
```

Enforcement:
- Plugin `tool.execute.before` checks bash command against patterns
- If command doesn't match any pattern → blocked with error listing allowed patterns
- `sdlc_submit_output` also validates logged bash commands against patterns
- Pattern matching uses glob-style matching (`*` as wildcard)

### Phase Output Size Limit

Subagent outputs could be megabytes. Protect against that:

```
sdlc_submit_output:
  Soft limit: 1MB
  Hard limit: 5MB
  < 1MB: accepted as-is
  1MB-5MB: accepted with warning "output truncated to X characters"
  > 5MB: rejected with error "output exceeds maximum size"

Plugin can enforce this preemptively by warning the subagent:
  "Your output is approaching the 1MB limit."
```

### Infinite Loop Protection (Oscillation Detection)

Review ↔ Coding could oscillate forever:

```
Per-task state:
  iteration_count: increments on every phase transition
  max_iterations: 8 (from env SDLC_MAX_ITERATIONS)

On Review → Coding transition:
  if iteration_count >= max_iterations:
    force next_phase = "Done"
    reason = "max_iterations_reached — review cycle completed"
  
  At 80% threshold:
    sdlc_get_next_action includes oscillation_warning: true
    Agent is instructed to be more thorough in review

Configurable via SDLC_MAX_ITERATIONS env var.
```

---

## Missing Concrete Details

### Branch Naming Convention

Worktree plugin creates branches per task. Standardize the name:

```
Format:  sdlc/<task_id>-<slug>

Slug: first 40 chars of description, lowercased, hyphenated
Example:
  description: "Build a REST API endpoint that returns paginated user list"
  slug:       build-a-rest-api-endpoint-that-returns-p
  task_id:    abc123
  branch:     sdlc/abc123-build-a-rest-api-endpoint-that-returns-p

Commit message format:
  sdlc(<task_id>): <phase> — <brief summary>
  Example: "sdlc(abc123): Coding — implement paginated user list endpoint"
```

### Plugin Startup Validation

On `session.created`, the plugin should verify its dependencies:

```typescript
"event": async ({ event }) => {
  if (event.type === "session.created") {
    // Check background agents plugin is installed
    try {
      const { background } = await import("kdco/background-agents")
      hasBackgroundAgents = true
    } catch {
      console.warn("[SDLC Enforcer] kdco/background-agents not found. Debate will not work.")
      hasBackgroundAgents = false
    }
    // Restore state from disk
    const state = await readStateFromDisk(sessionId)
    if (state) sessions.set(sessionId, state)
  }
}
```

### Testing Strategy Per Layer

| Layer | Testing Approach | Framework |
|---|---|---|---|
| Plugin (`sdlc-enforcer.ts`) | Unit: mock opencode session + tool calls. Verify single event handler dispatches correctly (session.created, session.deleted, session.idle). Verify no formatting/tracing/decision logic in plugin. | Vitest + opencode headless |
| StoreBackend (`runtime/store_*.py`) | Unit: test SQLite backend CRUD. Integration: swap to in-memory StoreBackend, verify orchestrator works identically. | pytest + pytest-asyncio |
| Phase Graph + Templates | Parametrized: each valid transition per template, each invalid transition, dead-end detection, template load from YAML. | pytest |
| Schema Checks (`engine/schema_checks.py`) | Parametrized: per-transition required sections (present/missing), artifact existence checks. Edge cases: empty output, null values. | pytest |
| Judge Engine | Parametrized: one test per transition type. Verify 3-stage gate: phase match → schema_checks → LLM judge. LLM judge mocked in unit tests. | pytest |
| Consensus Engine | Controlled input: 3 agents with known positions. Verify minority reports extracted. Verify sycophantic collapse flag. Verify stalemate at threshold. | pytest |
| Deterministic Validation | Adapter-level: known-good and known-bad files. Integration: validation runner with all 3 adapters. | pytest |
| Cross-Task Memory (Phase 7) | Store memory, retrieve with project-scoped query, verify confidence decay filters old entries. | pytest |
| Agent Config | Integration: opencode in temp project, verify skill loads, subagents spawn, permissions work. | Manual + shell script |
| End-to-End | Full SDLC run from Chatting to Done in sandboxed temp project. Measure: completion time, token usage, iteration count, trace completeness. | Shell script + pytest |

### Config Validation on Init

`python -m sdlc init` should validate everything before the server runs:

```bash
python -m sdlc init

# Validates:
# 1. All graph templates in graphs/ — no dead ends (except Done), all phases reachable from start
# 2. model_routing.yaml — every phase across all templates has an entry
# 3. judge prompt files — every transition across all templates has a matching prompt file
# 4. All prompt files exist and are non-empty
# 5. Ollama is reachable (optional: try to pull missing models)
# 6. StoreBackend path is writable (sqlite or pg)
# 7. Plugin state path is writable
# 8. Plugin is enforcement-only (scans sdlc-enforcer.ts for forbidden patterns: formatting, tracing, decisions)
# 9. Graph templates are loadable and parseable YAML

# Output:
# ✓ graphs/feature.yaml — valid (7 phases, 6 transitions)
# ✓ graphs/bugfix.yaml — valid (5 phases, 4 transitions)
# ✓ graphs/refactor.yaml — valid (5 phases, 4 transitions)
# ✓ graphs/docs.yaml — valid (4 phases, 3 transitions)
# ✓ graphs/research.yaml — valid (3 phases, 2 transitions)
# ✓ model_routing.yaml — covers all 6 phases across all templates
# ✓ judge prompts — all 6 transition types have prompt files
# ✓ Plugin enforcement-only — no violations
# ✓ Ollama reachable — but models [qwen2.5-coder:7b, deepseek-r1:1.5b] not pulled
#   Run: ollama pull qwen2.5-coder:7b && ollama pull deepseek-r1:1.5b
# ✓ data/ — writable
```

### Prompt Versioning

When prompt files change mid-task, the task should use the version locked at creation:

```
Task creation:
  prompt_version = current git hash of the prompts/ directory
  stored in task record

sdlc_get_next_action:
  If task.prompt_version exists, serve the prompt text from that version
  Implementation: store prompts inline in the task record at creation time
    (copy prompt text, don't reference file — so file changes don't affect running tasks)

If prompts are not git-tracked (no .git), use file modification timestamp as version.
```

---

## Nice-to-Have Additions (Post-Launch)

### Progress Endpoint

`sdlc_get_status` returns estimated progress based on phase position:

```
Calculation:
  phase_order = [Specs, Planning, Coding, Review, Testing, Done]
  progress = ((phase_index + 1) / total_phases) * 100

  History consideration:
    If task went through 2 Review cycles, progress stays at ~66%
    (it's in Review for the 2nd time, not making "forward progress")

  Better calculation: track unique phases completed / total unique phases
```

### Structured Logging

Both MCP server and plugin write structured JSON logs:

```
MCP server → data/sdlc.log:
{"timestamp":"2026-05-17T12:34:56Z","level":"info","event":"task_created","task_id":"abc123","phase":"Specs"}
{"timestamp":"2026-05-17T12:35:10Z","level":"info","event":"phase_submitted","task_id":"abc123","phase":"Specs","next_phase":"Planning","duration_ms":14000}
{"timestamp":"2026-05-17T12:35:11Z","level":"warn","event":"model_fallback","task_id":"abc123","phase":"Planning","primary":"qwen3:4b","fallback":"qwen3:1.7b"}

Plugin → data/plugin.log:
{"timestamp":"2026-05-17T12:34:50Z","level":"info","event":"session_created","session_id":"sess_1"}
{"timestamp":"2026-05-17T12:35:12Z","level":"info","event":"phase_gate_blocked","session_id":"sess_1","tool":"edit","phase":"Specs"}
{"timestamp":"2026-05-17T12:35:20Z","level":"info","event":"compaction","session_id":"sess_1","injected_phase":"Planning"}
```

### Cost Tracking

Track token usage per phase per model:

```
Record in task history:
{
  "phase": "Coding",
  "model": "qwen2.5-coder:3b",
  "prompt_tokens": 4500,
  "completion_tokens": 1200,
  "total_tokens": 5700,
  "duration_ms": 45000
}

sdlc_get_status returns:
{
  "token_usage": {
    "total_tokens": 28400,
    "by_phase": {
      "Specs":    { "model": "qwen3:4b",           "tokens": 4200 },
      "Planning": { "model": "qwen3:4b",           "tokens": 8500 },
      "Coding":   { "model": "qwen2.5-coder:3b",   "tokens": 5700 },
      "Review":   { "model": "qwen2.5-coder:7b",   "tokens": 10000 }
    }
  }
}
```

Note: opencode doesn't expose token counts directly. This requires the MCP server to estimate or the subagent prompts to instruct the model to report usage.

### Prompt Lint on Init

Extend `python -m sdlc init` with:

```
--lint flag:
  - Reads each prompt file
  - Checks for:
    - Placeholder variables used but not defined in context
    - Missing instruction sections (must_have, must_not_do, output_format)
    - Run-on paragraphs (>500 chars without newline)
  - Outputs warnings:
    ⚠ prompts/code.txt: references {user_auth_model} but this isn't in the context
    ⚠ prompts/review.txt: paragraph at line 23 is 612 chars (prefer <400)
```

### Multi-Project Isolation

`SDLC_DB_PATH` defaults to `./data/sdlc.db`, creating one DB per project directory:

```
Behavior:
  ./project-a/data/sdlc.db  ← separate DB
  ./project-b/data/sdlc.db  ← separate DB

If user wants a shared global DB:
  export SDLC_DB_PATH=~/.config/opencode/sdlc.db

Plugin state is always session-scoped, not project-scoped.
```

Make the scoping explicit in the README and config comments.

---

## What's Already Handled Well

| Feature | Layer | Where |
|---|---|---|
| ToolAdapter interface | adapters | `adapters/base.py` — ABC with validate/execute/healthcheck |
| Plugin enforcement-only | Plugin | `.opencode/plugins/sdlc-enforcer.ts` — single event handler, hard gates only, no formatting/tracing/decisions |
| Phase graph enforcement | Plugin | `tool.execute.before` hard-blocks edits + `submit_output` rejects phase mismatch |
| Single event handler (no duplicates) | Plugin | Switch on `session.created/deleted/idle` in one function — no duplicate `event:` definitions |
| Anchored structured compaction | Plugin | Factory.ai-style anchor injected via `experimental.session.compacting` — state, next steps, merge-only |
| Stop workaround (no native hook) | Plugin | `event` + `session.idle` + `client.session.prompt()` — PR #16598 tracked for future native support |
| Graph templates (per task type) | engine | `graphs/feature.yaml`, `bugfix.yaml`, `refactor.yaml`, `research.yaml`, `docs.yaml` — selected at task creation |
| StoreBackend abstraction | runtime | `runtime/store_backend.py` ABC — SQLite now, Postgres later, orchestrator never imports aiosqlite |
| Orchestrator FSM | engine | `engine/orchestrator.py` — wires phases, transitions, adapters |
| Checkpoint system | engine | `engine/checkpoint.py` — snapshot/restore for crash recovery |
| Deterministic preconditions (before LLM judge) | engine | `engine/schema_checks.py` — required sections + artifact checks per transition type; LLM never runs before passing |
| 3-stage judge gate | engine | Phase match → schema_checks → LLM judge. Each stage can reject independently |
| 3-round deliberation protocol | engine | Round 1 (parallel) → Round 2 (cross-exposure) → Round 3 (residual objections) |
| ConsensusEngine with minority reports | engine | Diversity-preserving weighting, sycophantic collapse guard, stalemate detection |
| Structured debate provenance | engine | SAMEP-inspired claims with confidence, evidence_refs, and agent attribution |
| Parallel debate | agents | Background agents via `kdco/background-agents` or `Erinable/opencode-group-discuss`, 3 agents, hidden:true |
| Hidden agent design | agents | All subagents and debate agents set `hidden: true` |
| Build order (enforcement first) | meta | Phase 1 proves deterministic enforcement before any other feature |
| Rejection handling on submit | runtime | Clear `error` + `hint` for phase mismatch, missing sections, precondition failures |
| MCP Resources | runtime | `sdlc://task/{id}/spec` etc loaded on-demand, not up front |
| Approval gate (OAC) | runtime + Plugin | `sdlc_request_approval` + plugin blocks edits until approved |
| Per-phase permission model | agents | `opencode.json` restricts each subagent to only what its phase needs |
| Model routing with subagents | agents | Different models per phase via agent config |
| Integration governance | meta | "What architectural weakness does this solve?" before any integration |
| Deterministic validation | validators | `validators/deterministic/runner.py` aggregates lint/typing/test results |
| Layered directory structure | system | `engine/`, `adapters/`, `runtime/`, `validators/`, `agents/` — no concern mixing |
| Observability tracing | runtime | `trace_id` + `parent_span_id` + `span_id` on every tool call and MCP request; JSONL traces in `data/traces/` |
| Cross-task memory with decay (Phase 7) | adapters | Engram/Acervo as optional MCP servers; deferred to Phase 7 — contamination risk before stable core |
| Graphify context reduction | adapters | 71.5x token reduction (670k → 2k tokens per query); 3-pass AST+whisper+LLM pipeline |
| Bubblewrap sandboxing | adapters | `adapters/execution/sandbox.py` — default-deny isolation via Linux namespace sandbox |
| CI/CD integration | adapters | Optional PR auto-creation via `adapters/vcs/github.py` after Done phase |
| Research-informed debate design | engine | ControlMAD, DCI, and Counsel findings shape debate agent prompts (validity-aligned reasoning, structured memory) |
| Memory confidence decay | adapters | `effective_confidence = confidence * (1 - (days / 30))` — project-scoped, filtered below 0.15 |
| Plugin state per session | Plugin | One file per session in `data/plugin_state/` — atomic write via rename(), no single-JSON-blob corruption |
| DebateRuntime | engine | `engine/debate_runtime.py` — scheduling, timeouts, retries, cancellation, partial completion, stale cleanup |
| ExecutionSnapshot | engine | Full reproducibility lock at task creation: graph_hash, prompt_hashes, model_routing_hash, adapter_versions |
| FailureType taxonomy | engine | `RETRYABLE_MODEL`, `TERMINAL_VALIDATION`, `ORCHESTRATION_CANCELLED`, etc — orchestrator uses category for retry/abort |
| Budget policy | config | `config/budget_policy.yaml` — per-graph-template `max_total_tokens`, `max_review_cycles`, `max_runtime_minutes` |
| Trace retention policy | runtime | Errors forever, successful 7d, spans 30d, summaries permanently — daily background enforcement |
| Bubblewrap network risk | adapters | localhost-only not inherently safe — documented future migration to dedicated netns + Unix socket proxy |
| ExecutionPolicy | engine | `engine/execution_policy.py` — budget checks, failure classification, retry decisions (FSM never sees policy logic) |
| WriteQueue | runtime | `runtime/write_queue.py` — single-worker serialized persistence writer, prevents SQLite write contention |
| Filesystem policy tiers | adapters | `readonly_paths`, `writable_paths`, `denied_paths` per sandbox config — prevents agent from deleting repo internals |
| Artifact lineage | engine | `reason`, `source_phase`, `source_span`, `depends_on` per file modification — rollback, blame tracing, memory extraction |

## Research Appendix

### Key Sources

| Area | Source | Key Finding |
|---|---|---|
| opencode plugin API | GitHub issues #12472, PR #16598 | No native stop hook; workaround via event + session.idle |
| MCP SDK | FastMCP docs, MCP spec v1.0 | `from mcp.server.fastmcp import FastMCP` with composed lifespans |
| SQLite for agents | aiosqlite docs, opencode v1.2.2 migration | WAL mode + manual checkpoints required; one DB per agent defeats lock contention |
| Graphify | GitHub (48k+ stars, MIT) | 71.5x token reduction; native opencode installer (`graphify opencode install`) |
| Bubblewrap | Flatpak docs, Grapwulf/sandbox-run | `--unshare-all` for default-deny; `--ro-bind`/`--bind` for selective grant |
| Multi-agent debate | ControlMAD (OpenReview 2026) | Intrinsic reasoning + group diversity dominate; majority pressure suppresses correction |
| Multi-agent debate | DCI (Deliberation) | Typed epistemic acts, minority reports, residual objections — beats vanilla debate by 18% |
| Multi-agent debate | Counsel's DACI/Catfish | Sycophantic collapse 20% base rate; dynamic devil's advocate outperforms static by 23% |
| Ollama structured output | Ollama API docs | `format` (JSON grammar) and `tools` are mutually exclusive |
| Leiden clustering | leidenalg docs | NetworkX + leidenalg for community detection; resolution parameter for granularity control |
| Tree-sitter | tree-sitter docs | 305+ languages, zero-copy parsing, syntax-aware chunking |
| Cross-task memory (Phase 7) | Engram MCP, Acervo | Episodic + semantic memory MCP servers; deferred to Phase 7 — stable core first |
| Bubblewrap + agents | umago/bubblewrap-ai | Reference implementation for agent sandboxing with namespace isolation |

### Multi-Agent Debate Research Details

**ControlMAD** (OpenReview 2026):
- Intrinsic reasoning strength is the dominant predictor of debate success
- Group diversity is the second most important factor
- Majority pressure suppresses independent correction (agents conform)
- Validity-aligned reasoning most strongly predicts improvement
- Implication: debate agents should be diverse (different models/temps) and encouraged to maintain independent positions

**DCI (Deliberation via Typed Epistemic Acts)**:
- Phased progression: propose → critique → refine → resolve
- Minority reports: dissenting positions preserved in output
- Residual objections: unresolved disagreements surfaced to judge
- Beats standard debate by 18% on policy/architecture tasks
- Implication: design ConsensusEngine to accept minority reports + residual objections, don't force unanimity

**Counsel's DACI Protocol and Catfish**:
- Sycophantic collapse is the #1 problem (20% base rate)
- Static devil's advocate (always criticize) makes it worse — agents learn to ignore it
- Dynamic injection (Catfish protocol): randomly inject a contrarian agent that changes position mid-debate
- Catfish outperforms static devil's advocate by 23%
- Implication: debate prompts should include "maintain independent position even if others agree"
- For ConsensusEngine: weight by confidence, not majority
