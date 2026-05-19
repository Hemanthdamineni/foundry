# Foundry Implementation TODO

> Authoritative execution checklist for one operational deterministic feature
> workflow. This file expands `planning/execution/PHASE-0.md` through
> `PHASE-4.md` into concrete implementation TODOs.

Completion rule: do not mark a task done because a file exists. Mark it done
only when the runtime initializes it, the authoritative path calls it, it can
affect accept/reject behavior where relevant, required state persists, and tests
cover success and failure behavior.

Authoritative runtime path:

```text
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> SQLite persistence
  -> sdlc_resume_task / recovery
```

MVP excludes rollback, advanced replay, dashboards, advanced memory,
multi-agent/team coordination, autonomous controllers, distributed execution,
non-feature workflows, and enterprise integrations.

## Phase 0: Baseline Enforcement

Goal: freeze the corrected MVP boundary before runtime code changes begin.

### P0-01: Establish Execution Plan Index

- [x] Confirm `planning/execution/PHASE-0.md` exists and defines baseline enforcement.
- [x] Confirm `planning/execution/PHASE-1.md` exists and defines the single submit pipeline.
- [x] Confirm `planning/execution/PHASE-2.md` exists and defines ToolExecutor/ToolGate enforcement.
- [x] Confirm `planning/execution/PHASE-3.md` exists and defines checkpoint restore and bounded recovery.
- [x] Confirm `planning/execution/PHASE-4.md` exists and defines MVP end-to-end proof.
- [x] Confirm `planning/execution/MVP-COMPLETION.md` exists and defines release evidence.
- [x] Verify every phase task references concrete files/modules.
- [x] Verify every implementation task has runtime integration points.
- [x] Verify no phase depends on rollback, replay, dashboard, advanced memory, or team coordination.
- [x] Verify execution planning points back to `planning/MASTER-ROADMAP.md`.

Done when phase files exist, match corrected MVP scope, and do not introduce new runtime layers.

All planning files verified: `planning/execution/PHASE-0.md` through `PHASE-4.md`,
`MVP-COMPLETION.md`, `MASTER-ROADMAP.md`, `TOOLING-AND-WORKFLOWS-SPEC.md`,
`DEPENDENCY-GRAPH.md`, `QUALITY-AND-VALIDATION.md`, `RUNTIME-SPEC.md`.
Each references concrete modules (`sdlc/runtime/tools/phase.py`, `sdlc/runtime/tool_executor.py`,
`sdlc/runtime/tool_gate.py`, `sdlc/engine/checkpoint.py`, `sdlc/models.py`).
No phase depends on rollback, replay, dashboards, advanced memory, or team coordination —
all explicitly deferred in planning docs.

### P0-02: Enforce MVP Vocabulary

- [x] Scan `planning/` for "fully implemented", "all implemented", "production ready", and similar overclaims.
- [x] Replace file-existence completion language with runtime integration status.
- [x] Use only: `file exists`, `scaffolded`, `partially wired`, `operationally integrated`, `production-ready`, `deferred`, `non-operational concept`.
- [x] Confirm `planning/MASTER-ROADMAP.md` does not mark ToolExecutor or ToolGate operational until submit path wiring exists.
- [x] Confirm rollback, replay, dashboards, memory, and team coordination are explicitly deferred.
- [x] Confirm production-ready is not used as an MVP status.

Done when planning status language cannot be mistaken for implementation completion.

Planning docs use runtime integration language ("operationally integrated", "deferred",
"scaffolded"). `MASTER-ROADMAP.md` marks ToolExecutor/ToolGate as deferred until submit
path wiring. Rollback, replay, dashboards, memory, team coordination explicitly deferred.
No "production-ready" claims for MVP status.

### P0-03: Lock Feature-Only Scope

- [x] Confirm `feature` is the only MVP workflow in `planning/TOOLING-AND-WORKFLOWS-SPEC.md`.
- [x] Confirm Phase 1 includes explicit non-feature mode rejection or unsupported response.
- [x] Confirm no Phase 0-4 task requires bugfix/refactor/research/docs graph execution.
- [x] Confirm workflow-specific budgets are deferred.
- [x] Confirm workflow-specific model routing is deferred.
- [x] Confirm `sdlc/graphs/feature.yaml` remains the only executable MVP graph.

Done when implementation cannot accidentally treat graph templates as supported workflows.

`TOOLING-AND-WORKFLOWS-SPEC.md` confirms `feature` as only MVP workflow.
`app.py:342` enforces `mode != "feature"` rejection with clear error message.
No Phase 0-4 task requires non-feature graph execution. Workflow-specific budgets
and model routing explicitly deferred. `sdlc/graphs/feature.yaml` is the only
executable MVP graph.

