# Phase 3: Checkpoint Restore and Bounded Recovery

## Phase Overview

**Goal:** Make accepted progress recoverable and transient failures bounded.

**Rationale:** Checkpoint files currently exist as snapshots, but recovery is not operational. This phase turns latest checkpoint restore/resume and minimal retry handling into real runtime behavior without introducing advanced replay or rollback.

**Dependencies:** Phase 1 and Phase 2 complete.

**Runtime impact:** Runtime can resume from persisted accepted state and avoids infinite retry loops.

**Blocking systems:**

- Latest checkpoint restore is not wired.
- Retry counts are not persisted.
- Exhausted failures do not consistently stall or return terminal non-advancing results.

**Acceptance gates:**

- Accepted transitions survive restart.
- Latest checkpoint can restore missing task state when explicitly invoked.
- `sdlc_resume_task(task_id)` is the explicit MVP recovery entrypoint.
- Retry ceilings are persisted and enforced.
- Exhausted transient failures cannot loop forever.

## Task P3-01: Define Latest Checkpoint Resume Path

**Objective:** Add operational restore/resume behavior using existing SQLite store and base CheckpointManager.

**Subsystem:** Recovery.

**Priority:** P0.

**Dependencies:** P1-03, P2-04.

**Exact files/modules involved:**

- `sdlc/runtime/app.py`
- `sdlc/runtime/tools/task.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/engine/checkpoint.py`
- `sdlc/models.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- App lifespan initialization.
- Existing `CheckpointManager.restore(...)`.
- Existing `SqliteStore.restore_checkpoint(...)`.
- Task status/get next action after restart.
- MCP tool `sdlc_resume_task(task_id)`.

**Expected runtime behavior:**

- Normal task reads prefer SQLite.
- `sdlc_resume_task(task_id)` can restore from latest checkpoint when task state is missing or explicitly requested.
- SQLite/checkpoint disagreement is reported, not silently hidden.

**Implementation notes:**

- Do not introduce versioned checkpoints for MVP.
- Do not wire `EnhancedCheckpointManager` unless latest restore cannot be done with current checkpoint manager.
- Add minimal `sdlc_resume_task(task_id)` if absent. This is an MVP entrypoint,
  not a new subsystem.
- Normal status reads must not silently mutate state.

**Failure considerations:**

- Corrupt checkpoint returns explicit recovery failure.
- Missing checkpoint returns explicit not-recoverable result.
- Divergent SQLite/checkpoint state must not be silently overwritten.

### Ordered Subtasks

1. Document current checkpoint write shape in code comments or tests.
2. Add helper to load latest checkpoint for task.
3. Add helper to compare checkpoint phase/history with SQLite task state.
4. Add MCP/runtime handler `sdlc_resume_task(task_id)`.
5. Add recovery path for missing task with existing checkpoint.
6. Add explicit mismatch result for divergent states.
7. Add integration tests for restore success, missing checkpoint, and mismatch.

### Runtime Invariants

- SQLite is normal task authority.
- Checkpoint is recovery snapshot.
- Accepted phase history is not silently discarded.
- Resume is explicit and does not silently overwrite mismatches.

### Validation Requirements

- Unit tests for checkpoint/task comparison helper.
- Integration test: create task, advance, restart, get same phase/history.
- Integration test: invoke `sdlc_resume_task` to restore/reconcile latest checkpoint.
- Integration test: remove/corrupt task state if feasible, restore from checkpoint.
- Done when checkpoint restore is operational and bounded.

## Task P3-02: Persist Minimal Retry State

**Objective:** Store retry count and last failure reason needed for deterministic bounded retry.

**Subsystem:** Recovery and Persistence.

**Priority:** P0.

**Dependencies:** P1-03, P2-04.

**Exact files/modules involved:**

- `sdlc/models.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/runtime/write_queue.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- Task model persisted in SQLite.
- Rejected phase record.
- Validation failure paths in submit flow.

**Expected runtime behavior:**

- Retry count persists across process restart.
- Last failure reason persists.
- Retry count is scoped to task and current phase.

**Implementation notes:**

- Prefer adding minimal fields to `Task` only if current `iteration_count` is not sufficient.
- Do not implement five-level escalation.
- Do not create a separate retry database.

**Failure considerations:**

