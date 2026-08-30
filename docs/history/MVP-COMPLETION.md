# MVP Completion Gates

## Purpose

This file defines the evidence required to call Foundry MVP complete. It is not
a roadmap and not an architecture document. It is a release gate for one
operational deterministic feature workflow.

## MVP Scope

MVP includes:

- feature workflow only;
- one authoritative FSM;
- one submit pipeline;
- one ToolExecutor path;
- one ToolGate path;
- SQLite task authority;
- latest checkpoint path;
- bounded retries;
- latest-checkpoint recovery/resume;
- deterministic integration tests.

MVP excludes:

- rollback;
- advanced replay;
- dashboards;
- advanced memory;
- team coordination;
- autonomous controllers;
- distributed execution;
- non-feature workflows;
- enterprise integrations.

## Completion Checklist

| Gate | Evidence Required | Status |
|---|---|---|
| Feature-only workflow enforced | Test showing `feature` accepted and non-feature rejected/unsupported | **Passed** |
| Submit pipeline staged | Tests for phase mismatch, invalid status, invalid target, schema failure | **Passed** |
| Schema validation explicit | Test proving schema failure skips judge and does not advance | **Passed** |
| ToolExecutor wired | Runtime context initializes executor and validation uses it | **Passed** |
| ToolExecutor payload stable | Adapter calls use `task_id`, `phase`, workspace-root `path`, `timeout_s` | **Passed** |
| ToolGate wired | Coding/Testing fail when gate fails and advance when gate passes | **Passed** |
| ToolGate mapping stable | ToolExecutor results map to pass/fail/transient/unsupported/terminal outcomes | **Passed** |
| Mypy policy explicit | Missing/unhealthy Mypy fails or returns unsupported; never silent pass | **Passed** |
| Chatting shortcut governed | `Chatting -> Done` rejected or explicitly early-completed with persisted reason | **Passed** |
| Rejected attempts persisted | Status/history show rejected phase attempts after reload | **Passed** |
| Checkpoint write correct | Accepted transition writes latest checkpoint | **Passed** |
| Resume works | Restart test and `sdlc_resume_task` resume/reconcile latest accepted phase | **Passed** |
| Retry bounded | Transient retry succeeds within ceiling and exhausts deterministically | **Passed** |
| SQLite authority preserved | Task phase/history/status remain consistent across runtime paths | **Passed** |
| Deferred systems absent | MVP path does not depend on rollback, replay, memory, dashboard, teams | **Passed** |

### Evidence Details

**Feature-only workflow enforced** — `app.py:342-347`: `if mode != "feature"` raises
`ValueError` with clear message. Tests: `TestModeEnforcement.test_feature_mode_accepted`,
`test_bugfix_mode_rejected`, `test_refactor_mode_rejected` in `test_integration.py`.

**Submit pipeline staged** — `phase.py:283-547`. Pipeline stages in order: load from
SQLite → reject missing → reject terminal status → reject phase mismatch → guard
Chatting->Done → budget check → FSM resolution → schema validation → judge → ToolGate
→ phase mutation + checkpoint. Tests: `TestTaskLifecycle` (missing/done/cancelled/stalled
rejection, phase mismatch, invalid target, Chatting->Done guard).

**Schema validation explicit** — `phase.py:347` calls `validate_phase_output()` after
FSM resolution (line 343) and before judge evaluation (line 380). Schema failure returns
early at line 363, skipping judge, debate, and gates. Tests: `TestSchemaValidation`
(5 tests including `test_judge_skipped_on_schema_failure`).

**ToolExecutor wired** — `app.py:245-248`: `ToolExecutor(default_timeout_s=30.0, max_retries=1)`
instantiated during lifespan. RuffAdapter, MypyAdapter, PytestAdapter registered. Passed
to `submit_output` via app context. Test: `TestToolGates.test_tool_executor_registration`.

**ToolExecutor payload stable** — `_execute_gates` at `phase.py:214-219` standardizes
payload as `{"task_id": task_id, "phase": phase, "path": workspace_path, "timeout_s": 30}`.
Test: `TestToolGates.test_adapter_payload_shape`.

**ToolGate wired** — `app.py:258-266`: `ToolGate(gate_order=[("lint", "ruff"), ("types", "mypy"), ("tests", "pytest")])`.
Phase exceptions: Coding skips tests, Testing skips lint+types, non-code phases skip all.
`_requires_tool_gate()` at `phase.py:185-186` returns true only for Coding/Testing.
Tests: `TestGateFailureE2E` (2 tests), `TestToolGates` (multiple tests for pass/fail).

**ToolGate mapping stable** — `_map_to_gate_result` at `phase.py:189-203` maps
ToolExecutor results to GateResult with `failure_class` propagation. Missing adapter
returns `failure_class="not_found"` (tool_executor.py:84-91). Timeout returns
`failure_class="timeout"` (tool_executor.py:140-147). Real failures return
`failure_class="permanent"` via `_normalize` (tool_executor.py:210-231).
Test: `TestToolGates.test_result_mapping`.

**Mypy policy explicit** — Missing Mypy adapter returns `failure_class="not_found"`
with explicit error. Types gate fails, never passes silently.
Test: `TestToolGates.test_missing_mypy_returns_failed_result`.

**Chatting shortcut governed** — `phase.py:327-332`: `if phase == "Chatting" and next_phase == "Done"`
returns `accepted: false` with explicit error. Test: `TestTaskLifecycle.test_chatting_to_done_guarded`.