## Phase 1: Single Submit Pipeline

Goal: make `sdlc_submit_output` the only phase-transition authority.

### P1-01: Stage the Submit Pipeline

- [x] Read current `submit_output` implementation in `sdlc/runtime/tools/phase.py`.
- [x] Identify current load, validation, judge, transition, persistence, and checkpoint boundaries.
- [x] Add or clarify private helper functions only where they make stage ordering obvious.
- [x] Load task from SQLite before any validation or mutation.
- [x] Reject missing task with `accepted: false`.
- [x] Reject `DONE`, `CANCELLED`, and `STALLED` tasks before validation.
- [x] Reject submitted phase mismatch before budget, judge, tools, or mutation.
- [x] Check minimal budget/retry constraints before acceptance.
- [x] Resolve candidate transition through `OrchestratorFSM.submit(...)`.
- [x] Reject invalid transition target before state mutation.
- [x] Reject normal feature-task `Chatting -> Done` unless explicit early-completion policy records the reason.
- [x] Move all `task.current_phase` mutation after validation success.
- [x] Ensure every rejection response returns `accepted: false`.
- [x] Ensure rejection paths do not write accepted checkpoints.
- [x] Add tests for missing task rejection.
- [x] Add tests for done/cancelled/stalled task rejection.
- [x] Add tests for phase mismatch rejection.
- [x] Add tests for invalid target rejection.
- [x] Add tests for guarded `Chatting -> Done`.
- [x] Verify existing happy path still advances when valid.

Done when no accepted transition can happen before the staged acceptance gates pass.

Implemented in `sdlc/runtime/tools/phase.py:283-611`. Pipeline stages in order:
(1) Load task from SQLite via `store.get_task(task_id)` — line 301;
(2) Reject missing task — line 302-303;
(3) Reject DONE/CANCELLED/STALLED — line 306-310;
(4) Reject phase mismatch — line 320-325;
(5) Guard Chatting->Done — line 327-332;
(6) Budget check — line 334-340;
(7) FSM target resolution via `orchestrator.submit(phase, target=next_phase)` — line 343;
(8) Schema validation — line 347;
(9) Judge evaluation — line 380-424;
(10) ToolGate execution — line 430-512;
(11) Phase mutation + checkpoint write — line 514-547.
All rejection paths return `accepted: false`. Rejection paths do not write checkpoints.
Tests: `TestTaskLifecycle.test_missing_task_rejection`, `test_done_task_rejection`,
`test_cancelled_task_rejection`, `test_stalled_task_rejection`, `test_phase_mismatch_rejection`,
`test_chatting_to_done_guarded` in `test_integration.py`.

### P1-02: Make Schema Validation Explicit

- [x] Import or call existing `validate_phase_output(...)` in `sdlc/runtime/tools/phase.py`.
- [x] Run schema validation after FSM target resolution.
- [x] Run schema validation before `JudgeEngine.evaluate(...)`.
- [x] Build a structured schema failure payload containing phase, reason, and violations.
- [x] Persist schema rejection as a rejected attempt.
- [x] Ensure judge does not run when schema validation fails.
- [x] Ensure debate does not run when schema validation fails.
- [x] Ensure tool gates do not run when schema validation fails.
- [x] Add tests for invalid Specs output.
- [x] Add tests for invalid Planning output.
- [x] Add tests for invalid Review output.
- [x] Add tests for invalid Testing output.
- [x] Add test proving judge is skipped on schema failure.

Done when deterministic schema failure never advances phase and never enters probabilistic validation.

`validate_phase_output` imported at `phase.py:13`, called at line 347 after FSM resolution
(line 343) and before judge evaluation (line 380). Schema violations return structured
payload with `phase`, `violations` (section + message + details) — lines 363-374.
Rejected attempt persisted as `PhaseRecord(status=PhaseStatus.REJECTED)` — lines 349-362.
Judge/debate/gates all skipped on schema failure (early return at line 363).
Tests: `TestSchemaValidation.test_invalid_specs_rejected`, `test_invalid_planning_rejected`,
`test_invalid_review_rejected`, `test_invalid_testing_rejected`, `test_judge_skipped_on_schema_failure`
in `test_integration.py`.

### P1-03: Persist Rejected Attempts Consistently

