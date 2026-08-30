# Phase 4: MVP End-to-End Feature Workflow

## Phase Overview

**Goal:** Prove one operational deterministic autonomous execution loop for the feature workflow.

**Rationale:** Earlier phases wire the spine. Phase 4 proves the whole runtime path works under happy path, validation failure, transient failure, and restart.

**Dependencies:** Phases 1, 2, and 3 complete.

**Runtime impact:** Foundry reaches MVP only if this phase passes.

**Blocking systems:**

- Missing end-to-end feature workflow test.
- Potential dependence on live model/tool availability.
- Incomplete status/diagnostic reporting for rejected attempts.

**Acceptance gates:**

- Feature workflow reaches Done.
- ToolGate blocks bad code phases.
- Recovery resumes accepted state.
- Retry exhaustion cannot loop.
- SQLite task authority remains consistent.

## Task P4-01: Build Deterministic Feature Workflow E2E Test

**Objective:** Validate complete feature workflow through the authoritative submit path.

**Subsystem:** Quality and Validation.

**Priority:** P0.

**Dependencies:** P1-01 through P3-04.

**Exact files/modules involved:**

- `sdlc/tests/test_integration.py`
- `sdlc/runtime/app.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/tool_executor.py`
- `sdlc/runtime/tool_gate.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/engine/checkpoint.py`

**Exact runtime integration points:**

- `sdlc_create_task`
- `sdlc_get_next_action`
- `sdlc_submit_output`
- `sdlc_get_status`

**Expected runtime behavior:**

- Feature task advances Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done.
- Each advancement goes through `submit_output`.
- Coding/Testing gate summaries are present.
- Final task status is `done`.

**Implementation notes:**

- Use controlled outputs that satisfy schema.
- Use controlled/fake validation where needed to avoid environment-specific failures.
- Do not require real autonomous code generation for MVP validation; validate runtime execution loop.

**Failure considerations:**

- If live LLM is required, the test is not deterministic.
- If validation depends on installed tools, provide controlled adapters or mark environment requirement explicitly.

### Ordered Subtasks

1. Create deterministic task.
2. Submit valid Chatting output.
3. Submit valid Specs output.
4. Submit valid Planning output.
5. Submit Coding output with passing validation setup.
6. Submit Review output targeting Testing.
7. Submit Testing output with passing validation setup.
8. Assert Done status and persisted history.

### Runtime Invariants

- Every phase transition goes through FSM.
- Tool validation is required only for Coding/Testing.
- Checkpoint follows accepted transitions.

### Validation Requirements

- E2E integration test.
- Status check after completion.
- History length and phase order assertions.
- Done when deterministic feature happy path passes.

## Task P4-02: Validate ToolGate Failure Path End-to-End

**Objective:** Prove bad Coding/Testing submissions cannot advance.

**Subsystem:** Validation.

**Priority:** P0.

**Dependencies:** P2-03, P2-04.

**Exact files/modules involved:**

- `sdlc/tests/test_integration.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/tool_gate.py`
- `sdlc/runtime/tool_executor.py`
- `sdlc/runtime/tools/task.py`

**Exact runtime integration points:**

- Coding `submit_output`.
- Testing `submit_output`.
- `sdlc_get_status`.

**Expected runtime behavior:**

- Failing Coding gate returns `accepted: false`.
- Task remains in Coding.
- Rejected attempt is visible.
- Failing Testing gate returns `accepted: false`.
- Task remains in Testing.

**Implementation notes:**

- Use controlled failing adapter behavior.
- Assert failed gate name and errors are returned.

**Failure considerations:**

- Do not classify real validation failure as transient retry.
- Do not write checkpoint for rejected gate failure.

### Ordered Subtasks

1. Advance task to Coding.
2. Configure validation to fail lint or tests.
3. Submit Coding output.
4. Assert phase remains Coding.
5. Assert rejected attempt persisted.
6. Repeat for Testing.

### Runtime Invariants

- Tool failure blocks phase advancement.
- Rejected gate failure does not checkpoint accepted state.
- SQLite history explains failure.

### Validation Requirements

- Integration tests for Coding and Testing failure.
- Runtime check for unchanged phase.
- Done when bad code cannot advance.

## Task P4-03: Validate Recovery and Retry End-to-End

**Objective:** Prove transient failures and restart recovery are bounded and deterministic.

**Subsystem:** Recovery.

**Priority:** P0.

**Dependencies:** P3-01, P3-02, P3-03, P3-04.

**Exact files/modules involved:**

- `sdlc/tests/test_integration.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/engine/checkpoint.py`
- `sdlc/runtime/tool_executor.py`

**Exact runtime integration points:**

- ToolExecutor transient failure path.
- Retry persistence.
- Checkpoint restore/resume.
- `sdlc_get_status`.

**Expected runtime behavior:**

- Transient failure retries within ceiling.
- Retry success can proceed only after validation passes.
- Retry exhaustion returns non-advancing terminal/stalled state.
- Restart resumes latest accepted phase.

**Implementation notes:**

- Use fake transient executor behavior in tests if possible.
- Keep retry ceiling low in tests.
- Do not test replay or rollback.

**Failure considerations:**

- Avoid nondeterministic sleep-heavy tests.
- Avoid external network/model dependencies.

### Ordered Subtasks

1. Add transient failure fixture or fake adapter.
2. Test transient failure followed by success.
3. Test transient failure exhaustion.
4. Assert persisted retry count.
5. Restart server and assert phase/status consistency.

### Runtime Invariants

- Retry ceiling is hard.
- Retry does not bypass ToolGate.
- Restart does not erase retry state.

### Validation Requirements

- Integration test for retry success.
- Integration test for retry exhaustion.
- Integration test for restart after accepted checkpoint.
- Done when recovery path is tested with both success and failure.

## Task P4-04: Final MVP Runtime Audit

**Objective:** Verify implementation did not drift beyond corrected MVP boundaries.

**Subsystem:** Release Readiness.

**Priority:** P0.

**Dependencies:** P4-01, P4-02, P4-03.

**Exact files/modules involved:**

- `planning/MASTER-ROADMAP.md`
- `planning/RUNTIME-SPEC.md`
- `planning/DEPENDENCY-GRAPH.md`
- `planning/execution/MVP-COMPLETION.md`
- Runtime files touched in Phases 1-4.

**Exact runtime integration points:** All MVP runtime path points.

**Expected runtime behavior:** MVP behavior is demonstrably limited to the feature workflow and authoritative validation/recovery loop.

**Implementation notes:** This is an audit gate, not a refactor phase.

**Failure considerations:** If any deferred system became necessary, update the plan only if it is directly required for the MVP runtime path.

### Ordered Subtasks

1. Confirm feature-only workflow behavior.
2. Confirm no rollback/replay/dashboard/memory dependency in MVP path.
3. Confirm docs match implemented behavior.
4. Confirm tests cover happy path, validation failure, retry, and restart.
5. Update `MVP-COMPLETION.md` with pass/fail evidence.

### Runtime Invariants

- No architecture expansion.
- No speculative subsystem dependency.
- Operational status matches tests.

### Validation Requirements

- Full targeted test suite passes.
- `git diff --check` passes for changed files.
- Done when MVP completion gates are all satisfied.

