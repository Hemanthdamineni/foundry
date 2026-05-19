# Quality and Validation

> Validation plan for proving one operational deterministic feature workflow.
> Tests must prove runtime integration, not module existence.

## 1. Validation Principle

Foundry is not MVP-ready because files exist or unit tests pass. Foundry is
MVP-ready when the authoritative execution path behaves correctly under success,
failure, restart, and recovery.

The path under test is:

```
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> persistence
  -> recovery
```

## 2. Required Test Levels

| Level | Purpose | MVP Required |
|---|---|---|
| Unit | Validate small deterministic helpers | Yes |
| Integration | Validate runtime wiring across modules | Yes |
| E2E feature workflow | Validate one complete operational loop | Yes |
| Crash/restart | Validate checkpoint resume | Yes |
| Advanced replay/regression | Reproduce full historical runs | No |
| Chaos/distributed testing | Multi-process or hostile runtime testing | No |

## 3. MVP Integration Tests

| Test | Proves |
|---|---|
| Feature happy path reaches Done | Single submit pipeline can complete |
| Invalid phase rejected | `submit_output` is phase authority |
| Invalid Review branch rejected | FSM transition authority works |
| Specs missing section rejected | Deterministic schema validation blocks transition |
| Coding gate failure rejected | ToolExecutor + ToolGate are authoritative |
| Coding gate pass accepted | Tool validation allows transition |
| Testing gate failure rejected | Validation remains active late in workflow |
| Rejected attempt persisted | Recovery/status can explain failure |
| Checkpoint created after accepted transition | Persistence follows acceptance |
| Restart resumes latest accepted phase | Checkpoint/SQLite recovery works |
| Explicit resume handles checkpoint | `sdlc_resume_task` is operational |
| SQLite/checkpoint mismatch fails explicitly | No hidden state overwrite |
| Transient tool failure retries within ceiling | Bounded retry works |
| Retry exhaustion stalls or rejects without advancing | No infinite loop |
| Chatting cannot silently skip to Done | Early-completion edge is governed |
| Missing/unhealthy Mypy is explicit | Types gate cannot silently pass |

## 4. Validation Ordering

MVP validation order:

```
1. Phase match
2. Budget/retry ceiling
3. FSM target resolution
4. Deterministic schema validation
5. Optional judge
6. ToolExecutor validation commands for Coding/Testing
7. ToolGate fail-fast decision
8. Persistence/checkpoint on accepted transition
```

Tool validation must run before phase advancement. Checkpointing must run only
after accepted transitions.

## 5. Schema Requirements

| Phase | MVP Rule |
|---|---|
| Chatting | Non-empty clarification |
| Specs | `## Requirements`, `## Scope`, `## Constraints` |
| Planning | `## Implementation Plan`, `## File Changes`, `## Risks` |
| Coding | References modified files and passes tool gates |
| Review | `## Issues Found`, `## Severity`, `## Must Fix` |
| Testing | `## Test Results`, `## Coverage`, `## Failed` and passes tool gates |
| Done | Completion summary |

## 6. Tool Validation Requirements

For MVP, Coding and Testing require:

```
lint -> types -> tests
```

Acceptance:

- lint/type/test commands are executed by ToolExecutor;
- ToolGate evaluates the normalized results;
- first required failure blocks transition;
- result payload is persisted;
- missing required adapter is explicit failure or explicit unsupported skip, not silent pass.
- ToolExecutor payload contains `task_id`, `phase`, workspace-root `path`, and
  `timeout_s`.
- ToolExecutor results map deterministically into ToolGate pass/fail,
  transient, unsupported, or terminal adapter failure.

## 7. Recovery Requirements

Recovery tests must prove:

- accepted transition writes SQLite task update and latest checkpoint;
- rejected transition does not overwrite current phase;
- process restart does not lose accepted history;
- explicit `sdlc_resume_task(task_id)` can restore or reconcile latest checkpoint
  when recovery is invoked;
- disagreement between SQLite and checkpoint is reported explicitly.

Versioned replay, rollback, and restore points are post-MVP and are not required
for this validation plan.

## 8. Reliability Targets

| Target | MVP Requirement |
|---|---|
| No hidden phase advancement | Every advancement goes through `submit_output` |
| No unvalidated code acceptance | Coding/Testing blocked without passing gate |
| No infinite retry | Retry ceiling enforced and persisted |
| No lost accepted phase | Latest accepted state recoverable after restart |
| No fake workflow support | Unsupported modes rejected or clearly deferred |
| No silent early completion | `Chatting -> Done` is disabled or explicitly governed |

## 9. Current Test Gaps

Existing tests prove parts of the MCP server and individual modules. They do not
yet prove the corrected MVP because they do not require:

- ToolExecutor in the submit path;
- ToolGate blocking Coding/Testing;
- persisted rejected attempts;
- latest checkpoint restore/resume;
- bounded retry state after restart;
- feature-only mode truth.

These gaps are P0/P1 until closed.

## 10. Production Readiness Gates

Production readiness is after MVP and requires:

- stage-level tracing for submit pipeline;
- healthcheck reporting for required adapters;
- configurable judge fail-open/fail-closed policy;
- persistent recovery state;
- backup/compaction strategy for SQLite/checkpoints;
- security review of shell/tool execution.

Dashboards, advanced memory, multi-agent coordination, replay analytics, and
enterprise integrations do not affect MVP acceptance.