- [x] Define one helper for appending rejected phase records.
- [x] Use existing `PhaseRecord` unless current model cannot represent required data.
- [x] Record rejected phase name.
- [x] Record rejection status.
- [x] Record rejection reason/error.
- [x] Record validation metadata where available.
- [x] Record iteration/retry metadata where available.
- [x] Persist task update after appending rejected record.
- [x] Persist phase output with rejected status if existing storage supports it.
- [x] Keep `task.current_phase` unchanged after rejection.
- [x] Ensure failed rejected-attempt persistence returns an explicit write failure.
- [x] Ensure failed rejected-attempt persistence does not partially advance task.
- [x] Verify `sdlc_get_status` exposes latest rejection from persisted history.
- [x] Add integration test: invalid Specs is visible after status call.
- [x] Add integration test: rejected attempt survives store reload.

Done when rejected attempts are inspectable runtime facts, not invisible failures.

Schema rejection persisted at `phase.py:349-362` (PhaseRecord with REJECTED status,
phase name, error="schema_validation_failed", iteration_count). Judge rejection
persisted at lines 396-413. Gate rejection persisted at lines 489-506. All paths
persist via `write_queue.enqueue(WriteOp(target="task", action="update", ...))`
then `write_queue.flush()`. `task.current_phase` unchanged after all rejection paths.
`get_status` exposes history with rejected records (line 62-65 in `task.py`).
Tests: `test_invalid_specs_visible_after_status`, `test_rejected_attempt_survives_reload`
in `test_integration.py` (TestSchemaValidation class).

### P1-04: Enforce Feature-Only Mode Truth

- [x] Locate `sdlc_create_task` mode handling in `sdlc/runtime/tools/task.py` and app wiring.
- [x] Set supported MVP modes to `{"feature"}`.
- [x] Return a clear unsupported-mode error for non-feature modes.
- [x] Ensure unsupported-mode errors preserve MCP response shape.
- [x] Do not delete existing graph template files.
- [x] Do not wire additional graph selection in MVP.
- [x] Update tests that expected non-feature modes to be accepted.
- [x] Add integration test for `mode="feature"` accepted.
- [x] Add integration test for `mode="bugfix"` rejected/unsupported.
- [x] Keep graph template tests scoped to template existence, not workflow support.

Done when non-feature modes cannot silently run the feature graph.

Mode enforcement at `app.py:342-347`: `if mode != "feature"` raises `ValueError` with
clear message listing deferred modes. Error propagates through MCP as `isError` response
with structured text. Graph template files preserved. No additional graph selection wired.
Tests: `TestModeEnforcement.test_feature_mode_accepted`, `test_bugfix_mode_rejected`,
`test_refactor_mode_rejected` in `test_integration.py`.

## Phase 2: ToolExecutor and ToolGate Enforcement

Goal: make Coding and Testing transitions depend on governed lint/type/test validation.

### P2-01: Initialize MVP ToolExecutor

- [x] Add `tool_executor` to `SDLCAppContext`.
- [x] Instantiate one `ToolExecutor` during app lifespan.
- [x] Instantiate Ruff adapter.
- [x] Instantiate Mypy adapter.
- [x] Instantiate Pytest adapter.
- [x] Register Ruff, Mypy, and Pytest with ToolExecutor.
- [x] Do not register coverage/security/benchmark gates for MVP.
- [x] Pass ToolExecutor into `phase_tools.submit_output(...)`.
- [x] Standardize adapter payload as `{"task_id": task_id, "phase": phase, "path": workspace_path, "timeout_s": 30}`.
- [x] Treat `path` as workspace root for MVP.
- [x] Expose adapter health status without silently passing required validation.
- [x] Ensure missing/unhealthy Mypy returns explicit unsupported/failed result.
- [x] Ensure required adapter absence does not crash startup unless explicitly configured.
- [x] Add unit test for ToolExecutor registration.
- [x] Add integration test that app context contains ToolExecutor.
- [x] Add test for adapter payload shape.
- [x] Add test for missing/unhealthy Mypy behavior.

Done when submit flow can receive ToolExecutor and adapter availability cannot silently pass validation.

Initialized in `app.py:245-248`: `ToolExecutor(default_timeout_s=30.0, max_retries=1)`,
`RuffAdapter()`, `MypyAdapter()`, `PytestAdapter()` registered. Health checks run at
line 250-256 with warnings logged for failures. Passed to `submit_output` via app
context wiring. Adapter payload standardized in `_execute_gates` at `phase.py:214-219`.
No coverage/security/benchmark gates registered. Tests: `test_tool_executor_registration`,
`test_adapter_payload_shape`, `test_missing_mypy_returns_failed_result` in
`test_integration.py` (TestToolGates class).

### P2-02: Initialize MVP ToolGate

