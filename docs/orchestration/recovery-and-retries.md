# Recovery and Retries

> Failure classification, 5-level retry escalation, replanning with stable work preservation, rollback safety, and recovery engine state management.

---

## Recovery Philosophy

Foundry's recovery system is built on a simple principle: **try the cheapest fix first, then escalate**. A syntax error doesn't need a full task rollback. A missing import doesn't need a phase restart. And a fundamentally flawed plan doesn't benefit from retrying the same approach.

The system classifies failures, selects the appropriate recovery level, and escalates only when cheaper approaches are exhausted.

---

## Failure Classification

### The FailureType Taxonomy

```python
class FailureType(StrEnum):
    # Retryable — transient, likely to succeed on retry
    RETRYABLE_MODEL   = "model_timeout"       # LLM call timed out
    RETRYABLE_INFRA   = "infra_transient"     # Infrastructure blip
    RETRYABLE_DEBATE  = "debate_timeout"      # Debate round timed out

    # Terminal — structural problem, retry won't help
    TERMINAL_VALIDATION = "validation_failed"  # Schema check failure
    TERMINAL_PHASE      = "phase_mismatch"     # Invalid phase transition
    TERMINAL_SANDBOX    = "sandbox_violation"   # Sandbox policy violated
    TERMINAL_DEPENDENCY = "dependency_gone"     # Required dependency unavailable
    TERMINAL_CONSENSUS  = "consensus_stalemate" # Debate deadlock

    # Orchestration — execution policy decisions
    ORCHESTRATION_CANCELLED = "cancelled"       # User cancelled
    ORCHESTRATION_LIMIT     = "limit_reached"   # Budget ceiling hit
    ORCHESTRATION_GATE      = "gate_blocked"    # Validation gate blocked
```

### Pattern-Based Classification

The retry policy classifies errors by matching against known patterns in error messages:

```python
FAILURE_PATTERNS = {
    # Syntax-level errors → LOCAL_RETRY
    ("syntax", "indent", "parse", "unterminated", "unexpected token"): "syntax_error",
    
    # Test failures → LOCAL_RETRY
    ("test", "assert", "expect", "failed test", "test error"): "test_failure",
    
    # Lint violations → LOCAL_RETRY
    ("lint", "ruff", "style", "formatting", "flake8"): "lint_violation",
    
    # Type errors → LOCAL_RETRY
    ("type error", "incompatible type", "missing argument"): "type_error",
    
    # Timeout → PHASE_RETRY
    ("timeout", "timed out", "deadline exceeded"): "timeout",
    
    # Integration issues → STRUCTURAL_REPLAN
    ("import", "module not found", "no module named"): "integration_issue",
    ("circular import", "circular dependency"): "integration_issue",
    
    # System crashes → FULL_RECOVERY
    ("crash", "segfault", "killed", "oom", "out of memory"): "system_crash",
}
```

The classification function scans the error message for any matching pattern (case-insensitive) and returns the corresponding failure type.

---

## 5-Level Escalation Ladder

### Level 0: LOCAL_RETRY

**What:** Same phase, same approach, fix the specific error.

**When:** Syntax errors, test failures, lint violations — errors that suggest the output was *almost* correct but has a specific fixable problem.

**How:** The error context is included in the next prompt, and the agent is asked to fix the specific issue without regenerating the entire output.

**Budget cost:** Low — one additional LLM call.

**Counter:** Per-phase `retry_count`, max 3 (configurable).

```python
if failure_type.startswith("RETRYABLE") and retry_count < max_retries:
    return RecoveryAction(level=LOCAL_RETRY, reason=f"Retry {retry_count+1}/{max_retries}")
```

### Level 1: LOCAL_REPLAN

**What:** Same phase, but regenerate the approach. Instead of fixing a specific error, rethink the approach entirely.

**When:** Validation failures (schema check says the output is structurally wrong), phase mismatches — the output isn't slightly wrong, it's *structurally* wrong.

