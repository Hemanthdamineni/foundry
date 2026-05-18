# Governance, Safety & Security

> Runtime policies, sandboxing, permission models, auditability, the safety model, and security assumptions.

---

## Governance Architecture

### Centralized Authority Model

All runtime decisions pass through a single governance point: `OrchestratorAuthority`. No component may advance phases, continue debate, retry, replan, or rollback without explicit approval.

```
Component wants to act
    │
    └── AuthorityRequest(type, requester, phase, target, reason)
            │
            ▼
    OrchestratorAuthority.request_authority()
            │
            ├── Check rules for request type
            ├── Check blocked transitions
            ├── Check retry counts
            ├── Check budget exhaustion
            │
            ├── APPROVED → log + return AuthorityDecision(approved=True, conditions=[...])
            └── DENIED   → log + return AuthorityDecision(approved=False, reason="...")
```

### Authority Request Types

| Type | Requester | Decision Logic | Conditions Applied |
|---|---|---|---|
| `phase_transition` | Phase controller | Blocked transitions list | None |
| `debate_continue` | DebateRuntime | Always approved | None |
| `retry` | RetryPolicy | Per-phase retry count vs max | None |
| `replan` | Replanner | Always approved | `preserve_stable_work` |
| `recovery` | RecoveryEngine | Always approved | `restore_from_checkpoint`, `validate_state` |
| `rollback` | RollbackManager | Always approved | `never_corrupt_stable_phases` |
| `budget` | BudgetController | Check exhaustion set | None |

### Explicit Blocking

The authority supports permanent transition blocks:

```python
authority.block_transition("Review", "Specs")   # Never regress from Review to Specs
authority.block_transition("Done", "Coding")     # Done is truly terminal
```

Blocked transitions are permanent for the authority instance lifetime. There is no unblock mechanism — this is intentional to prevent runtime circumvention.

### Decision Audit Log

Every authority decision is recorded in an ordered log:

```python
authority.decision_log
# [
#   {"request_type": "phase_transition", "approved": True, "reason": "Specs → Planning approved", ...},
#   {"request_type": "retry", "approved": True, "reason": "Retry 1/3 approved for Coding", ...},
#   {"request_type": "retry", "approved": False, "reason": "Retry limit (3) exceeded for Coding", ...},
# ]
```

This log provides a complete audit trail of every governance decision made during execution.

---

## Security Model

### Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│ Trust Zone: Local Machine                           │
│                                                     │
│  ┌───────────────┐     ┌──────────────────┐        │
│  │ Host Agent    │────▶│ SDLC MCP Server  │        │
│  │ (OpenCode)    │stdio│ (Foundry Runtime) │        │
│  └───────────────┘     └──────────────────┘        │
│                              │                      │
│                         ┌────▼─────┐                │
│                         │ Ollama   │                │
│                         │ (Local)  │                │
│                         └──────────┘                │
│                                                     │
└─────────────────────────────────────────────────────┘
         │
         │ HTTPS (API keys in env vars)
         ▼
┌─────────────────┐
│ External LLMs   │
│ (OpenAI, etc.)  │
└─────────────────┘
```

### Assumptions

1. **Single-user execution** — Foundry runs as a local MCP server, not multi-tenant
2. **Host agent is trusted** — The agent calling Foundry's MCP tools is assumed legitimate
3. **Local filesystem is trusted** — State files, configs, and checkpoints are not encrypted at rest
4. **Ollama is local** — LLM inference runs on localhost; no network attack surface for local models
5. **API keys in environment** — External provider keys (OpenAI) live in env vars, never in config files or logs

### Threat Model

| Threat | Attack Vector | Mitigation | Status |
|---|---|---|---|
| **Malicious MCP server** | Compromised MCP returns harmful tool results | Whitelist-only MCP registration | **Planned** |
| **Prompt injection** | User description contains malicious instructions | Prompt hash locking prevents runtime prompt mutation | **Implemented** |
| **Runaway execution** | Infinite retry loops, unbounded token consumption | BudgetController with hard ceilings + critical violations | **Implemented** |
| **State corruption** | Crash during file write leaves partial state | Atomic writes via tmp+rename on all state files | **Implemented** |
| **Unsafe rollback** | Rollback corrupts completed work | RollbackManager enforces stable phase protection | **Implemented** |
| **Token exfiltration** | API keys leak into logs or traces | Structured JSON logging; no credential fields | **Implemented** |
| **Unsafe code execution** | Generated code runs destructive commands | Phase restrictions (only Coding/Testing can run commands) | **Implemented** |
| **Dependency confusion** | Malicious packages installed during build | Sandbox path restrictions (when enabled) | **Partial** |
| **Data exfiltration** | Generated code sends data to external services | No network monitoring; relies on sandbox | **Not implemented** |

### Sandbox Configuration

```python
class SandboxConfig(BaseModel):
    enabled: bool = False          # Sandbox is off by default
    allowed_paths: list[str]       # Filesystem paths that tools can access
    denied_paths: list[str]        # Explicitly blocked paths
    max_file_size_mb: int = 100    # Max file size for write operations
