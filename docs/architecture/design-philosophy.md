# Design Philosophy

> The principles, constraints, and intentional tradeoffs that shape every architectural decision in Foundry.

---

## Core Thesis

Foundry exists because current AI coding agents are **brittle, unrecoverable, and unauditable**. They operate as open-ended chat loops with no structural guarantees about output quality, resource consumption, or crash recovery. Foundry replaces that model with a **deterministic, recoverable, budget-bounded execution runtime** that treats software engineering as a finite state machine, not a freeform conversation.

The design is opinionated. Many popular approaches in the agent ecosystem were evaluated and intentionally rejected. This document explains why.

---

## The Ten Invariants

These are non-negotiable. Every subsystem, every module, every line of code must respect these:

### I1: Disk Is Truth

Persistent state files are canonical. In-memory state is derived from disk state on startup. If in-memory and disk disagree, **disk wins**.

**Why:** Agent runtimes crash. Power fails. Processes get killed. If state lives only in memory, a crash erases all progress. By writing state to disk atomically at every phase transition, Foundry can resume from exactly where it left off.

**Implementation:** `StateManager` uses `tmp+rename` for atomic writes. `SqliteStore` uses `BEGIN IMMEDIATE` transactions with WAL mode. `EnhancedCheckpointManager` creates versioned checkpoint chains.

### I2: Validation-First

Tool gates are authoritative. Schema checks are deterministic preconditions. "Looks correct to the LLM" is never sufficient when tools can verify.

**Why:** LLMs hallucinate. They claim tests pass when they don't. They say code compiles when it has syntax errors. Deterministic validation (lint, type check, test runner) provides ground truth that no amount of reasoning can replace.

**Implementation:** `SchemaChecks` run before `JudgeEngine`. `ToolGate` enforces ordered validation sequences with fail-fast semantics. Schema violations produce terminal failures — no retry, because the output is structurally wrong.

### I3: Budget Ceilings Are Absolute

When a budget ceiling is hit, the task is aborted. No override, no exception, no negotiation.

**Why:** Without hard limits, an agent can loop forever — retrying the same failing approach, consuming tokens, and accomplishing nothing. Budget ceilings are the fundamental safety mechanism that prevents runaway execution.

**Implementation:** `BudgetController.should_continue()` is checked before every phase transition. Violations at the `critical` level trigger immediate task abort.

### I4: Phase Transitions Are Validated

The FSM rejects invalid transitions. No phase can be reached without passing through the graph.

**Why:** Without transition validation, an agent could skip phases (jump from Specs to Done), regress phases (go from Review back to Chatting), or enter non-existent phases. The phase graph is the structural skeleton that makes execution predictable.

**Implementation:** `PhaseGraph` validates at construction (all transitions valid, all phases reachable, Done has no outgoing edges). `OrchestratorFSM.submit()` rejects transitions not in the graph.

### I5: Rollback Never Corrupts Stable Phases

Completed, stable-marked phases are sacred. Rollback preserves them unconditionally.

**Why:** If a Coding phase produced correct, tested code, and a later Review phase fails, rolling back should not destroy the working code. Stable work represents irreversible progress that must be preserved.

**Implementation:** `RollbackManager.plan_rollback()` computes `protected_files` from stable phases. If `files_to_revert ∩ protected_files ≠ ∅`, the rollback is refused.

### I6: Checkpoint-Recoverable

Every phase transition produces a checkpoint. Crashes are recoverable from the last checkpoint.

**Why:** Long-running tasks (30-60 minutes) that crash at minute 55 must not lose 55 minutes of work. Checkpoints enable resume-from-last-known-good-state without re-executing completed phases.

**Implementation:** `WriteQueue` triggers checkpoint creation on every accepted submission. `EnhancedCheckpointManager` maintains versioned chains with restore points.

### I7: Single Orchestrator

One agent (Foundry), internal behavioral modes via prompts. Not a multi-agent swarm.

**Why:** Multi-agent architectures introduce coordination complexity (message passing, consensus protocols, resource contention, deadlocks) that is unnecessary when a single orchestrator can manage behavioral variation through prompt strategies. Debate exists for quality review, not for execution — debate agents evaluate, they don't execute.