- [x] Add `tool_gate` to `SDLCAppContext`.
- [x] Instantiate one ToolGate during app lifespan.
- [x] Configure gate order exactly as `lint -> types -> tests`.
- [x] Define helper for phases requiring ToolGate.
- [x] Return true only for Coding and Testing in MVP gate helper.
- [x] Pass ToolGate into `phase_tools.submit_output(...)`.
- [x] Add minimal capability/name mapping if adapter capability names differ from gate names.
- [x] Add mapper from ToolExecutor result to ToolGate result.
- [x] Map successful tool result to gate pass.
- [x] Map nonzero exit or adapter failure to gate failure.
- [x] Map timeout/process execution error to transient execution failure.
- [x] Map missing MVP adapter to failed/unsupported gate result.
- [x] Map malformed adapter output to terminal adapter contract failure.
- [x] Ensure missing Mypy cannot become a passing `types` gate.
- [x] Add unit test for deterministic gate order.
- [x] Add unit test for result mapping.
- [x] Add integration test that non-code phases do not require ToolGate.

Done when ToolGate is initialized, deterministic, and available to submit flow.

Initialized in `app.py:258-266`: `ToolGate(gate_order=[("lint", "ruff"), ("types", "mypy"), ("tests", "pytest")])`.
Phase exceptions configured: Coding skips tests, Testing skips lint+types, non-code phases
skip all gates. `_requires_tool_gate(phase)` at `phase.py:185-186` returns true only for
Coding/Testing. `_map_to_gate_result` at `phase.py:189-203` maps ToolExecutor results to
GateResult with failure_class propagation. Missing adapter returns `failure_class="not_found"`
(tool_executor.py:84-91). Tests: `test_deterministic_gate_order`, `test_result_mapping`,
`test_non_code_phases_no_gates` in `test_integration.py` (TestToolGates class).

### P2-03: Execute Validation Before Coding/Testing Advancement

- [x] Add `tool_executor` parameter to `phase_tools.submit_output(...)`.
- [x] Add `tool_gate` parameter to `phase_tools.submit_output(...)`.
- [x] Execute ToolExecutor validation after schema/judge stages.
- [x] Execute ToolExecutor validation before `task.current_phase` mutation.
- [x] Use MVP gate sequence for Coding submissions.
- [x] Use MVP gate sequence for Testing submissions.
- [x] Convert ToolExecutor results into ToolGate inputs.
- [x] Evaluate ToolGate fail-fast in deterministic order.
- [x] Return gate summary in submit response.
- [x] Persist rejected attempt with gate summary on failed gate.
- [x] Persist accepted phase output with gate summary on passed gate.
- [x] Keep task in Coding when Coding gate fails.
- [x] Keep task in Testing when Testing gate fails.
- [x] Ensure Tool timeout is classified as transient only when appropriate.
- [x] Ensure real lint/type/test failure is not classified as transient.
- [x] Ensure missing Mypy is explicit unsupported/failed.
- [x] Add tests for failing lint blocking transition.
- [x] Add tests for failing types blocking transition.
- [x] Add tests for failing tests blocking transition.
- [x] Add tests for passing validation allowing Coding advancement.
- [x] Add tests for passing validation allowing Testing advancement.

Done when Coding and Testing cannot advance without passing required gates.

Gate execution at `phase.py:430-512` runs after schema validation (line 347) and judge
evaluation (line 380), before phase mutation (line 522). `_execute_gates` at lines 206-238
runs gates in deterministic order with fail-fast on first failure. Gate summary returned
in response at line 510-511. Rejected attempt persisted at lines 489-506. Accepted output
persisted at lines 514-531. Task stays in current phase on gate failure (early return at
line 507-512). Timeout classified as `failure_class="timeout"` (tool_executor.py:140-147).
Real lint/type/test failures classified as `failure_class="permanent"` via `_normalize`
(tool_executor.py:210-231). Missing adapter returns `failure_class="not_found"`.
Tests: `test_failing_lint_blocks_transition`, `test_failing_types_blocks_transition`,
`test_failing_tests_blocks_transition`, `test_passing_validation_allows_coding`,
`test_passing_validation_allows_testing` in `test_integration.py` (TestToolGates class).

### P2-04: Persist Validation Results

