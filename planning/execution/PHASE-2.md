# Phase 2: ToolExecutor and ToolGate Enforcement

## Phase Overview

**Goal:** Make Coding and Testing transitions depend on governed validation through ToolExecutor and ToolGate.

**Rationale:** The runtime cannot claim autonomous engineering correctness while code phases advance without lint/type/test validation. This phase turns validation from scaffolded modules into authoritative runtime behavior.

**Dependencies:** Phase 1 complete.

**Runtime impact:** Coding/Testing submissions run validation before phase advancement. Failed validation persists rejection and keeps the phase unchanged.

**Blocking systems:**

- ToolExecutor exists but is not initialized by app lifespan.
- ToolGate exists but is not called by submit flow.
- MVP adapters are not registered into a validation path.

**Acceptance gates:**

- ToolExecutor is initialized in runtime context.
- ToolGate is initialized in runtime context.
- Coding/Testing failing validation blocks transition.
- Coding/Testing passing validation allows transition.
- Gate result is persisted.
- Required adapter absence is explicit failure/unsupported, not a silent pass.

## Task P2-01: Initialize MVP ToolExecutor

**Objective:** Construct ToolExecutor during app lifespan and make it available to phase tools.

**Subsystem:** Execution Runtime.

**Priority:** P0.

**Dependencies:** P1-01.

**Exact files/modules involved:**

- `sdlc/runtime/app.py`
- `sdlc/runtime/tool_executor.py`
- `sdlc/adapters/base.py`
- `sdlc/adapters/tools/ruff.py`
- `sdlc/adapters/tools/mypy.py`
- `sdlc/adapters/tools/pytest.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- `lifespan(...)`
- `SDLCAppContext`
- `sdlc_submit_output(...)`
- `phase_tools.submit_output(...)`

**Expected runtime behavior:**

- App lifespan creates one ToolExecutor instance.
- MVP adapters are registered with the executor.
- Phase tools receive the executor via context injection.
- Missing optional adapter policy is explicit.
- MVP adapter payload is stable: `task_id`, `phase`, workspace-root `path`, `timeout_s`.

**Implementation notes:**

- Register only MVP adapters: Ruff, Mypy, Pytest.
- If adapter healthchecks are too strict for local dev, expose health status but do not silently mark required validation passed.
- Do not introduce a new tool gateway module.

**Failure considerations:**

- If a required adapter is unavailable, Coding/Testing validation must fail closed or return explicit unsupported.
- Mypy cannot silently pass the `types` gate when missing or unhealthy.
- Startup should not crash for optional adapter absence unless configured as required.

### Ordered Subtasks

1. Add `tool_executor` field to `SDLCAppContext`.
2. Instantiate `ToolExecutor` in `lifespan`.
3. Instantiate Ruff, Mypy, and Pytest adapters.
4. Register adapters with ToolExecutor.
5. Pass ToolExecutor into `phase_tools.submit_output`.
6. Standardize the adapter payload:
   `{"task_id": task_id, "phase": phase, "path": workspace_path, "timeout_s": 30}`.
7. Add tests that context contains executor and required adapters are known.
8. Add test for missing/unhealthy Mypy returning explicit unsupported/failed result.

### Runtime Invariants

- Tool execution is governed by ToolExecutor.
- Phase code does not call validation adapters directly.
- ToolExecutor does not decide phase transitions.
- ToolExecutor payload shape is deterministic across adapters.

### Validation Requirements

- Unit test ToolExecutor registration if not already covered.
- Integration test server startup with executor initialized.
- Done when submit flow can receive executor without changing behavior yet.

## Task P2-02: Initialize MVP ToolGate

**Objective:** Construct ToolGate with deterministic MVP gate order and pass it into submit flow.

**Subsystem:** Validation Runtime.

**Priority:** P0.

**Dependencies:** P2-01.

**Exact files/modules involved:**

- `sdlc/runtime/app.py`
- `sdlc/runtime/tool_gate.py`
- `sdlc/runtime/tools/phase.py`
- `sdlc/tests/test_phase*.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- `lifespan(...)`
- `SDLCAppContext`
- `phase_tools.submit_output(...)`

**Expected runtime behavior:**

- App lifespan creates one ToolGate instance.
- Gate order is `lint -> types -> tests` for Coding/Testing.
- Other phases have no tool gate for MVP.
- Missing/unhealthy required gate is a gate failure or unsupported result.

**Implementation notes:**

- Use existing ToolGate sequence mechanisms.
- If ToolGate names differ from adapter capability names, add minimal mapping in phase tool code, not a new subsystem.
- Required result mapping is local and deterministic:
  pass, fail, transient execution failure, unsupported, terminal adapter failure.

**Failure considerations:**

- Gate order must not depend on dictionary iteration.
- Gate exceptions must not silently disable Coding/Testing validation.

### Ordered Subtasks

