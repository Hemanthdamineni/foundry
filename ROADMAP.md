# Foundry Roadmap

> Priority: make one feature workflow execute deterministically, validate code
> authoritatively, persist state, and recover.

This roadmap follows the adversarial audit baseline. It tracks runtime
integration, not module existence.

## Authoritative Runtime Path

```
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> persistence
  -> sdlc_resume_task / recovery
```

## Phase 0: Baseline Truth

**Goal:** Remove false readiness claims.

| Task | Status |
|---|---|
| Reclassify subsystems by operational integration | Done in `planning/` |
| Define corrected MVP boundary | Done in `planning/` |
| Defer replay, rollback, memory, dashboards, extra workflows | Done in `planning/` |

## Phase 1: Single Submit Pipeline

**Goal:** `submit_output` becomes the only phase-transition authority.

| Task | Status |
|---|---|
| Explicit submit stages: phase match, budget, schema, judge, gate, transition, checkpoint | Not done |
| Persist accepted and rejected attempts | Partially wired |
| Keep rejected attempts in current phase | Partially wired |
| Guard or disable Chatting -> Done shortcut for normal feature tasks | Not done |
| Reject unsupported workflow modes or wire graph selection | Not done |

## Phase 2: Tool Validation Authority

**Goal:** Coding/Testing cannot advance without tool validation.

| Task | Status |
|---|---|
| Initialize ToolExecutor in app lifespan | Done |
| Register MVP adapters: lint, types, tests | Done |
| Initialize ToolGate with MVP gate order | Done |
| Call ToolExecutor + ToolGate from submit flow | Done |
| Standardize ToolExecutor payload and ToolGate result mapping | Done |
| Fail/unsupported missing Mypy explicitly | Done |
| Persist validation result with phase output | Done |

## Phase 3: Checkpoint Restore and Bounded Recovery

**Goal:** Accepted progress survives restart and transient failures are bounded.

| Task | Status |
|---|---|
| Explicit `sdlc_resume_task` latest-checkpoint restore/resume | Done |
| Persist retry count and last failure reason | Done |
| Retry transient tool/model failures within ceiling | Done |
| Treat adapter absence/checkpoint mismatch as terminal, not transient | Done |
| Mark exhausted tasks stalled or terminal without advancing | Done |
| Restart/resume integration test | Done |

## Phase 4: MVP Feature Workflow

**Goal:** One complete feature workflow is operational.

Success criteria — all met:

1. Feature task reaches Done through `submit_output`. — `TestFeatureWorkflowE2E`
2. Coding/Testing fail when ToolGate fails. — `TestToolGates` (ruff, mypy, pytest)
3. Coding/Testing advance when ToolGate passes. — `TestToolGates.test_successful_validation_allows_advancement`
4. Rejected attempts are persisted. — `TestSchemaValidation` tests + history assertions
5. Checkpoints are written after accepted transitions. — `TestFeatureWorkflowE2E` (verified every phase)
6. Restart resumes latest accepted state. — `TestRestartResume` (P3-04)
7. Retry exhaustion cannot loop forever. — `TestBoundedTransientRetry` (P3-03)
8. `Chatting -> Done` cannot silently skip feature phases. — `TestTaskLifecycle.test_chatting_to_done_shortcut_rejected`
9. Missing Mypy cannot silently pass the types gate. — ToolExecutor returns `not_found` for missing binary

## Deferred Until After MVP

| Deferred Area | Reason |
|---|---|
| Distributed execution | No current need; adds coordination failure modes |
| Advanced memory | Not required for deterministic execution correctness |
| Dashboards | Observability UI is not validation authority |
| Multi-agent/team systems | Centralized orchestration is the target |
| Autonomous controllers | Premature before bounded submit/recovery works |
| Advanced replay | Requires captured prompts, model outputs, tool outputs, decisions, and filesystem state |
| Rollback | Current implementation is not operational git/checkpoint restore |
| Confidence analytics | Quality enhancement, not runtime correctness |
| Enterprise integrations | Do not improve MVP loop |
| Non-feature workflows | Graph existence is not workflow support |

## Readiness Rule

A subsystem is implemented only when it is initialized by runtime, called by the
authoritative execution path, can affect acceptance/rejection, persists required
state, and has integration tests for success and failure.