- [x] Define validation summary shape in existing phase output payloads.
- [x] Include gate order in validation summary.
- [x] Include each gate name and result.
- [x] Include failure reason/error for rejected gates.
- [x] Include unsupported required adapter result when applicable.
- [x] Include transient execution failure metadata when applicable.
- [x] Persist validation summary on accepted Coding/Testing output.
- [x] Persist validation summary on rejected Coding/Testing output.
- [x] Ensure `sdlc_get_status` can expose latest validation failure from history.
- [x] Ensure validation result persistence failure fails submit response explicitly.
- [x] Avoid schema migration unless current JSON fields cannot represent the summary.
- [x] Add integration test: validation failure visible after store reload.
- [x] Add integration test: validation pass summary visible after accepted transition.

Done when validation decisions survive process lifetime and explain accept/reject outcomes.

Gate summary shape: `{"passed": bool, "passed_gates": [...], "failed_at": str, "gates": [...]}`
returned in submit response (line 510-511). Each gate includes name, tool, passed, errors,
failure_class. Rejected gate summary persisted in PhaseRecord error field (line 493).
Accepted gate summary available via `get_status` history. No schema migration needed —
existing JSON fields represent the summary. Tests: `test_validation_failure_visible_after_reload`,
`test_validation_pass_summary_visible_after_accepted` in `test_integration.py`
(TestToolGates class).

## Phase 3: Checkpoint Restore and Bounded Recovery

Goal: make accepted progress recoverable and transient failures bounded.

### P3-01: Define Latest Checkpoint Resume Path

- [x] Document current checkpoint write shape in test or code comments.
- [x] Add helper to load latest checkpoint for task.
- [x] Add helper to compare checkpoint phase with SQLite task phase.
- [x] Add helper to compare checkpoint history with SQLite task history.
- [x] Add minimal MCP/runtime handler `sdlc_resume_task(task_id)` if absent.
- [x] Ensure normal status reads prefer SQLite.
- [x] Ensure normal status reads do not silently mutate state.
- [x] Implement compatible latest-checkpoint resume path.
- [x] Implement missing-task restore path when latest checkpoint is available and safe.
- [x] Return explicit not-recoverable result when checkpoint is missing.
- [x] Return explicit recovery failure when checkpoint is corrupt.
- [x] Return explicit mismatch result when SQLite and checkpoint diverge.
- [x] Do not silently overwrite SQLite with checkpoint state.
- [x] Do not wire `EnhancedCheckpointManager` unless base latest restore is impossible.
- [x] Do not implement versioned checkpoint chains.
- [x] Add unit tests for checkpoint/task comparison helper.
- [x] Add integration test for restart with same phase/history.
- [x] Add integration test invoking `sdlc_resume_task(task_id)`.
- [x] Add integration test for missing checkpoint.
- [x] Add integration test for corrupt checkpoint.
- [x] Add integration test for SQLite/checkpoint mismatch.

Done when latest-checkpoint resume is explicit, bounded, and cannot silently corrupt state.

All items implemented and verified: `resume_task()` in `sdlc/runtime/tools/task.py:113-199`,
`CheckpointManager.restore()` integration, `sdlc_resume_task` MCP handler in
`sdlc/runtime/app.py`, and 5 integration tests in `TestResumeTask` (consistent state,
missing checkpoint, missing task restore, corrupt checkpoint, phase mismatch).

### P3-02: Persist Minimal Retry State

- [x] Decide whether existing `iteration_count` is sufficient for MVP retry ceilings.
- [x] If insufficient, add minimal persisted retry metadata to `Task`.
- [x] Store retry count scoped to task and current phase.
- [x] Store last failure reason.
- [x] Store last failure classification.
- [x] Increment retry count only for transient runtime failures.
- [x] Do not increment transient retry count for schema failures.
- [x] Do not increment transient retry count for lint/type/test failures.
- [x] Do not increment transient retry count for missing required adapters.
- [x] Reset phase-scoped retry state after accepted transition.
- [x] Persist retry state through SQLite/write queue.
- [x] Add model serialization/deserialization tests if fields are added.
- [x] Add integration test proving retry count survives store reload.

Done when retry decisions do not depend on in-memory counters.

Implemented: `retry_count`, `last_failure_reason`, `last_failure_type` fields on Task
model. Gate failure path classifies failures via `failure_class` (transient/timeout →
increment; permanent/not_found → no increment). Accepted transitions reset all retry
metadata. Persisted through SQLite JSON blob. Tests: `test_task_retry_metadata_defaults`,
`test_task_retry_metadata_roundtrip` in `test_foundation.py`.

### P3-03: Implement Bounded Transient Retry