1. Add `tool_gate` field to `SDLCAppContext`.
2. Instantiate ToolGate with MVP order.
3. Define helper for phases requiring tool validation.
4. Pass ToolGate into `phase_tools.submit_output`.
5. Add mapper from ToolExecutor result to ToolGate result.
6. Add unit test for phase-to-gate behavior and result mapping.

### Runtime Invariants

- Gate order is deterministic.
- ToolGate evaluates results; it does not execute tools.
- Coding/Testing are the only MVP gated phases.
- Missing Mypy cannot become a passing `types` gate.

### Validation Requirements

- Unit test ToolGate order.
- Integration test non-code phases do not require ToolGate.
- Done when ToolGate is available to submit flow.

## Task P2-03: Execute Validation Before Coding/Testing Advancement

**Objective:** Wire ToolExecutor and ToolGate into `submit_output` before phase mutation.

**Subsystem:** Authoritative Validation.

**Priority:** P0.

**Dependencies:** P2-01, P2-02, P1-03.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/tool_executor.py`
- `sdlc/runtime/tool_gate.py`
- `sdlc/adapters/tools/ruff.py`
- `sdlc/adapters/tools/mypy.py`
- `sdlc/adapters/tools/pytest.py`
- `sdlc/models.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- `phase_tools.submit_output(...)`
- ToolExecutor `execute(...)` or `execute_gate(...)`
- ToolGate `evaluate_sequence(...)`
- WriteQueue task/phase_output persistence.

**Expected runtime behavior:**

- Coding and Testing submissions run lint, types, tests before transition.
- First required failing gate blocks transition.
- Passing gate sequence allows normal FSM transition.
- Gate summary is returned in submit result.
- Gate summary is persisted.

**Implementation notes:**

- Execute validation after schema/judge and before task.current_phase mutation.
- Use normalized ToolExecutor result to build ToolGate `GateResult`.
- Keep working directory and file selection conservative; use repository root/current task context already available.
- Do not add coverage/security/benchmark gates.
- For MVP, `path` means workspace root. Changed-file targeting is post-MVP.

**Failure considerations:**

- Tool timeout is a ToolExecutor failure and may be retryable only if classified transient.
- Real test/lint/type failure is not a transient runtime failure.
- Missing required tool is a validation failure unless explicitly configured otherwise.
- Missing required Mypy is explicit unsupported/failed, not a silent skip.

### Ordered Subtasks

1. Add parameters `tool_executor` and `tool_gate` to `phase_tools.submit_output`.
2. Add helper `_requires_tool_gate(phase)`.
3. Add helper to execute MVP gate sequence through ToolExecutor.
4. Convert ToolExecutor results into ToolGate results.
5. On failed ToolGate result, persist rejected attempt with gate summary.
6. On passed ToolGate result, include gate summary in accepted phase output.
7. Add tests for ToolExecutor payload shape.
8. Add tests for failing lint/type/test blocking transition.
9. Add tests for passing validation allowing transition.

### Runtime Invariants

- No code phase advances without validation.
- Tool validation cannot mutate task phase directly.
- Gate failure keeps current phase unchanged.
- Accepted transition writes checkpoint only after gate pass.
- Gate result mapping is deterministic and auditable.

### Validation Requirements

- Unit tests for validation helper behavior.
- Integration test using fake or controlled adapters for pass/fail.
- Runtime check that Coding cannot reach Review when gate fails.
- Done when failing validation blocks and passing validation advances.

## Task P2-04: Persist Validation Results

**Objective:** Make validation outcomes recoverable and inspectable.

**Subsystem:** Persistence.

**Priority:** P0.

**Dependencies:** P2-03.

**Exact files/modules involved:**

- `sdlc/runtime/tools/phase.py`
- `sdlc/runtime/store_sqlite.py`
- `sdlc/runtime/tools/task.py`
- `sdlc/models.py`
- `sdlc/tests/test_integration.py`

**Exact runtime integration points:**

- Phase history rows.
- Task history.
- `sdlc_get_status`.

**Expected runtime behavior:**

- Accepted Coding/Testing records include validation summary.
- Rejected Coding/Testing records include failed gate, errors, and summary.
- Status/history can explain latest validation failure.

**Implementation notes:**

- Prefer storing validation metadata in existing phase output payloads.
- Avoid schema migrations unless current JSON blob fields cannot represent required data.

**Failure considerations:**

- Validation result persistence failure should fail the submit response rather than lose audit data.

### Ordered Subtasks

1. Define validation summary shape in phase output payload.
2. Include validation summary on accepted phase output.
3. Include validation summary on rejected phase output.
4. Ensure `get_status` surfaces persisted history.
5. Add persistence tests.

### Runtime Invariants

- Persisted state explains accept/reject decision.
- SQLite remains source of truth.
- Checkpoint reflects accepted state only.

### Validation Requirements

- Integration test: validation failure visible after store reload.
- Integration test: validation pass summary visible after accepted transition.
- Done when validation outcomes survive process lifetime.
