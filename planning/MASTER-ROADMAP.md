# Master Roadmap

> Authoritative runtime integration roadmap. This document tracks operational
> readiness, not module existence.

## Project Status Summary

| Metric | Corrected Status |
|---|---|
| Current implementation state | MCP lifecycle scaffold with deterministic phase progression |
| MVP completeness | Low: core happy path exists, validation/recovery loop is not operational |
| Production readiness | Not ready |
| Current phase | Phase 1: single authoritative submit pipeline |
| Primary blocker | Runtime wiring from `submit_output` through ToolExecutor, ToolGate, checkpoint, persistence, and recovery |
| Implementation rule | Do not mark a subsystem implemented unless it is operationally integrated |

## Operational Status

| Subsystem | Status | Evidence | MVP Role |
|---|---|---|---|
| Feature phase graph | operationally integrated | `PhaseGraph` loaded in app lifespan; feature transitions used by submit flow | Required |
| Task CRUD | operationally integrated | MCP task tools use SQLite via write queue | Required |
| SQLite task store | operationally integrated | Runtime task authority for create/get/update/list/history/checkpoints | Required |
| Write queue | operationally integrated | Used for task, phase output, checkpoint writes | Required |
| Basic latest checkpoint | partially wired | Checkpoint created on accepted submit; restore/resume not wired | Required |
| FSM submit transition | operationally integrated | `submit_output` validates phase and advances with `OrchestratorFSM` | Required |
| Schema checks | partially wired | Run through `JudgeEngine`; not separated as explicit deterministic stage in submit contract | Required |
| Judge engine | partially wired | Called from submit flow; fail-open and no bounded retry/fallback semantics | Required but bounded |
| Debate runtime | partially wired | Runs only on judge rejection; optional and not MVP-critical | Deferred for MVP unless it blocks nothing |
| ToolExecutor | scaffolded | Module exists; not initialized or called by submit flow | Required |
| ToolGate | scaffolded | Sequence evaluator exists; not wired to adapters/executor/submit flow | Required |
| Tool adapters | scaffolded | Individual adapters exist; not registered into runtime gate path | Required subset only |
| Budget handling | partially wired | `ExecutionPolicy.check_budget` checks iterations/runtime; `BudgetController` not on submit path | Required minimal |
| Recovery engine | scaffolded | Module exists; no checkpoint restore/resume integration | Required minimal |
| Retry policy | scaffolded | Module exists; submit flow does not perform bounded retry handling | Required minimal |
| Execution runtime | scaffolded | Module exists; app does not create execution contexts or lock runtime IDs | Required only if used to support deterministic submit path |
| Enhanced checkpoints | scaffolded | Versioned manager exists; app uses base `CheckpointManager` | Defer version chains |
| StateManager | scaffolded | Atomic state files exist; not runtime authority | Defer or remove from MVP authority |
| Rollback manager | non-operational concept | In-memory planning/records only; no git restore/checkpoint restore | Defer |
| Replay engine | non-operational concept | Trace/checkpoint reader; explicit TODO for full replay | Defer |
| Memory | partially wired/scaffolded | MCP memory tools exist when enabled; not part of phase context loop | Defer |
| Dashboard | scaffolded | Data aggregation module; not runtime critical | Defer |
| Team coordinator | non-operational concept | Parallel subagent coordination not used | Defer |
| Autonomous controller | non-operational concept | Watchdog mode not used by runtime | Defer |
| Extra workflows | partially wired labels | Modes accepted, but app always loads feature graph | Defer |

## Corrected MVP

MVP is one deterministic feature workflow that can advance from task creation to
Done only after operational validation and recoverable persistence.

MVP must include:

- Feature workflow only.
- Single authoritative `submit_output` pipeline.
- FSM transition validation.
- Deterministic schema validation before any LLM judgment.
- ToolExecutor-managed validation commands.
- ToolGate enforcement after Coding and Testing.
- SQLite as task/history authority.
- Checkpoint saved after accepted transitions.
- Resume from latest checkpoint after restart or explicit recovery.
- Bounded retry handling for transient tool/model/runtime failures.
- Integration tests that prove acceptance and rejection paths.

MVP must not include:

- Versioned checkpoint chains unless required for latest checkpoint restore.
- Rollback to git state.
- Advanced replay.
- Advanced memory/context injection.
- Dashboards.
- Confidence analytics.
- Multi-agent/team coordination.
- Non-feature workflow templates.
- Enterprise or external integrations.

## Implementation Phases

### Phase 0: Baseline Correction

**Objective:** Make planning reflect operational truth.

