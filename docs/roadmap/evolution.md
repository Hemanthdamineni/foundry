# Roadmap, Research & Future Architecture

> Phased implementation roadmap, deferred systems, expansion points, research ideas, and long-term evolution strategy.

---

## Implementation Phases

### Phase 1: End-to-End Build Loop (CURRENT PRIORITY)

**Goal:** `foundry build "description"` autonomously delivers working, validated code.

**What "works" means:**
1. User provides natural language requirements
2. Foundry generates a specification (Specs)
3. Foundry decomposes into a dependency-ordered plan (Planning)
4. Foundry implements each task via subagent prompts (Coding)
5. Tool gates validate: lint → types → tests (Testing)
6. Structured debate reviews the output (Review)
7. Output: working implementation + completion report (Done)
8. Everything is checkpoint-recoverable and budget-bounded

**Remaining integration work:**

| Work Item | Module | What's Missing |
|---|---|---|
| Wire `ExecutionRuntime` into submit flow | `execution_runtime.py` | Prompt locks and deterministic IDs not enforced |
| Wire `ToolGate` into phase transitions | `tool_gate.py` | Gates defined but not called during submit |
| Wire `BudgetController` into main loop | `budget_controller.py` | Controller exists but not integrated with `ExecutionPolicy` |
| Wire `EnhancedCheckpointManager` as primary | `enhanced_checkpoint.py` | Two checkpoint systems; need to unify |
| Foundry installer bundles Python runtime | `install.js` | Installer assumes separate runtime installation |
| End-to-end integration test | New: `tests/integration/` | No test exercises the full SDLC loop |

**Success criteria:** Given a natural language requirement, Foundry produces code that passes lint, types, and tests — autonomously, with no human intervention during execution.

---

### Phase 2: Reliability

**Goal:** The build loop handles failures gracefully without human rescue.

| Work Item | Module |
|---|---|
| Retry escalation on failures | Wire `RetryPolicy` into orchestration loop |
| Replanning when stuck | Wire `Replanner` into orchestrator |
| Rollback to last-green on unrecoverable | Wire `RollbackManager` with git integration |
| State persistence across sessions | Unify `StateManager` with `SqliteStore` |
| GitHub adapter (create PRs, respond to reviews) | New: `adapters/github.py` |
| Review debate integration | Already works; needs polish |

**Success criteria:** Foundry recovers from tool failures, model errors, and test regressions without human intervention. Execution is resumable after crashes.

---

### Phase 3: Reasoning Quality

**Goal:** Improve the quality of generated code through structured reasoning.

| Work Item | Module |
|---|---|
| Confidence gating (reject low-quality outputs) | Wire `ConfidenceGate` after debate |
| Judge hierarchy during review | Wire `JudgeHierarchy` for multi-layer validation |
| Context harvesting for smarter prompts | Wire `ContextHarvester` with `IndexPipeline` |
| Error memory (learn from past failures) | Wire `MemoryStore.find_similar_error()` |
| Drift detection (catch specification drift) | Wire `DriftDetector` between phases |

**Success criteria:** Code quality improves measurably. Fewer retry cycles. Debates catch real issues.

---

### Phase 4: Scalability

**Goal:** Handle larger projects, multiple repos, and longer autonomous runs.

| Work Item | Module |
|---|---|
| Tool gateway with MCP routing/fallback | New: `runtime/tool_gateway.py` |
| Observability dashboard | Wire `dashboard.py` + `tracing.py` |
| Prompt registry (versioned, replay-safe) | Wire `prompt_registry.py` |
| Multi-project support | Architecture work |
| Docker-sandboxed execution | MCP integration |

---

## Deferred Systems

These are deliberately excluded from the implementation roadmap. They represent expansion points, not requirements.

### Deferred Indefinitely

