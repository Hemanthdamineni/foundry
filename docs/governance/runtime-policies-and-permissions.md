# Runtime Policies and Permissions

> OrchestratorAuthority, phase restrictions, sandbox configuration, spec-lock enforcement, and permission boundaries.

---

## OrchestratorAuthority

All runtime decisions pass through a centralized governance point. No component may advance phases, retry, replan, or rollback without explicit authority approval.

### Request Types

| Type | Requester | Decision Logic | Conditions |
|---|---|---|---|
| `phase_transition` | Phase controller | Check blocked transitions list | None |
| `debate_continue` | DebateRuntime | Always approved | None |
| `retry` | RetryPolicy | Per-phase retry count vs max | None |
| `replan` | Replanner | Always approved | `preserve_stable_work` |
| `recovery` | RecoveryEngine | Always approved | `restore_from_checkpoint`, `validate_state` |
| `rollback` | RollbackManager | Always approved | `never_corrupt_stable_phases` |
| `budget` | BudgetController | Check exhaustion set | None |

### Explicit Blocking

```python
authority.block_transition("Review", "Specs")   # Never regress from Review to Specs
authority.block_transition("Done", "Coding")     # Done is terminal
```

Blocks are **permanent** for the authority instance lifetime. No unblock mechanism — intentional prevention of runtime circumvention.

### Decision Audit Log

Every authority decision is recorded:

```python
authority.decision_log
# [{"request_type": "phase_transition", "approved": True, ...},
#  {"request_type": "retry", "approved": False, "reason": "Retry limit exceeded", ...}]
```

### Limitation

The authority decision log is **in-memory only** — lost on server restart. This should be persisted in a future version for complete cross-session auditability.

---

## Phase Restrictions

Different phases have different permission levels:

| Phase | File Editing | Shell Commands | Git Operations |
|---|---|---|---|
| Chatting | ✗ | ✗ | ✗ |
| ContextHarvesting | ✗ | ✗ | ✗ |
| Specs | ✗ | ✗ | ✗ |
| Planning | ✗ | ✗ | ✗ |
| Coding | ✓ | ✓ (pattern-restricted) | ✓ |
| Testing | ✓ | ✓ (pattern-restricted) | ✓ |
| Review | ✗ | ✗ | ✗ |
| Done | ✗ | ✗ | ✗ |

### Allowed Shell Patterns (Coding/Testing)

```python
ALLOWED_PATTERNS = [
    "test", "build", "lint", "format", "install",
    "npm *", "pip *", "pixi *", "git *", "python *",
]
```

Custom patterns configurable in `model_routing.yaml`:

```yaml
phases:
  Coding:
    bash_allowed_patterns: ["test", "build", "docker *", "cargo *"]
```

### Phase Restriction Implementation

```python
def _phase_restrictions(phase: str) -> list[str]:
    if phase in {"Coding", "Testing"}:
        return []  # Full tool access
    return ["Do not edit files in this phase.", "Do not run mutating shell commands."]
```

Restrictions are injected into the phase prompt. Enforcement depends on the host agent respecting the constraints.

---

## Sandbox Configuration

```python
class SandboxConfig(BaseModel):
    enabled: bool = False
    network_isolation: str = "localhost"       # Network access scope
    readonly_paths: list[str] = ["/usr", "/etc", "/nix/store"]
    writable_paths: list[str] = ["/workspace/src", "/workspace/tests"]
    denied_paths: list[str] = []
```

When enabled:
- **File access** restricted to `writable_paths` + `readonly_paths`
- **Network access** restricted to `network_isolation` scope
- **Denied paths** are always blocked, regardless of other settings

When disabled (default): full filesystem access. Acceptable for local development; should be enabled for shared/production use.

---

## Spec-Lock Enforcement

After specification approval, the system monitors all downstream outputs for scope drift.

### Expansion Signals (Detected)

```python
EXPANSION_SIGNALS = [
    "additional feature", "also implement", "bonus feature",
    "while we're at it", "scope expansion", "new requirement", "added requirement",
]
```

### Requirement Change Signals (Detected)

```python
CHANGE_SIGNALS = [
    "changed requirement", "updated requirement", "instead of",
    "no longer need", "replacing the requirement",
]
```

### Enforcement Modes

| Mode | Expansion Signals | Change Signals |
|---|---|---|
| Normal | `warning` | `error` |
| Strict | `error` | `error` |

In strict mode, any drift signal is an error. In normal mode, implementation adaptations are allowed but requirement changes are flagged.

---

## Fail-Open vs Fail-Closed Matrix

| Component | Failure Behavior | Rationale |
|---|---|---|
| Schema checks | **Fail-closed** | Structural violations are always wrong |
| Budget ceilings | **Fail-closed** | Runaway execution is dangerous |
| Authority system | **Fail-closed** | Unknown requests are suspicious |
| Judge LLM call | **Fail-open** | LLM unavailability shouldn't block execution |
| Debate agent timeout | **Fail-open** | One agent's failure shouldn't block debate |
| Consensus LLM call | **Fail-open** | Consensus should degrade, not break |

---

## Implementation Status

| Component | Status |
|---|---|
| OrchestratorAuthority | **Implemented** — rule-based decisions, audit log |
| Phase restrictions | **Implemented** — prompt-injected constraints |
| Sandbox config | **Implemented** — config model, not enforced at runtime |
| Spec-lock enforcement | **Implemented** — keyword-based drift detection |
| Authority persistence | **Not implemented** — in-memory only |
| Sandbox runtime enforcement | **Not implemented** — config exists but no filesystem interception |