- [x] Define failure classes: transient, gate failure, unsupported dependency, terminal contract/recovery failure.
- [x] Classify ToolExecutor timeout as transient where appropriate.
- [x] Classify adapter process interruption as transient where appropriate.
- [x] Classify temporary SQLite/write queue failure as transient only when transaction did not commit.
- [x] Classify schema failure as terminal for current submission.
- [x] Classify phase mismatch as terminal for current submission.
- [x] Classify lint/type/test failure as gate failure, not transient.
- [x] Classify missing Mypy or MVP adapter as unsupported dependency, not transient.
- [x] Classify checkpoint corruption as terminal recovery failure.
- [x] Classify SQLite/checkpoint mismatch as terminal recovery failure.
- [x] Add retry loop around transient validation execution only.
- [x] Persist retry count before retry or after failed attempt.
- [x] Enforce hard retry ceiling.
- [x] Return non-advancing terminal/stalled result on exhaustion.
- [x] Ensure retry never bypasses ToolGate.
- [x] Ensure retry never advances phase without accepted validation.
- [x] Add unit tests for classification mapping.
- [x] Add integration test for transient ToolExecutor failure followed by success.
- [x] Add integration test for transient failure exhaustion.
- [x] Add integration test for permanent gate failure not being retried as transient.
- [x] Add integration test for missing Mypy not being retried as transient.
- [x] Add integration test for checkpoint mismatch not being retried as transient.

Done when transient and deterministic failures behave differently and retry cannot loop forever.

Implemented: Bounded transient retry loop in `submit_output` gate execution path. Pre-checks `task.retry_count` against `MAX_GATE_RETRY_CEILING=3` before running gates. Transient/timeout gate failures increment `retry_count`, persist task state, apply exponential backoff (2^attempt up to 30s), and retry. Permanent/gate failures (lint/type/test) return immediately without incrementing `retry_count`. When retry ceiling is reached, task is marked `STALLED` with explicit `task_stalled` response field and `"Transient retry ceiling exhausted"` error. Retry never bypasses ToolGate. Phase never advances without accepted validation. `get_status` now exposes `retry_count`, `last_failure_reason`, `last_failure_type`. Tests: `test_permanent_gate_failure_does_not_increment_retry`, `test_retry_exhaustion_stalls_task` in `test_integration.py`.

### P3-04: Restart/Resume Integration Test

- [x] Add fixture that starts runtime with stable temporary runtime directory.
- [x] Ensure fixture isolates SQLite database path per test.
- [x] Ensure fixture isolates checkpoint directory per test.
- [x] Create feature task through runtime surface.
- [x] Advance task to a known accepted phase.
- [x] Stop runtime cleanly.
- [x] Restart runtime with same runtime paths.
- [x] Query `sdlc_get_status`.
- [x] Query `sdlc_get_next_action`.
- [x] Assert phase is same latest accepted phase.
- [x] Assert accepted history survived.
- [x] Assert checkpoint and SQLite do not contradict.
- [x] Avoid live Ollama/OpenAI dependency.
- [x] Avoid sleep-heavy nondeterministic test behavior.
- [x] Ensure test passes locally and in CI-like environment.

Done when accepted progress survives process lifetime.

Implemented: `TestRestartResume` in `test_integration.py` with two integration tests.
`test_restart_resume_preserves_phase_and_history` — creates task, advances to Planning
through submit_output, stops server, restarts with same isolated runtime paths (SQLite DB,
checkpoint dir, logs in `tmp_path`), verifies status returns same phase/history, verifies
next action resumes from same phase, verifies continued submission advances correctly,
verifies checkpoint reflects new state after restart+submit.
`test_restart_resume_checkpoint_sqlite_consistency` — advances task to Planning, stops
server, directly compares checkpoint phase and history length against SQLite persistence,
restarts, invokes `sdlc_resume_task`, verifies resume agrees with persisted state.
No live LLM dependency, no sleep-based synchronization, fully isolated per test via
`SDLC_DB_PATH`, `SDLC_CHECKPOINT_DIR`, and `SDLC_LOG_PATH` environment variables.

## Phase 4: MVP End-to-End Feature Workflow

Goal: prove one operational deterministic autonomous execution loop.

### P4-01: Build Deterministic Feature Workflow E2E Test

- [x] Create deterministic feature task.
- [x] Submit valid Chatting output through `submit_output`.
- [x] Submit valid Specs output through `submit_output`.
- [x] Submit valid Planning output through `submit_output`.
- [x] Submit Coding output with passing validation setup.
- [x] Submit Review output targeting Testing.
- [x] Submit Testing output with passing validation setup.
- [x] Assert final task status is `done`.
- [x] Assert phase order is Chatting, Specs, Planning, Coding, Review, Testing, Done.
- [x] Assert every phase transition went through FSM.
- [x] Assert Coding gate summary exists.
- [x] Assert Testing gate summary exists.
- [x] Assert accepted checkpoints exist for accepted transitions.
- [x] Use controlled/fake validation where needed.
- [x] Do not require real autonomous code generation.
- [x] Do not require live LLM availability.

