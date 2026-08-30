# Phase 1: Single Submit Pipeline

## Phase Overview

**Goal:** Make `sdlc_submit_output` the only phase-transition authority and turn the current implicit flow into explicit, testable runtime stages.

**Rationale:** ToolGate, retry, and recovery cannot be safely integrated while the submit path is a loose sequence of inline operations. This phase creates the stable spine that later phases wire into.

**Dependencies:** Phase 0 complete.

**Runtime impact:** `submit_output` gains explicit stage ordering, clearer rejection behavior, persistent rejected attempts, and feature-only workflow truth.

**Blocking systems:**

- Current submit flow advances without an explicit deterministic validation stage.
- Rejected attempts persist only partially.
- Non-feature modes are accepted even though runtime always loads the feature graph.

**Acceptance gates:**

- Invalid task status cannot advance.
- Invalid phase cannot advance.
- Invalid transition target cannot advance.
- `Chatting -> Done` cannot be used as an accidental shortcut for normal feature tasks.
- Deterministic schema failures cannot advance.
- Rejected attempts are visible in task history/status.
- Non-feature modes are rejected or explicitly unsupported.

## Task P1-01: Stage the Submit Pipeline

**Objective:** Refactor `submit_output` into explicit ordered stages without changing architecture.

**Subsystem:** Orchestration Runtime.

**Priority:** P0.

**Dependencies:** P0-01, P0-02.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/app.py`
- `sdlc/models.py`
- `sdlc/engine/orchestrator.py`
- `sdlc/engine/execution_policy.py`
- `sdlc/engine/schema_checks.py`
- `sdlc/engine/judge.py`
- `sdlc/runtime/write_queue.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- MCP tool `sdlc_submit_output`
- `phase_tools.submit_output(...)`
- `OrchestratorFSM.submit(...)`
- `ExecutionPolicy.check_budget(...)`
- `WriteQueue.enqueue(...)`

**Expected runtime behavior:**

- Submit loads the task first.
- Submit rejects missing, cancelled, done, or stalled tasks.
- Submit rejects phase mismatch before any validation or mutation.
- Submit resolves the target transition before accepting output.
- Submit rejects `Chatting -> Done` for normal feature tasks unless an explicit
  early-completion policy marks and persists the reason.
- Submit does not mutate current phase until all acceptance gates pass.

**Implementation notes:**

- Introduce private helper functions in `sdlc/runtime/tools/phase.py` only if they reduce stage ambiguity.
- Do not create a new orchestrator subsystem.
- Keep existing `OrchestratorFSM` as the transition authority.
- Keep existing `ExecutionPolicy` as the minimal budget gate.

**Failure considerations:**

- A helper raising unexpectedly must return a structured rejected result, not leave partial writes.
- Any write before final acceptance must be explicitly for rejected-attempt persistence.

### Ordered Subtasks

1. Identify current stage boundaries in `submit_output`.
2. Add explicit task-status guard for `DONE`, `CANCELLED`, and `STALLED`.
3. Keep phase mismatch check before budget and FSM work.
4. Resolve candidate next phase through `OrchestratorFSM.submit`.
5. Add explicit guard for `Chatting -> Done` normal feature submissions.
6. Move task mutation until after validation success.
7. Ensure every rejection path returns `accepted: false`.
8. Add integration tests for missing task, phase mismatch, invalid target, guarded `Chatting -> Done`, and done/cancelled/stalled task.

### Runtime Invariants

- Deterministic phase transition remains owned by `OrchestratorFSM`.
- SQLite remains task authority.
- No accepted transition happens before all gates pass.
- Rejection does not advance phase.
- Normal feature tasks cannot skip directly from `Chatting` to `Done`.

### Validation Requirements

- Unit tests for helper functions if introduced.
- Integration tests through MCP or direct phase tool invocation.
- Failure-path validation for invalid phase and invalid target.
- Done when current happy-path behavior still works and new rejection paths are covered.

## Task P1-02: Make Schema Validation Explicit

**Objective:** Run deterministic schema validation as its own stage before LLM judge.

**Subsystem:** Validation.

**Priority:** P0.

**Dependencies:** P1-01.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/engine/schema_checks.py`
- `sdlc/engine/judge.py`
- `sdlc/models.py`
- `sdlc/tests/test_phase1.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- `submit_output` deterministic validation stage.
- Existing `validate_phase_output(...)`.
- Existing `JudgeEngine.evaluate(...)`.

**Expected runtime behavior:**