```

When enabled, the sandbox restricts:
- Which filesystem paths the runtime can read/write
- Maximum file sizes for generated artifacts
- Which directories are accessible for tool operations

When disabled (default), the runtime has full access to the user's filesystem. This is acceptable for local development but should be enabled for any shared or production use.

---

## Runtime Policies

### Phase Restrictions

Different phases have different permission levels:

| Phase | File Editing | Shell Commands | Git Operations |
|---|---|---|---|
| Chatting | ✗ | ✗ | ✗ |
| ContextHarvesting | ✗ | ✗ | ✗ |
| Specs | ✗ | ✗ | ✗ |
| Planning | ✗ | ✗ | ✗ |
| Coding | ✓ | ✓ (restricted patterns) | ✓ |
| Testing | ✓ | ✓ (restricted patterns) | ✓ |
| Review | ✗ | ✗ | ✗ |
| Done | ✗ | ✗ | ✗ |

### Allowed Shell Patterns (Coding/Testing)

```python
ALLOWED_PATTERNS = [
    "test", "build", "lint", "format", "install",
    "npm *", "pip *", "pixi *", "git *", "python *",
]
```

Commands not matching these patterns should be rejected by the host agent. This prevents generated code from running arbitrary destructive commands like `rm -rf /`.

### Budget Policies (Default)

```python
class BudgetPolicy(BaseModel):
    max_total_tokens: int = 100_000      # Total tokens across all phases
    max_review_cycles: int = 8           # Maximum judge rejections before abort
    max_debate_rounds: int = 3           # Maximum debate rounds per phase
    max_runtime_minutes: int = 60        # Wall-clock time limit
    fallback_depth: int = 2              # Model fallback chain depth
    max_debate_budget_tokens: int = 15_000  # Token budget for debate
    memory_enabled: bool = False         # Cross-task memory (opt-in)
```

These are **hard ceilings**, not advisory limits. When any ceiling is hit, the task is aborted with a critical violation.

---

## Validation System

### Schema Checks (Deterministic Preconditions)

Before any LLM evaluation, outputs are validated against structural requirements:

| Phase | Required Sections |
|---|---|
| ContextHarvesting | `## Questions`, `## Constraints` |
| Specs | `## Requirements`, `## Scope`, `## Constraints` |
| Planning | `## Implementation Plan`, `## File Changes`, `## Risks` |
| Coding | Must reference specific files modified |
| Review | `## Issues Found`, `## Severity`, `## Must Fix` |
| Testing | `## Test Results`, `## Coverage`, `## Failed` |
| Done | Minimum 2 lines of content |

**Section extraction:** Searches for `## <heading>` patterns, extracts content until next `##` heading.

**Failure type:** Schema violations produce `TERMINAL_VALIDATION` failures — no retry, immediate rejection.

### Multi-Layer Validation Flow

```
Output submitted
    │
    ├─ 1. Schema checks (deterministic)
    │      └─ Required sections present and non-empty
    │      └─ If fail → TERMINAL_VALIDATION → immediate rejection
    │
    ├─ 2. JudgeEngine (LLM)
    │      └─ Locked prompt + temperature=0.0 + structured JSON
    │      └─ If fail → record rejection, increment iteration
    │
    ├─ 3. Debate (if configured and judge failed)
    │      └─ 3-round multi-agent protocol
    │      └─ ConsensusEngine evaluation
    │      └─ Can OVERTURN judge rejection if consensus passes
    │
    └─ 4. JudgeHierarchy (optional, multi-dimension)
           └─ 6 judge types evaluate different dimensions
           └─ Majority must pass, no critical blockers
```

