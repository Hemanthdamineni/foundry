# Runtime Invariants

> The 10 non-negotiable properties that every subsystem must respect, with enforcement mechanisms and violation consequences.

---

## Invariant Reference

### I1: Disk Is Truth

> Persistent state files are canonical. In-memory state is derived from disk state.

**Enforcement:** `StateManager` uses `tmp+rename` for atomic writes. `SqliteStore` uses `BEGIN IMMEDIATE`. On startup, all state is loaded from disk — in-memory structures are never authoritative.

**Violation consequence:** State corruption. Task progress lost. Checkpoint chain broken.

**How to verify:** Kill the server process mid-execution. Restart. Verify that the last completed phase is recoverable.

---

### I2: Validation-First

> Tool gates are authoritative. Schema checks are deterministic preconditions.

**Enforcement:** `SchemaChecks` run before `JudgeEngine`. Schema violations produce `TERMINAL_VALIDATION` failures — no retry, no debate.

**Violation consequence:** Structurally invalid output advances to downstream phases, causing cascading failures.

**How to verify:** Submit output missing a required section (e.g., `## Requirements` for Specs). Confirm it is rejected with a terminal error.

---

### I3: Budget Ceilings Are Absolute

> When a budget ceiling is hit, the task is aborted. No override.

**Enforcement:** `BudgetController.should_continue()` checked before every phase transition. `critical` violations set `status=stalled`.

**Violation consequence:** Runaway execution consuming unbounded tokens/time.

**How to verify:** Set `max_review_cycles=1`. Submit a failing output. Confirm the task is aborted after 1 rejection.

---

### I4: Phase Transitions Are Validated

> The FSM rejects invalid transitions.

**Enforcement:** `PhaseGraph` validates structure at construction. `OrchestratorFSM.submit()` verifies the transition exists in the graph. `OrchestratorAuthority` can block specific transitions.

**Violation consequence:** Tasks skip phases (e.g., Specs→Done), producing incomplete deliverables.

**How to verify:** Attempt to submit output claiming a transition not in the graph. Confirm rejection.

---

### I5: Rollback Never Corrupts Stable Phases

> Completed, stable-marked phases are sacred.

**Enforcement:** `RollbackManager.plan_rollback()` computes file overlap between rollback target and stable phases. If overlap exists, rollback is refused.

**Violation consequence:** Stable, validated work is destroyed by a rollback targeting a later phase.

**How to verify:** Mark Specs as stable. Attempt rollback from Coding to Chatting. Confirm refused.

---

### I6: Checkpoint-Recoverable

> Every phase transition produces a checkpoint. Crashes are recoverable.

**Enforcement:** `WriteQueue` triggers checkpoint creation on every accepted submission. `EnhancedCheckpointManager` creates versioned files with atomic writes.

**Violation consequence:** Server crash loses all progress since the last checkpoint.

**How to verify:** Complete 3 phases. Kill the server. Restore from checkpoint. Verify phase 3 state is intact.

---

### I7: Single Orchestrator

> One agent, internal behavioral modes via prompts. Not a swarm.

**Enforcement:** All execution flows through `tools/phase.py`. The `engine/` layer provides policies, not independent agents. Debate agents are LLM calls, not processes.

**Violation consequence:** Coordination complexity, state synchronization bugs, unpredictable recovery.

**How to verify:** Audit the codebase for any module that independently advances phases. There should be none.

---

### I8: Prompts Are Locked Per Task

> Prompt content hashes are frozen at task creation.

**Enforcement:** `Task.locked_prompts` populated at creation. `JudgeEngine` uses locked prompts when available. `ExecutionSnapshot.prompt_hashes` records content hashes.

**Violation consequence:** Same task produces different results on replay. Debugging becomes impossible.

**How to verify:** Create a task. Edit a judge prompt on disk. Verify the running task still uses the original prompt.

---

### I9: State Writes Are Atomic

> No state file write can produce a partially-written file.

**Enforcement:** All persistence uses `tmp+rename` (POSIX atomic) or `BEGIN IMMEDIATE` + `COMMIT`/`ROLLBACK` (SQLite).

**Violation consequence:** Half-written JSON files crash deserialization. Database corruption.

**How to verify:** Monitor write operations. Confirm all file writes go through a temporary file first.

---

### I10: Authority Is Centralized

> No component may advance phases without orchestrator approval.

**Enforcement:** `OrchestratorAuthority.request_authority()` is the single decision point. Decision log records every approval/rejection.

**Violation consequence:** Components independently advancing state produce conflicts and audit gaps.

**How to verify:** Search codebase for direct state mutations outside the authority system. There should be none in production code.

---

## Invariant Dependency Graph

```
I1 (Disk Is Truth)
    └── enables I6 (Checkpoint-Recoverable)
        └── enables I5 (Rollback Never Corrupts)

I2 (Validation-First)
    └── enables I4 (Transitions Validated)

I3 (Budget Ceilings)
    └── independent (enforced at every check point)

I7 (Single Orchestrator)
    └── enables I10 (Centralized Authority)
        └── enables I4 (Transitions Validated)

I8 (Prompts Locked)
    └── independent (enforced at task creation)

I9 (Atomic Writes)
    └── enables I1 (Disk Is Truth)
        └── enables I6 (Checkpoint-Recoverable)
```

**Root invariants:** I9 (Atomic Writes) and I7 (Single Orchestrator) are foundational. Most other invariants depend on these two.