Done when the deterministic feature happy path passes end to end.

Implemented: `TestFeatureWorkflowE2E.test_feature_workflow_reaches_done` in
`test_integration.py`. Full 6-phase feature workflow through the authoritative
submit path with isolated runtime paths. Creates task, submits Chatting → Specs
→ Planning → Coding → Review → Testing → Done. Verifies each transition accepted
with correct next_phase. Verifies checkpoint file written per accepted transition
with correct phase and history length. Verifies Coding gate_summary passed with
lint+types. Verifies Testing gate_summary passed with tests. Verifies final
get_status returns status=done, phase=Done, iteration_count=6. Uses clean
src/tests files for passing gate validation. No live LLM dependency (JudgeError
soft-fallthrough). No real code generation.

### P4-02: Validate ToolGate Failure Path End-to-End

- [x] Advance a task to Coding.
- [x] Configure validation to fail lint, types, or tests.
- [x] Submit Coding output.
- [x] Assert response has `accepted: false`.
- [x] Assert current phase remains Coding.
- [x] Assert rejected attempt is persisted.
- [x] Assert failed gate name is returned.
- [x] Assert no accepted checkpoint is written for the rejected gate.
- [x] Advance or create a task at Testing.
- [x] Configure validation to fail lint, types, or tests.
- [x] Submit Testing output.
- [x] Assert response has `accepted: false`.
- [x] Assert current phase remains Testing.
- [x] Assert rejected attempt is persisted.
- [x] Assert failure is not classified as transient retry.

Done when bad Coding/Testing output cannot advance.

Implemented: `TestGateFailureE2E` in `test_integration.py` with two comprehensive
tests. Both use isolated runtime paths for direct checkpoint inspection.
`test_coding_gate_failure_preserves_phase_and_no_checkpoint`: advances to Coding,
captures checkpoint state (phase=Coding, history=3), submits with bad lint, verifies
`accepted: false`, `failed_at="lint"`, phase remains Coding via `get_next_action`,
rejected attempt in history via `get_status`, checkpoint unchanged (same content,
no additional checkpoint written), `retry_count=0`.
`test_testing_gate_failure_preserves_phase_and_no_checkpoint`: advances to Testing
(Chatting→Specs→Planning→Coding→Review→Testing), submits with failing test, verifies
`failed_at="tests"`, phase remains Testing, rejected attempt persisted, checkpoint
unchanged, `retry_count=0`. Covers both explicit transient-retry exclusion assertions.

### P4-03: Validate Recovery and Retry End-to-End

- [x] Add fake transient executor behavior for tests (`SDLC_INJECT_TRANSIENT_TOOL_FAILURES` env var).
- [x] Configure low retry ceiling for deterministic test (`SDLC_MAX_GATE_RETRY_CEILING` env var).
- [x] Test transient failure followed by success.
- [x] Assert success proceeds only after validation passes.
- [x] Test transient failure exhaustion.
- [x] Assert exhausted result is terminal/stalled and non-advancing.
- [x] Restart runtime after stalled checkpoint.
- [x] Assert stalled state and retry metadata survive process restart.
- [x] Assert retry does not bypass ToolGate.
- [x] Do not test replay.
- [x] Do not test rollback.

Done when recovery path is tested with success, exhaustion, and restart.

Implemented: `TestRecoveryRetryE2E` in `test_integration.py` with three integration
tests. `test_transient_failure_then_success`: sets `SDLC_TOOL_EXECUTOR_MAX_RETRIES=0`
to disable internal ToolExecutor retry, `SDLC_MAX_GATE_RETRY_CEILING=2` to allow
gate-level retry, `SDLC_INJECT_TRANSIENT_TOOL_FAILURES=1` for one simulated transient
failure; verifies the gate-level retry loop recovers and Coding is accepted with
`gate_summary.passed=True`. `test_transient_exhaustion_stalls`: sets ceiling=1 with
inject=2; verifies first transient failure increments retry_count, second hits the
ceiling → `task_stalled=True`, status="stalled". `test_retry_state_survives_restart`:
stalls a task via exhaustion, stops the server, restarts with clean env; verifies
`status="stalled"`, `retry_count=1`, `last_failure_type="retry_exhausted"` all survive
process restart via SQLite persistence. `SDLC_TOOL_EXECUTOR_MAX_RETRIES` env var added
to `ToolExecutor.execute()` to override internal retry count for test determinism.
409 tests pass.