- Schema validation runs before judge.
- Schema failure is a deterministic rejection.
- Judge does not run when schema fails.
- Schema rejection is persisted as a rejected attempt.

**Implementation notes:**

- Avoid duplicating validation rules.
- If `JudgeEngine.evaluate` still calls schema checks internally, that is acceptable temporarily, but `submit_output` must own the first deterministic rejection.
- Keep Chatting rules minimal and deterministic.

**Failure considerations:**

- Schema validation failures are not retryable transient failures.
- Schema failure must not trigger debate or tool gates.

### Ordered Subtasks

1. Import/use `validate_phase_output` in `phase.py`.
2. Run schema checks after FSM target resolution and before judge.
3. Build a structured failure payload from violations.
4. Persist rejected attempt with reason `schema_validation_failed`.
5. Add tests proving judge is skipped on schema failure.

### Runtime Invariants

- Deterministic validation precedes probabilistic validation.
- Schema rejection keeps current phase unchanged.
- Schema failures are stable for same input.

### Validation Requirements

- Unit tests for schema violation payload shape.
- Integration tests for invalid Specs, Planning, Review, and Testing output.
- Done when schema failure never advances the task.

## Task P1-03: Persist Rejected Attempts Consistently

**Objective:** Make rejected submissions recoverable and inspectable.

**Subsystem:** Persistence.

**Priority:** P0.

**Dependencies:** P1-01, P1-02.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/tools/task.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/runtime/write_queue.py`
- `sdlc/models.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- `WriteOp(target="task", action="update", ...)`
- `WriteOp(target="phase_output", action="create", ...)`
- `sdlc_get_status`

**Expected runtime behavior:**

- Rejected attempts append a `PhaseRecord` with status `REJECTED`.
- Rejected attempts are saved to phase history.
- Task remains in same `current_phase`.
- Status/history expose the latest rejected attempt.

**Implementation notes:**

- Use existing `PhaseRecord` rather than adding new models unless absolutely required.
- Include error/reason, iteration count, and validation metadata where available.
- Avoid checkpointing rejected attempts unless later recovery semantics explicitly require it.

**Failure considerations:**

- If rejected-attempt persistence fails, return the write failure rather than pretending rejection was recorded.
- Do not partially advance task on failed write.

### Ordered Subtasks

1. Create one helper to append rejected phase record.
2. Persist task update after appending rejected record.
3. Persist phase output with status `rejected`.
4. Update `get_status` only if current history output is insufficient.
5. Add tests for rejected attempt visibility.

### Runtime Invariants

- Rejection does not advance.
- SQLite task state and phase history do not contradict each other.
- Iteration count changes are deterministic and persisted.

### Validation Requirements

- Integration test: submit invalid Specs, call status, verify phase unchanged and rejection visible.
- Integration test: restart or reload store and verify rejection remains.
- Done when rejected attempts are not invisible runtime events.

## Task P1-04: Enforce Feature-Only Mode Truth

**Objective:** Remove false support for non-feature workflows during MVP.

**Subsystem:** Workflow Runtime.

**Priority:** P0.

**Dependencies:** P0-03.

**Exact files/modules involved:**

- `sdlc/runtime/app.py`
- `sdlc/runtime/tools/task.py`
- `sdlc/tests/test_integration.py`
- `sdlc/tests/test_templates.py`

**Exact runtime integration points:**

- MCP tool `sdlc_create_task`
- Task `mode` field.

**Expected runtime behavior:**

- `mode="feature"` succeeds.
- Non-feature modes return explicit unsupported-mode error until mode-to-graph selection is implemented.
- Runtime does not imply bugfix/refactor/research/docs support.

**Implementation notes:**

- Do not delete existing graph files.
- Do not wire additional graph selection in MVP unless it becomes necessary for feature correctness.
- Error text should say non-feature workflows are deferred.

**Failure considerations:**

- Avoid raising unhandled exceptions that break MCP response shape.
- Existing tests expecting accepted non-feature modes must be corrected to the new MVP boundary.

### Ordered Subtasks

1. Change supported modes in `sdlc_create_task` to `{"feature"}`.
2. Return or raise a clear unsupported-mode error for other modes.
3. Add integration test for `feature` accepted.
4. Add integration test for `bugfix` rejected.
5. Leave graph template tests as template existence tests, not workflow support tests.

### Runtime Invariants

- One workflow.
- One authoritative FSM.
- No false capability.

### Validation Requirements

- MCP integration tests for supported and unsupported modes.
- Done when non-feature mode cannot silently run the feature graph.