| System | Reason to Defer |
|---|---|
| **Distributed execution** | No multi-node scenario exists; single-process is sufficient |
| **Chaos/simulation testing** | System must work correctly first |
| **Compliance/governance frameworks** | No enterprise customers; no regulatory requirements |
| **Learning/adaptation engines** | Premature optimization; memory store covers core needs |
| **30+ memory/validator/security types** | Methods on existing modules suffice |
| **Enterprise integrations** (Jira, Slack, Linear) | Only if users explicitly request |
| **Multi-model orchestration** (per-token routing) | Model router handles model selection adequately |
| **Custom language servers** | Workspace indexing covers symbol extraction |

### The Kill List

These concepts from the brainstorming drafts were explicitly rejected:

| Concept | Why Rejected |
|---|---|
| 500+ independent skills | These are methods on existing modules, not standalone systems |
| Micro-agent decomposition (30+ agents) | Single agent with behavioral modes is simpler and sufficient |
| Regulatory compliance engine | No customers, no regulations |
| Economic resource governance | Budget controller covers resource limits |
| Chaos engineering framework | Can't chaos-test what doesn't reliably work yet |
| Real-time collaboration system | Single-user runtime; no collaboration scenario |
| Meta-cognitive reasoning layer | Unnecessary abstraction; debate + confidence covers quality |
| Self-modifying prompt evolution | Prompt hash locking explicitly prevents this (determinism) |
| Enterprise SaaS deployment | Local-first; cloud deployment is a separate product |

---

## Expansion Points

These are well-defined extension interfaces where future functionality can plug in without architectural changes:

### New Phase Graph Templates

Add new workflow types by creating YAML phase graph files:

```yaml
# graphs/bugfix.yaml — shorter workflow
phases: [Chatting, Debugging, Coding, Testing, Done]
transitions:
  - { from: Chatting, to: Debugging }
  - { from: Debugging, to: Coding }
  - { from: Coding, to: Testing }
  - { from: Testing, to: Done }
  - { from: Testing, to: Coding }
```

Currently planned templates: `feature`, `bugfix`, `refactor`, `research`, `docs`.

### New LLM Providers

Add providers by implementing `LLMProvider`:

```python
class AnthropicProvider(LLMProvider):
    async def generate(self, messages, model, temperature, max_tokens, response_format) -> str:
        # Use Anthropic API
```

Then register in `llm_config.yaml`.

### New Store Backends

Replace SQLite by implementing `StoreBackend`:

```python
class PostgresStore(StoreBackend):
    async def initialize(self) -> None: ...
    async def create_task(self, payload: dict) -> None: ...
    async def get_task(self, task_id: str) -> dict | None: ...
    # ... etc
```

### New Validation Gates

Add custom gates to the tool gate sequence:

```python
tool_gate.set_gate_order([
    ("lint", "ruff"),
    ("types", "mypy"),
    ("tests", "pytest"),
    ("coverage", "coverage"),
    ("security", "semgrep"),
    ("docs", "pydocstyle"),      # NEW: documentation linting
    ("complexity", "radon"),      # NEW: complexity checking
    ("benchmarks", "benchmarks"),
])
```

### New Debate Agent Roles

Add domain-specific reviewers:

```python
class DebateAgentRole(StrEnum):
    SPECS = "specs"
    PLANNING = "planning"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    CONSENSUS = "consensus"
    SECURITY = "security"      # NEW
    PERFORMANCE = "performance" # NEW
    ACCESSIBILITY = "a11y"     # NEW
```

---

## Research Ideas

These are speculative concepts worth investigating but not committed to:

### 1. Execution Replay

**Concept:** Record every deterministic decision point and replay executions offline for debugging.

**Implementation path:**
- `ExecutionRuntime` already records transitions
- `EnhancedCheckpointManager` already supports replay sequences
- Missing: replay orchestrator that feeds recorded inputs back through the FSM

**Risk:** LLM non-determinism means replay produces different outputs even with same inputs. Useful for debugging orchestration logic, not LLM quality.

### 2. Cross-Task Learning

**Concept:** Use error memory from past tasks to improve future executions.

**Implementation path:**
- `MemoryStore.find_similar_error()` already searches for similar past errors
- Missing: feeding resolved errors into prompt context for future tasks
- Missing: tracking which resolutions actually worked