**How:** The phase prompt is regenerated with error context emphasizing what structural requirements were violated.

**Budget cost:** Moderate — full phase re-execution.

**Counter:** Per-phase `replan_count`, max 2 (configurable).

```python
if failure_type in (TERMINAL_VALIDATION, TERMINAL_PHASE) and replan_count < max_replans:
    return RecoveryAction(level=LOCAL_REPLAN, reason="Structural re-approach needed")
```

### Level 2: PHASE_RETRY

**What:** Reset the phase entirely. Clear iteration count, start from scratch.

**When:** Timeouts (the phase execution took too long and produced nothing useful), or when local retries and replans are all exhausted.

**How:** Phase record is reset to `PENDING`. All previous attempts for this phase are preserved in history but the execution restarts.

**Budget cost:** Moderate-high — full phase re-execution without prior context.

```python
if (failure_type == "timeout" or retries_exhausted) and phase_retry_count < max_phase_retries:
    return RecoveryAction(level=PHASE_RETRY, reason="Phase reset")
```

### Level 3: STRUCTURAL_REPLAN

**What:** Invalidate the current phase AND all downstream phases. The `Replanner` determines which downstream phases need to be re-executed.

**When:** Integration issues (the code doesn't integrate with the existing codebase), consensus stalemates (debate couldn't reach agreement), dependency failures (a required external dependency is missing).

**How:** The Replanner:
1. Identifies the trigger phase
2. Invalidates all downstream non-stable phases
3. Additionally invalidates phases that depend on invalidated phases
4. Preserves all stable-marked phases

```python
scope = replanner.plan_replan(
    task_id=task.task_id,
    trigger_phase=current_phase,
    all_phases=all_phases,
    reason=error_message,
)
# scope.invalidated_phases = ["Coding", "Testing", "Review"]
# scope.preserved_phases = ["Specs", "Planning"]  (if marked stable)
```

### Level 4: FULL_RECOVERY

**What:** Restore from the last checkpoint and attempt from the last known good state.

**When:** System crashes, exhaustion of all lower recovery levels, or fundamental failures that suggest the entire execution path is corrupt.

**How:** The EnhancedCheckpointManager restores the task to a specific version:

```python
checkpoint = checkpoint_mgr.restore(task_id, version=last_stable_version)
task.current_phase = checkpoint.phase
task.history = checkpoint.history
task.iteration_count = checkpoint.iteration_count
```

**Budget cost:** High — potentially re-executes multiple phases.

---

## Recovery Engine (`engine/recovery_engine.py`, 168 lines)

### State Management

The recovery engine maintains per-phase counters:

```python
class RecoveryEngine:
    _retry_counts: dict[str, int]    # phase → retry attempts
    _replan_counts: dict[str, int]   # phase → replan attempts
    _failure_history: list[dict]     # All failures across all phases
```

### Classification Flow

```python
def classify_recovery(self, phase, error, failure_type):
    # 1. Check if failure is retryable and retries remain
    if failure_type in RETRYABLE_TYPES:
        if self._retry_counts.get(phase, 0) < self._max_retries:
            self._retry_counts[phase] = self._retry_counts.get(phase, 0) + 1
            return RecoveryAction(level=LOCAL_RETRY)
    
    # 2. Check if failure warrants replan and replans remain
    if failure_type in (TERMINAL_VALIDATION, TERMINAL_PHASE):
        if self._replan_counts.get(phase, 0) < self._max_replans:
            self._replan_counts[phase] = self._replan_counts.get(phase, 0) + 1
            return RecoveryAction(level=LOCAL_REPLAN)
    
    # 3. Check if structural replan is appropriate
    if failure_type in (TERMINAL_CONSENSUS, TERMINAL_DEPENDENCY):
        return RecoveryAction(level=STRUCTURAL_REPLAN)
    
    # 4. Everything else → full recovery
    return RecoveryAction(level=FULL_RECOVERY)
```