**Implementation:** All execution flows through `tools/phase.py` and `tools/task.py`. The `engine/` layer provides behavioral policies (retry, replan, debate) that the single orchestrator applies.

### I8: Prompts Are Locked Per Task

Prompt content hashes are frozen at task creation. The same task always uses the same prompts.

**Why:** If prompts change mid-execution, the same task produces different results when replayed. Prompt locking ensures that debugging, replay, and regression testing are meaningful.

**Implementation:** `Task.locked_prompts` is populated from `settings.load_all_judge_prompts()` at creation time. `JudgeEngine` uses locked prompts when available. `ExecutionSnapshot` records content hashes for verification.

### I9: State Writes Are Atomic

No state file write can produce a partially-written file.

**Why:** A half-written JSON file is worse than no file at all — it corrupts state and breaks deserialization. Atomic writes ensure that every file is either fully old or fully new, never partially updated.

**Implementation:** All state persistence uses `Path.write_text()` to a `.tmp` file, then `Path.rename()` to the target. On POSIX systems, `rename()` within the same filesystem is atomic.

### I10: Authority Is Centralized

No component may advance phases, retry, replan, or rollback without orchestrator approval.

**Why:** If subsystems can independently advance state, the system becomes unpredictable. Centralized authority provides a single audit point, consistent policy enforcement, and deterministic decision logging.

**Implementation:** `OrchestratorAuthority.request_authority()` is the single decision point. Every authority decision is logged with type, requester, reason, and outcome.

---

## Rejected Alternatives

### Why Not Multi-Agent Swarms?

The agent ecosystem heavily promotes multi-agent architectures: researcher agents, coder agents, reviewer agents, tester agents — all running independently and communicating via message passing.

**What we evaluated:**
- CrewAI-style role-based agent teams
- AutoGPT-style recursive self-improvement loops
- Specialized microagent pools with routing

**What we found:**
- Coordination overhead exceeded the cost of sequential execution
- Message passing between agents introduced latency and state synchronization bugs
- No agent architecture could reliably recover from another agent's crash
- Debugging multi-agent interactions was exponentially harder than debugging a single orchestrator

**What we chose instead:** A single orchestrator with behavioral modes. The "agents" in Foundry's debate system are LLM calls with role-specific prompts, not independent processes. They evaluate; they don't execute.

### Why Not Embeddings for Context Retrieval?

Many agent frameworks use embedding-based semantic search for code context retrieval.

**What we evaluated:**
- Sentence-transformer embeddings for code chunks
- FAISS/ChromaDB vector stores for similarity search
- Hybrid keyword + embedding retrieval

**What we found:**
- Embedding quality for code is unreliable (variable names carry more semantic weight than logic)
- Vector store maintenance adds infrastructure complexity
- Keyword + structural matching (imports, dependents) is more predictable for code
- Embedding models require GPU or are slow on CPU

**What we chose instead:** Deterministic structural context retrieval via `DependencyGraphEngine`. Context is assembled from import edges, dependent files, and keyword matching against file paths and symbol names. No embeddings, no vector stores, no GPU dependency.

### Why Not LangChain / LangGraph?

**What we evaluated:**
- LangChain's chain abstraction for sequential processing
- LangGraph's graph-based agent execution

**What we found:**
- LangChain adds significant abstraction overhead for what is fundamentally "build a prompt, call an LLM, parse the result"
- LangGraph's graph model conflicts with our FSM model (we need validated transitions, not arbitrary graph traversal)
- Both frameworks assume cloud-first deployment; Foundry is local-first
- Neither provides checkpoint recovery, budget enforcement, or atomic state writes

**What we chose instead:** Direct `httpx` calls to Ollama/OpenAI via a thin `LLMProvider` abstraction. Total LLM integration code: ~230 lines across `base.py`, `providers.py`, and `routing.py`. No framework dependencies.

### Why Not Streaming Output?

**What we evaluated:**
- SSE-based streaming for real-time output display
- Chunked output validation (validate as tokens arrive)