| Task | Acceptance |
|---|---|
| Replace module-existence statuses with runtime integration statuses | Docs distinguish file exists, scaffolded, partially wired, integrated, production-ready |
| Remove MVP claims for rollback, replay, memory, dashboard, team coordination | Deferred list is explicit |
| Define one authoritative runtime path | All planning points to `submit_output -> ToolExecutor -> ToolGate -> validation -> checkpoint -> persistence -> recovery` |

### Phase 1: Single Submit Pipeline

**Objective:** Make `submit_output` the only phase-transition authority.

| Task | Acceptance |
|---|---|
| Split submit flow into explicit stages: load task, phase match, budget, schema, judge, tool gate, transition, checkpoint, persistence | Integration test verifies stage ordering |
| Reject any transition that bypasses required validation | Coding output cannot reach Review without configured gate result |
| Persist accepted and rejected phase attempts consistently | Status and history survive restart |
| Remove or ignore unused authority abstractions from MVP flow | No fake authority requirement in acceptance criteria |

### Phase 2: ToolExecutor and ToolGate Enforcement

**Objective:** Make validation authoritative.

| Task | Acceptance |
|---|---|
| Initialize ToolExecutor in app lifespan with only required adapters | Healthcheck result recorded or exposed |
| Initialize ToolGate with MVP gate order | Gate order is deterministic and test-covered |
| Wire Coding/Testing validation through ToolExecutor before phase advancement | Failing lint/type/test blocks transition |
| Keep Specs/Planning free of code gates | Non-code phases are not blocked by missing tool adapters |
| Persist gate results in phase output/history | Recovery/status can explain why a transition failed |

MVP gate order:

```
Coding/Testing: lint -> types -> tests
Review: no tool gate for MVP unless explicitly needed
Other phases: no tool gate
```

### Phase 3: Checkpoint Restore and Bounded Recovery

**Objective:** Make recovery real before adding advanced recovery systems.

| Task | Acceptance |
|---|---|
| Add resume/restore path from latest checkpoint | Restart or recovery returns task to last accepted phase |
| Persist retry counters needed for bounded retries | Retries survive process restart |
| Implement bounded retry around transient tool/model errors | Retry count has hard ceiling and clear terminal status |
| Mark unrecoverable tasks stalled with reason | No infinite loops |
| Add crash/restart integration test | Task can resume after server process restart |

### Phase 4: MVP End-to-End Feature Workflow

**Objective:** One operational deterministic autonomous execution loop.

| Task | Acceptance |
|---|---|
| Execute feature task through Chatting, Specs, Planning, Coding, Review, Testing, Done | End-to-end integration test passes |
| Force a tool-gate failure | Task remains in current phase with actionable failure |
| Force a transient failure | Runtime retries within configured ceiling |
| Force restart after checkpoint | Runtime resumes from latest accepted checkpoint |
| Verify SQLite task authority | Task status/history/checkpoint are consistent |

### Phase 5: Post-MVP Hardening

**Objective:** Improve reliability only after MVP loop is real.

Allowed work:

- Observability coverage for runtime stages.
- Production fail-closed/fail-open policy controls.
- Adapter healthcheck hardening.
- State compaction/backups.
- Additional workflow templates.

Deferred work remains deferred until this phase is complete.

## Critical Blockers

| Blocker | Impact | Resolution |
|---|---|---|
| ToolGate not wired into submit flow | Code can advance without authoritative validation | Wire ToolExecutor + ToolGate before Coding/Testing transition |
| ToolExecutor not initialized in runtime | Validation commands are not governed | Initialize executor and register MVP adapters |
| Checkpoint restore/resume absent | Checkpoints are snapshots, not recovery | Add latest-checkpoint resume path |
| Retry state not persisted | Recovery is not deterministic across restart | Persist retry counters and failure reasons |
| Workflow modes are labels only | Non-feature modes imply false capability | Defer non-feature modes or reject them until wired |
| Documentation overstated readiness | Implementation sequencing is distorted | Keep this roadmap as source of truth |

## Release Readiness Gates

| Gate | MVP Required |
|---|---|
| Feature workflow only | Yes |
| Single submit pipeline | Yes |
| ToolGate blocks failing Coding/Testing output | Yes |
| ToolExecutor owns validation command execution | Yes |
| SQLite task/history authority | Yes |
| Latest checkpoint restore/resume | Yes |
| Bounded retry handling | Yes |
| Full deterministic replay | No |
| Rollback to git state | No |
| Dashboard | No |
| Advanced memory | No |
| Extra workflows | No |

## Current Priority Order

1. Correct runtime status and remove false implementation claims.
2. Refactor `submit_output` into explicit authoritative stages.
3. Initialize and wire ToolExecutor.
4. Initialize and wire ToolGate for Coding/Testing.
5. Persist validation results and rejected attempts.
6. Implement latest checkpoint restore/resume.
7. Add bounded retry handling with persisted counters.
8. Prove one feature workflow end-to-end.