### Counter Isolation

Each phase has **independent** retry and replan counters:

```python
# Phase "Coding" exhausts its retries
recovery_engine._retry_counts = {"Coding": 3}

# Phase "Testing" still has full retry budget
recovery_engine._retry_counts.get("Testing", 0)  # → 0
```

Resetting a phase clears only that phase's counters:

```python
def reset_phase(self, phase):
    self._retry_counts.pop(phase, None)
    self._replan_counts.pop(phase, None)
```

---

## Replanner (`engine/replanner.py`, 108 lines)

### Core Invariant

> **PRESERVE COMPLETED STABLE WORK**

The replanner never invalidates a phase that has been explicitly marked as stable. This is the fundamental safety guarantee that makes replanning safe.

### Stable Phase Marking

```python
replanner.mark_stable(task_id, "Specs")     # Specs output is correct and final
replanner.mark_stable(task_id, "Planning")  # Plan is correct and final
```

Once marked stable, a phase is protected from invalidation in all replanning scenarios.

### Invalidation Algorithm

```python
def plan_replan(self, task_id, trigger_phase, all_phases, reason):
    trigger_index = all_phases.index(trigger_phase)
    
    # Start with trigger + all downstream phases
    candidates = set(all_phases[trigger_index:])
    
    # Remove stable phases
    stable = self._stable_phases.get(task_id, set())
    invalidated = candidates - stable
    
    # Add dependency-invalidated phases
    for phase in list(invalidated):
        deps = self._phase_deps.get(phase, [])
        for dep in deps:
            if dep not in stable:
                invalidated.add(dep)
    
    return ReplanScope(
        task_id=task_id,
        trigger_phase=trigger_phase,
        invalidated_phases=sorted(invalidated, key=all_phases.index),
        preserved_phases=sorted(stable),
        reason=reason,
    )
```

### Dependency-Aware Invalidation

Phases can have explicit dependencies beyond the linear graph order:

```python
replanner.set_phase_dependencies({
    "Testing": ["Coding"],           # Testing depends on Coding output
    "Review": ["Coding", "Testing"], # Review depends on both
})
```

If Coding is invalidated, Testing and Review are also invalidated (unless stable).

---

## Rollback Manager (`runtime/rollback_manager.py`, 144 lines)

### Safety Check

Before executing any rollback, the manager validates safety:

```python
def plan_rollback(self, task_id, to_phase, current_phase, all_phases):
    # Identify files touched by phases that will be rolled back
    phases_to_rollback = all_phases[all_phases.index(to_phase)+1 : all_phases.index(current_phase)+1]
    files_to_revert = set()
    for phase in phases_to_rollback:
        files_to_revert.update(self._phase_files.get(phase, []))
    
    # Identify files protected by stable phases
    protected_files = set()
    for phase in self._stable_phases:
        protected_files.update(self._phase_files.get(phase, []))
    
    # Safety check: no overlap allowed
    overlap = files_to_revert & protected_files
    safe = len(overlap) == 0
    
    return RollbackPlan(
        files_to_revert=files_to_revert,
        protected_files=protected_files,
        overlap=overlap,
        safe=safe,
        reason="Overlap with stable phase files" if not safe else "Safe to rollback",
    )
```

If `safe=False`, the rollback is **refused**. The caller must either:
1. Remove the stable marking from conflicting phases (explicit acknowledgment of data loss)
2. Choose a different rollback target that doesn't conflict

### Validation

```python
def validate_rollback(self, plan):
    """Final validation before execution."""
    if not plan.safe:
        return False, f"Unsafe: {len(plan.overlap)} files overlap with stable phases"
    if not plan.files_to_revert:
        return False, "No files to revert"
    return True, "Rollback is safe to execute"
```

---

## Execution Policy Integration