### P4-04: Final MVP Runtime Audit

- [x] Confirm feature-only workflow behavior.
- [x] Confirm non-feature modes are rejected or unsupported.
- [x] Confirm `Chatting -> Done` is disabled or explicitly governed.
- [x] Confirm no rollback dependency in MVP path.
- [x] Confirm no replay dependency in MVP path.
- [x] Confirm no dashboard dependency in MVP path.
- [x] Confirm no advanced memory dependency in MVP path.
- [x] Confirm no team/multi-agent dependency in MVP path.
- [x] Confirm docs match implemented runtime behavior.
- [x] Confirm tests cover feature happy path.
- [x] Confirm tests cover invalid phase/target failure.
- [x] Confirm tests cover schema failure.
- [x] Confirm tests cover ToolGate failure.
- [x] Confirm tests cover missing/unhealthy Mypy.
- [x] Confirm tests cover transient retry.
- [x] Confirm tests cover retry exhaustion.
- [x] Confirm tests cover checkpoint restart/resume.
- [x] Run targeted test suite.
- [x] Run `git diff --check`.
- [x] Update `planning/execution/MVP-COMPLETION.md` with pass/fail evidence.

Done when MVP completion gates are all satisfied with test evidence.

**Feature-only workflow**: `app.py:342` enforces `mode != "feature"` rejection.
**Non-feature modes rejected**: `TestModeEnforcement` tests bugfix/refactor rejection.
**Chatting->Done governed**: `phase.py:327-332` blocks shortcut with explicit error.
**No rollback**: No rollback code in MVP path; `sdlc/runtime/` has no rollback module.
**No replay**: No replay code in MVP path; replay explicitly deferred in planning docs.
**No dashboard**: No dashboard code in MVP path; dashboard explicitly deferred.
**No advanced memory**: No advanced memory in MVP path; memory explicitly deferred.
**No team/multi-agent**: No team coordination in MVP path; explicitly deferred.
**Docs match runtime**: TODO.md updated with evidence; planning docs reflect implementation.

**Test coverage evidence** (421 tests total):
- Feature happy path: `TestFeatureWorkflowE2E.test_feature_workflow_reaches_done`
- Invalid phase/target: `TestTaskLifecycle.test_phase_mismatch_rejection`, `test_invalid_target_rejection`
- Schema failure: `TestSchemaValidation` (5 tests)
- ToolGate failure: `TestGateFailureE2E` (2 tests), `TestToolGates` (multiple tests)
- Missing/unhealthy Mypy: `TestToolGates.test_missing_mypy_returns_failed_result`
- Transient retry: `TestRecoveryRetryE2E.test_transient_failure_then_success`
- Retry exhaustion: `TestRecoveryRetryE2E.test_transient_exhaustion_stalls`
- Checkpoint restart/resume: `TestRestartResume` (2 tests), `TestResumeTask` (5 tests)
- Opencode config validation: `test_opencode_config.py` (12 tests)

All 421 tests pass: `pytest sdlc/tests/` — 0 failures, 0 errors.
`git diff --check` — no whitespace errors.
`planning/execution/MVP-COMPLETION.md` updated with evidence.

## MVP Completion Evidence

- [x] Feature-only workflow enforced.
- [x] Submit pipeline staged.
- [x] Schema validation explicit.
- [x] ToolExecutor wired.
- [x] ToolExecutor payload stable.
- [x] ToolGate wired.
- [x] ToolGate mapping stable.
- [x] Mypy policy explicit.
- [x] `Chatting -> Done` shortcut governed.
- [x] Rejected attempts persisted.
- [x] Checkpoint write correct.
- [x] `sdlc_resume_task` works.
- [x] Retry bounded.
- [x] SQLite authority preserved.
- [x] Deferred systems absent from MVP path.

MVP is complete only when every item above has linked test evidence or command
output in `planning/execution/MVP-COMPLETION.md`.

**SQLite authority preserved**: All state reads prefer SQLite (`store.get_task` at
`phase.py:301`, `task.py:56`). Checkpoints are secondary — used only for recovery
(`resume_task` at `task.py:113`). Checkpoint mismatch causes explicit failure, not
silent fallback. No code path mutates state without SQLite persistence via write queue.

**Deferred systems absent from MVP path**: No rollback, replay, dashboard, advanced memory,
or team coordination code exists in `sdlc/runtime/`, `sdlc/engine/`, or `sdlc/models.py`.
All explicitly marked "deferred" in planning docs. `planning/MASTER-ROADMAP.md` confirms
these are post-MVP.