- Retry state must reset or advance deterministically after accepted phase transition.
- Retry counters must not count deterministic schema failures as transient retries.

### Ordered Subtasks

1. Decide whether existing `iteration_count` can represent MVP retry ceilings.
2. If not, add minimal persisted retry metadata to `Task`.
3. Update rejected transient failure path to increment retry count.
4. Update accepted transition path to clear phase-scoped retry failure state.
5. Add persistence tests across store reload.

### Runtime Invariants

- Retry state is persisted.
- Retry state does not advance phase.
- Retry ceilings are deterministic.

### Validation Requirements

- Unit test task model serialization/deserialization for retry metadata if added.
- Integration test retry count survives restart.
- Done when retry decisions do not depend only on memory.

## Task P3-03: Implement Bounded Transient Retry

**Objective:** Retry only transient runtime failures within a hard ceiling.

**Subsystem:** Recovery.

**Priority:** P0.

**Dependencies:** P3-02, P2-03.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/tool_executor.py`
- `sdlc/engine/execution_policy.py`
- `sdlc/models.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- ToolExecutor failure classification.
- Judge/model failure handling.
- Submit rejected/stalled result.

**Expected runtime behavior:**

- Transient ToolExecutor failures retry up to ceiling.
- Transient judge/model failures follow explicit policy.
- Deterministic schema failures do not retry.
- Real lint/type/test failures do not retry as runtime failures.
- Missing required adapter, checkpoint corruption, and SQLite/checkpoint mismatch do not retry as transient.
- Exhaustion returns non-advancing terminal/stalled result.

**Implementation notes:**

- Keep retry ceiling simple and configurable through existing budget/policy fields if possible.
- Do not implement replanning or rollback in MVP.
- Do not add autonomous loops outside submit.

**Failure considerations:**

- Retrying a failing user test forever is forbidden.
- Retrying missing tool may be terminal dependency failure, not transient retry.

### Ordered Subtasks

1. Classify failures into transient, gate failure, unsupported dependency, and terminal contract/recovery failure.
2. Add retry loop around transient validation execution only.
3. Persist retry count before each retry or after failure.
4. Return final failure without phase advancement on exhaustion.
5. Mark task stalled when configured ceiling is exhausted.
6. Add tests for transient retry success and exhausted retry.

### Runtime Invariants

- No infinite retry.
- Retry does not bypass validation.
- Retry state survives restart.

### Validation Requirements

- Unit tests for classification mapping.
- Integration test with fake transient ToolExecutor failure.
- Integration test with permanent gate failure.
- Integration test proving missing Mypy/checkpoint mismatch is not transient.
- Done when transient and deterministic failures behave differently.

## Task P3-04: Restart/Resume Integration Test

**Objective:** Prove accepted progress survives process restart.

**Subsystem:** Quality and Validation.

**Priority:** P0.

**Dependencies:** P3-01, P3-02.

**Exact files/modules involved:**

- `sdlc/tests/test_integration.py`
- `sdlc/runtime/app.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/engine/checkpoint.py`

**Exact runtime integration points:**

- MCP subprocess startup/shutdown.
- SQLite database path.
- Checkpoint directory.
- `sdlc_get_status`.
- `sdlc_get_next_action`.

**Expected runtime behavior:**

- Create task and advance to a known phase.
- Stop server.
- Restart server using same runtime paths.
- Status reports same task phase/history.
- Next action resumes from latest accepted phase.

**Implementation notes:**

- Keep test bounded and deterministic.
- Use fake/mock judge behavior where needed to avoid live model dependency.
- Avoid tests that hang on external LLM availability.

**Failure considerations:**

- If test requires live Ollama/OpenAI, it is not an MVP CI gate.
- Runtime paths must be isolated per test to avoid leaked state.

### Ordered Subtasks

1. Add fixture that starts server with stable temp runtime directory.
2. Create task and advance at least through Specs or Planning.
3. Stop server cleanly.
4. Restart server with same temp runtime directory.
5. Query status and next action.
6. Assert phase/history consistency.

### Runtime Invariants

- Accepted state survives process lifetime.
- SQLite and checkpoint do not contradict successful resume.
- No external LLM dependency in deterministic recovery test.

### Validation Requirements

- Integration test passes locally and in CI.
- Done when restart/resume behavior is proven.