The `ExecutionPolicy` (`engine/execution_policy.py`) is the decision engine that connects failure classification to recovery actions:

### Budget Decisions

```python
def check_budget(self, task):
    if task.iteration_count >= task.budget.max_review_cycles:
        return Decision(action=ABORT, reason="Review cycle limit exceeded")
    
    token_estimate = sum(r.token_estimate or 0 for r in task.history)
    if token_estimate >= task.budget.max_total_tokens:
        return Decision(action=ABORT, reason="Token budget exhausted")
    
    return Decision(action=PROCEED)
```

### Retry Decisions

```python
def should_retry(self, failure_type, attempt):
    if failure_type.startswith("RETRYABLE"):
        max_attempts = {
            RETRYABLE_MODEL: 3,
            RETRYABLE_INFRA: 2,
            RETRYABLE_DEBATE: 1,
        }.get(failure_type, 2)
        
        if attempt < max_attempts:
            return Decision(action=RETRY, retry_after_s=2 ** attempt)  # Exponential backoff
        return Decision(action=ESCALATE, reason="Retries exhausted")
    
    if failure_type.startswith("TERMINAL"):
        return Decision(action=ABORT, reason=f"Terminal failure: {failure_type}")
    
    return Decision(action=ABORT, reason="Unknown failure type")
```

---

## Recovery Effectiveness Tracking

The retry policy tracks success rates per phase:

```python
class RetryPolicy:
    _effectiveness: dict[str, dict] = {
        "Coding": {"total": 5, "succeeded": 3},    # 60% success rate
        "Testing": {"total": 8, "succeeded": 7},   # 87.5% success rate
        "Review": {"total": 2, "succeeded": 0},    # 0% success rate
    }
```

### No-Progress Detection

If the last N retries all failed, the system signals that escalation is needed regardless of remaining budget:

```python
def detect_no_progress(self, phase, window=3):
    recent = self._attempt_history[phase][-window:]
    if len(recent) >= window and all(not a.succeeded for a in recent):
        return True  # No progress — escalate
    return False
```

This prevents the system from burning through its entire retry budget on an approach that is clearly not working.

---

## Recovery Flow Integration

### Where Recovery Runs in submit_output

```python
# In tools/phase.py submit_output handler:

verdict = await judge_engine.evaluate(task, from_phase, to_phase, output)

if not verdict.passed:
    # Classify the failure
    failure_type = policy.classify_failure(verdict.reason)
    
    # Determine recovery action
    recovery = recovery_engine.classify_recovery(
        phase=task.current_phase,
        error=verdict.reason,
        failure_type=failure_type,
    )
    
    # Apply recovery
    if recovery.level == LOCAL_RETRY:
        task.iteration_count += 1
        # Stay in same phase, return rejection with error context
    
    elif recovery.level == LOCAL_REPLAN:
        task.iteration_count += 1
        # Stay in same phase, prompt will be regenerated
    
    elif recovery.level == STRUCTURAL_REPLAN:
        scope = replanner.plan_replan(task.task_id, task.current_phase, ...)
        # Invalidate downstream phases
    
    elif recovery.level == FULL_RECOVERY:
        checkpoint = checkpoint_mgr.restore(task.task_id)
        # Restore to last checkpoint
```

---

## Implementation Status

| Component | Status |
|---|---|
| RetryPolicy (5-level escalation) | **Implemented** |
| RecoveryEngine (classification + counters) | **Implemented** |
| Replanner (stable work preservation) | **Implemented** |
| RollbackManager (safety checks) | **Implemented** |
| ExecutionPolicy (budget + retry decisions) | **Implemented** |
| Effectiveness tracking | **Implemented** |
| No-progress detection | **Implemented** |
| Counter isolation per phase | **Implemented** |
| Rollback ↔ checkpoint integration | **Partial** — rollback plans exist but execution not fully wired |
| Replanner ↔ submit_output integration | **Partial** — replanning scope computed but not auto-applied |