### Spec-Lock Enforcement

After specification approval, the system monitors for scope drift:

**Expansion signals detected:**
- "additional feature"
- "also implement"
- "bonus feature"
- "while we're at it"
- "scope expansion"
- "new requirement"

**Requirement change signals:**
- "changed requirement"
- "updated requirement"
- "instead of"
- "no longer need"
- "replacing the requirement"

In strict mode, any drift signal is an `error`. In normal mode, implementation adaptations are allowed but requirement changes are still flagged.

---

## Auditability

### What Is Recorded

| Data | Storage | Retention |
|---|---|---|
| Phase transitions | Task history (SQLite) | Permanent |
| Authority decisions | Authority decision log (in-memory) | Session lifetime |
| Judge verdicts | Phase records + trace spans | Permanent / 7-30 days |
| Debate transcripts | Consensus results in task history | Permanent |
| Budget violations | Budget controller (in-memory) | Session lifetime |
| Trace spans | JSONL files | 7-30 days (errors: indefinite) |
| Checkpoint chain | JSON files | Permanent |
| Rollback records | RollbackManager history (in-memory) | Session lifetime |

### Reconstruction Capability

Given a task ID, the following can be fully reconstructed:
1. **Complete phase execution history** — from SQLite task record
2. **Every checkpoint version** — from versioned checkpoint chain
3. **Trace spans** — from JSONL trace files (within retention window)
4. **Debate transcripts** — from consensus results attached to phase records

### What Cannot Be Reconstructed

- Authority decision logs (in-memory, lost on restart)
- Budget violation history (in-memory, lost on restart)
- Retry counter state (in-memory, lost on restart)

These items should be persisted in a future version for complete auditability.

---

## Failure Safety Properties

### Critical Safety Invariants

| Invariant | Enforcement Mechanism | Violation Response |
|---|---|---|
| Budget ceilings are absolute | `BudgetController.should_continue()` | Task abort with critical violation |
| Phase transitions are validated | `PhaseGraph.is_valid_transition()` | `OrchestratorError` exception |
| Rollback never corrupts stable phases | `RollbackManager.plan_rollback()` safety check | Refuse unsafe rollback |
| Schema checks run before LLM judge | `JudgeEngine.evaluate()` three-stage gate | Terminal validation failure |
| Prompts are locked per task | `locked_prompts` dict on Task model | Deterministic replay |
| State writes are atomic | `tmp+rename` pattern | Crash-safe persistence |

### Failure Mode Analysis

| Failure Mode | Impact | Recovery Path |
|---|---|---|
| LLM provider down | No judge evaluation, no debate | Judge returns `passed=True` (fail-open); debate skipped |
| SQLite database locked | Writes fail | Retry with busy timeout (configured in StoreConfig) |
| Checkpoint file corrupted | Cannot restore version | Skip to next version or last stable |
| JSONL trace file corrupted | Missing observability data | Silently skip corrupt lines on read |
| Memory store corrupted | Lost cross-task context | Initialize empty; re-accumulate from new executions |
| Phase graph YAML invalid | Server won't start | `PhaseGraphError` at startup; fix config and restart |
| Model not pulled in Ollama | LLM calls fail | `dependency_gone` terminal failure; pull model and retry task |

### Fail-Open vs Fail-Closed

| Component | Failure Behavior | Rationale |
|---|---|---|
| Judge LLM call | **Fail-open** (pass with warning) | LLM unavailability shouldn't block execution |
| Schema checks | **Fail-closed** (reject immediately) | Structural violations are always wrong |
| Budget ceilings | **Fail-closed** (abort task) | Runaway execution is dangerous |
| Debate agent timeout | **Fail-open** (continue with remaining agents) | One agent's failure shouldn't block debate |
| Consensus LLM call | **Fail-open** (majority vote fallback) | Consensus should degrade, not break |
| Authority system | **Fail-closed** (deny unknown request types) | Unknown governance requests are suspicious |