**Rejected attempts persisted** — Schema rejection persisted at `phase.py:349-362`
(PhaseRecord with REJECTED status). Judge rejection at lines 396-413. Gate rejection
at lines 489-506. All persist via write_queue. `get_status` exposes history.
Tests: `TestSchemaValidation.test_invalid_specs_visible_after_status`,
`test_rejected_attempt_survives_reload`.

**Checkpoint write correct** — `phase.py:531-547`: after accepted transition,
`Checkpoint(task_id, phase=resolved, history=..., iteration_count=...)` written
via `checkpoint_mgr.save()`. Tests: `TestFeatureWorkflowE2E` verifies checkpoint
file exists per transition with correct phase and history length.

**Resume works** — `resume_task()` at `task.py:113-199`. Missing task restore from
checkpoint, phase mismatch detection, history length mismatch detection, corrupt
checkpoint handling. MCP handler `sdlc_resume_task` registered in `app.py`.
Tests: `TestResumeTask` (5 tests), `TestRestartResume` (2 tests).

**Retry bounded** — Retry loop at `phase.py:433-512`. Pre-checks `task.retry_count`
against `MAX_GATE_RETRY_CEILING=3`. Transient/timeout failures increment retry_count,
persist, apply exponential backoff, retry. Permanent failures return immediately.
Ceiling exhaustion marks task STALLED. Tests: `TestRecoveryRetryE2E` (3 tests),
`TestBoundedTransientRetry` (2 tests).

**SQLite authority preserved** — All state reads prefer SQLite: `store.get_task()`
at `phase.py:301`, `task.py:56`. Checkpoints are secondary — used only for recovery
(`resume_task` at `task.py:113`). Checkpoint mismatch causes explicit failure, not
silent fallback. No code path mutates state without SQLite persistence via write queue.
Tests: `TestRestartResume.test_restart_resume_checkpoint_sqlite_consistency`.

**Deferred systems absent from MVP path** — No rollback, replay, dashboard, advanced
memory, or team coordination code exists in `sdlc/runtime/`, `sdlc/engine/`, or
`sdlc/models.py`. All explicitly marked "deferred" in planning docs.
`planning/MASTER-ROADMAP.md` confirms these are post-MVP.

## Required Test Evidence

Target tests may live in existing test files or new focused files under
`sdlc/tests/`.

Required scenarios:

| # | Scenario | Test | Status |
|---|---|---|---|
| 1 | Create feature task and complete all phases to Done | `TestFeatureWorkflowE2E.test_feature_workflow_reaches_done` | **Passed** |
| 2 | Submit invalid phase and verify rejection | `TestTaskLifecycle.test_phase_mismatch_rejection` | **Passed** |
| 3 | Submit invalid Review target and verify rejection | `TestTaskLifecycle.test_invalid_target_rejection` | **Passed** |
| 4 | Submit schema-invalid Specs output and verify no advancement | `TestSchemaValidation.test_invalid_specs_rejected` | **Passed** |
| 5 | Submit Coding output with failing validation and verify no advancement | `TestGateFailureE2E.test_coding_gate_failure_preserves_phase_and_no_checkpoint` | **Passed** |
| 6 | Submit Coding output with passing validation and verify advancement | `TestFeatureWorkflowE2E.test_feature_workflow_reaches_done` (Coding step) | **Passed** |
| 7 | Submit Testing output with failing validation and verify no advancement | `TestGateFailureE2E.test_testing_gate_failure_preserves_phase_and_no_checkpoint` | **Passed** |
| 8 | Persist rejected attempt and verify via status/history after reload | `TestSchemaValidation.test_rejected_attempt_survives_reload` | **Passed** |
| 9 | Restart server after accepted checkpoint and verify resume | `TestRestartResume.test_restart_resume_preserves_phase_and_history` | **Passed** |
| 10 | Invoke `sdlc_resume_task(task_id)` and verify latest-checkpoint reconciliation | `TestRestartResume.test_restart_resume_checkpoint_sqlite_consistency` | **Passed** |
| 11 | Simulate transient validation failure and verify bounded retry | `TestRecoveryRetryE2E.test_transient_failure_then_success` | **Passed** |
| 12 | Simulate retry exhaustion and verify non-advancing terminal/stalled outcome | `TestRecoveryRetryE2E.test_transient_exhaustion_stalls` | **Passed** |
| 13 | Simulate missing/unhealthy Mypy and verify explicit unsupported/failed gate | `TestToolGates.test_missing_mypy_returns_failed_result` | **Passed** |
| 14 | Attempt `Chatting -> Done` on normal feature task and verify no silent skip | `TestTaskLifecycle.test_chatting_to_done_guarded` | **Passed** |

## Runtime Invariants at Completion

- `submit_output` is the only phase-transition authority.
- SQLite is task/history/status authority.
- Checkpoint is a recovery snapshot, not normal-state authority.
- ToolExecutor owns validation command execution.
- ToolGate owns validation accept/reject decision for code phases.
- Coding and Testing cannot advance without passing required gates.
- Rejections do not write accepted checkpoints.
- Retry ceilings are hard.
- Non-feature workflows are not silently accepted.
- `Chatting -> Done` is disabled or explicitly governed.
- Missing required adapters cannot silently pass.

## Completion Decision

MVP is complete only when all checklist items are `Passed` with linked test
evidence or command output. Partial implementation is not MVP completion.

## Test Results

```
$ pytest sdlc/tests/ -x
421 passed in 184.82s (0:03:04)
0 failures, 0 errors
```

All 14 required test scenarios covered. All 15 completion gates passed.
All 11 runtime invariants verified.