**What we found:**
- Schema checks require complete output (can't validate `## Requirements` section until all sections exist)
- Judge evaluation requires full output for holistic quality assessment
- Checkpoint semantics are phase-level, not token-level
- Streaming adds complexity to the write queue and state management

**What we chose instead:** Full output collection, then validation. The host agent handles streaming to the user if needed; Foundry operates on complete outputs.

### Why Not Postgres / Redis / Cloud Storage?

**What we evaluated:**
- PostgreSQL for structured task/phase storage
- Redis for in-memory state caching
- S3/GCS for checkpoint storage

**What we found:**
- Foundry is a local development tool, not a cloud service
- SQLite provides ACID transactions, WAL mode for concurrent reads, and zero infrastructure
- JSON files provide human-readable state that can be inspected with `cat` and `jq`
- External database dependencies increase setup friction for contributors

**What we chose instead:** SQLite + JSON files. SQLite for structured queries (task listing, history retrieval). JSON for human-readable state (checkpoints, traces, configs). Both are zero-dependency on Linux/macOS.

---

## Architectural Constraints

### Local-First

Foundry assumes local execution. The primary deployment model is a developer's workstation, not a cloud cluster. This constrains:

- **Storage:** Must work with local filesystems (no S3, no distributed storage)
- **Compute:** Must run on consumer hardware (no GPU requirements for core functionality)
- **Network:** Ollama is localhost; only OpenAI calls go over the network
- **Concurrency:** Single-user, not multi-tenant

### MCP Protocol

Foundry exposes its functionality as an MCP server. The host agent (OpenCode) calls MCP tools. This constrains:

- **Interface:** All user-facing operations must be expressible as MCP tool calls
- **State:** The MCP protocol is stateless between calls; all state must be persisted
- **Response format:** Tool responses are structured dictionaries, not freeform text
- **Discovery:** Tools are self-describing via MCP metadata

### Python Runtime

The SDLC engine is Python. This constrains:

- **Concurrency model:** `asyncio` for I/O-bound operations, no true parallelism for CPU-bound work
- **Type safety:** Runtime type validation via Pydantic, not compile-time guarantees
- **Performance:** Acceptable for orchestration (the bottleneck is LLM inference, not Python execution)
- **Deployment:** Requires Python 3.11+ and pip/pixi for package management

---

## Design Tensions

### Determinism vs. Quality

**Tension:** LLMs are inherently non-deterministic. Even with `temperature=0.0`, the same prompt can produce slightly different outputs across runs. But Foundry needs deterministic behavior for replay and regression testing.

**Resolution:** Determinism is enforced at the orchestration level (schema checks, budget enforcement, phase transitions), not at the LLM output level. The system is deterministic in its reaction to outputs, even if the outputs themselves vary.

### Simplicity vs. Robustness

**Tension:** Simple systems are easier to understand and debug. Robust systems handle more edge cases. Every additional recovery mechanism, validation gate, or retry strategy adds complexity.

**Resolution:** Complexity is concentrated in the `engine/` layer. The `runtime/` layer and MCP tool surface remain simple. Users see 14 tools; the engine provides 20+ subsystems behind those tools.

### Safety vs. Speed

**Tension:** Every validation gate, every judge evaluation, every debate round adds latency. A task that could complete in 5 minutes takes 15 with full validation.

**Resolution:** Validation is mandatory but configurable in depth. Schema checks are always on (fast, deterministic). LLM judge is always on (moderate cost). Debate is configurable per-phase. Multi-judge hierarchy is optional. The user can tune the validation depth to match their risk tolerance.

### Autonomy vs. Control

**Tension:** Fully autonomous execution is the goal, but users need the ability to inspect, pause, and override decisions.

**Resolution:** The `requires_approval` flag enables approval gates at phase transitions. Tracing provides full auditability. Authority governance provides a complete decision log. The system is autonomous by default with opt-in human oversight.

---

## What Foundry Is NOT

| Not This | Why Not | What Instead |
|---|---|---|
| A chatbot | Chatbots have no execution lifecycle | Phase-driven FSM with validation |
| A code generator | Generators produce code without quality control | Validated execution with judge + debate |
| An IDE plugin | Plugins are UI-coupled | Headless MCP server, UI-agnostic |
| A CI/CD system | CI/CD operates post-commit | Foundry operates pre-commit |
| A testing framework | Testing frameworks run tests | Foundry orchestrates test execution as one validation gate |
| A project management tool | PM tools track tasks for humans | Foundry tracks phases for autonomous execution |