**Risk:** Memory pollution — storing too many irrelevant errors degrades retrieval quality.

### 3. Confidence Calibration

**Concept:** Track whether confident approvals actually produce good outcomes and adjust thresholds.

**Implementation path:**
- `ConfidenceGate` already detects drift
- Missing: correlating confidence scores with downstream test results
- Missing: auto-adjusting thresholds based on historical accuracy

**Risk:** Auto-adjustment could create feedback loops (lower thresholds → more approvals → more failures → lower thresholds...).

### 4. Adaptive Retry Budgets

**Concept:** Adjust retry limits based on historical retry effectiveness per phase.

**Implementation path:**
- `RetryPolicy.effectiveness_score()` already computes per-phase success ratios
- Missing: using effectiveness scores to dynamically adjust `max_local_retries`
- Missing: decay mechanism for stale data

**Risk:** If a phase historically had easy retries, reducing budget could cause failures when a genuinely hard problem appears.

### 5. Workspace Sandbox Execution

**Concept:** Run untrusted generated code in Docker containers with filesystem isolation.

**Implementation path:**
- `SandboxConfig` already defines path restrictions
- Docker MCP can execute in containers
- Missing: automatic container creation/teardown per phase
- Missing: filesystem bridge between sandbox and host

**Risk:** Complexity explosion. Docker adds network, storage, and process management concerns.

---

## Long-Term Evolution Strategy

### Year 1: Make It Work

- End-to-end build loop (Phase 1)
- Crash recovery (Phase 2)
- Quality improvement (Phase 3)
- **Validation criterion:** Foundry can autonomously build a simple web application from requirements

### Year 2: Make It Reliable

- Tool gateway with MCP routing
- Multi-repository support
- Docker sandboxing
- GitHub PR workflow automation
- **Validation criterion:** Foundry can autonomously maintain a production codebase (bug fixes, feature additions, test updates)

### Year 3: Make It Fast

- Parallel phase execution for independent tasks
- Multi-model orchestration (cheap models for draft, expensive for review)
- Index-based context injection (only relevant code in prompts)
- Prompt optimization based on historical effectiveness
- **Validation criterion:** Foundry completes a standard feature task in under 10 minutes

### Architectural Invariants That Must Survive

No matter how the system evolves, these must remain true:

1. **Users see workflows, not internals** — Never expose orchestration complexity
2. **Validation-first** — Tool gates are law; no phase advances without verification
3. **Checkpoint-recoverable** — Every phase transition must be restorable
4. **Budget-bounded** — Hard ceilings prevent runaway execution
5. **Disk is truth** — Persistent state is canonical; in-memory derives from it
6. **Single orchestrator** — One agent, behavioral modes, not agent swarms

---

## Deployment Concepts

### Current: Local Development

```
Host Agent (OpenCode)
    │
    └── MCP stdio connection
           │
           └── sdlc MCP server (Python, local process)
                  │
                  └── Ollama (local LLM inference)
```

### Planned: Installed Runtime

```
User: npx --yes github:Hemanthdamineni/foundry
    │
    ├── npm postinstall:
    │   ├── Link skills to ~/.config/opencode/skills/foundry/
    │   ├── Link agents to ~/.config/opencode/agents/
    │   ├── Install Python runtime (pip or pixi)
    │   └── Register MCP server in opencode config
    │
    └── Ready to use: "foundry build ..."
```

### Future: Containerized

```
Docker container
    ├── Python runtime + dependencies
    ├── Ollama (sidecar or external)
    ├── Workspace volume mount
    └── MCP stdio exposed to host agent
```

### Future: Remote

```
Cloud instance
    ├── SDLC runtime
    ├── GPU-backed LLM inference
    ├── Object storage for checkpoints
    ├── PostgreSQL for state
    └── WebSocket MCP transport
```

These deployment modes don't require architectural changes — they only change:
1. How the MCP server is started (stdio vs WebSocket vs HTTP)
2. Where state files live (local disk vs object storage)
3. Where LLM inference runs (local Ollama vs remote API)
