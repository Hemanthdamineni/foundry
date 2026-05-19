# Dependency Graph and Technical Debt

> Runtime integration dependency graph. This replaces the previous
> module-existence graph with the order required to make one operational
> deterministic execution loop.

## 1. Correct Dependency Principle

Dependencies are ordered by runtime execution, not package structure.

The critical path is:

```
Feature task
  -> SQLite task authority
  -> submit_output
  -> FSM transition resolution
  -> deterministic validation
  -> ToolExecutor
  -> ToolGate
  -> accepted/rejected phase record
  -> checkpoint
  -> recovery/resume
```

Anything outside this chain is deferred unless it removes a blocker in the
chain.

## 2. MVP Dependency Graph

### Layer 0: Foundational Runtime Truth

```
PhaseGraph
SchemaChecks
StoreBackend
SqliteStore
WriteQueue
CheckpointManager (latest checkpoint only)
```

These must remain small and deterministic.

### Layer 1: Submit Authority

```
OrchestratorFSM -> PhaseGraph
ExecutionPolicy -> Task.budget / iteration limits
submit_output -> SqliteStore, OrchestratorFSM, SchemaChecks, WriteQueue
```

This layer decides whether a phase may advance.

### Layer 2: Authoritative Validation

```
ToolAdapter subset -> ToolExecutor -> ToolGate -> submit_output
JudgeEngine -> SchemaChecks + LLMProvider -> submit_output
```

MVP requires ToolExecutor and ToolGate before accepting Coding/Testing.
Judge remains secondary to deterministic/tool validation.

### Layer 3: Persistence and Recovery

```
submit_output -> WriteQueue -> SqliteStore
submit_output -> WriteQueue -> CheckpointManager
recovery/resume -> SqliteStore + CheckpointManager
bounded retry -> persisted task metadata
sdlc_resume_task -> SqliteStore + CheckpointManager
```

Recovery must use persisted runtime state. In-memory counters are insufficient.

### Layer 4: Post-MVP Systems

```
EnhancedCheckpointManager
RollbackManager
ReplayEngine
MemoryStore
Dashboard
TeamCoordinator
AutonomousController
Non-feature workflow graphs
Enterprise integrations
```

These are not dependencies for MVP and must not block it.

## 3. Corrected Blocking Dependencies

| Blocker | Blocks | Required Before |
|---|---|---|
| ToolExecutor not initialized in app lifespan | Governed validation execution | ToolGate enforcement |
| ToolGate not called by submit flow | Authoritative code validation | MVP end-to-end feature workflow |
| Required adapters not registered | lint/type/test gate execution | ToolGate enforcement |
| Rejected attempts not fully persisted | retry/recovery correctness | Bounded retry |
| Checkpoint restore/resume absent | crash recovery | MVP reliability gate |
| Retry counters not persisted | deterministic recovery after restart | Bounded retry |
| Non-feature modes accepted without graph selection | capability truth | MVP release |
| `Chatting -> Done` unguarded | feature workflow can skip critical phases | Submit pipeline hardening |
| ToolExecutor payload unspecified | adapters diverge at integration time | ToolExecutor wiring |
| Mypy skip policy ambiguous | types gate can silently pass | ToolGate enforcement |

## 4. Corrected Technical Debt

### P0: Blocks MVP Runtime Loop

| Debt | Current Reality | Fix |
|---|---|---|
| Submit pipeline is implicit and incomplete | Phase advances before any tool validation | Stage submit flow and insert ToolGate before advancement |
| ToolExecutor is scaffolded | Not constructed or used by app | Initialize in lifespan and use for gate commands |
| ToolGate is scaffolded | Evaluates provided results only | Feed it ToolExecutor results in submit flow |
| Restore/resume missing | Checkpoints are written but not recovery authority | Add latest checkpoint restore/resume |
| Retry state in-memory/nonexistent in submit path | Restart loses failure context | Persist retry count and last failure on task |
| Workflow mode mismatch | Modes accepted but feature graph always loaded | Reject or defer non-feature modes |

### P1: Required After MVP Loop Works

| Debt | Current Reality | Fix |
|---|---|---|
| Judge fail-open hardcoded behavior | Model outages can pass silently | Make policy explicit and test both modes |
| BudgetController not on submit path | Resource counters are not authoritative | Either wire minimal counters or remove from MVP claims |
| Trace coverage partial | Spans exist but not full stage-level observability | Add stage-level spans after pipeline is stable |
| Adapter healthchecks not authoritative | Unhealthy tools discovered late | Healthcheck required adapters at startup |

### P2: Deferred Complexity

| Debt | Current Reality | Decision |
|---|---|---|
| Enhanced checkpoint chains | File exists, not live runtime authority | Defer |
| RollbackManager | In-memory planner, no git/checkpoint restore | Defer |
| ReplayEngine | Trace/checkpoint reader, not deterministic replay | Defer |
| Memory injection | Storage tools exist, not phase context authority | Defer |
| Dashboard | Aggregator exists, not needed for correctness | Defer |
| TeamCoordinator | Parallel coordination concept unused | Defer |
| AutonomousController | Watchdog concept unused | Defer |

## 5. Runtime Integration Order

Implement in this order:

1. Make `submit_output` stage ordering explicit and tested.
2. Add deterministic schema validation as an explicit pre-judge stage.
3. Initialize ToolExecutor with MVP adapters.
4. Initialize ToolGate with MVP gate order.
5. Call ToolExecutor + ToolGate from submit flow for Coding/Testing.
6. Enforce ToolExecutor payload shape and ToolResult-to-GateResult mapping.
7. Fail/unsupported missing required MVP adapters explicitly, including Mypy.
8. Guard or disable `Chatting -> Done` for normal feature tasks.
9. Persist validation results for both accepted and rejected attempts.
10. Keep rejected tasks in the same phase.
11. Write latest checkpoint only after accepted transitions.
12. Add explicit latest-checkpoint resume through `sdlc_resume_task(task_id)`.
13. Persist bounded retry state.
14. Add restart/recovery integration tests.
15. Prove one feature workflow end-to-end.

Do not implement rollback, replay, dashboards, memory, extra workflows, or
multi-agent orchestration before step 15.

## 6. Deferred Systems

### Distributed Execution

Deferred. Single-process runtime is the correct current scope.

### Advanced Memory and Vector Retrieval

Deferred. The MVP does not need semantic memory to validate deterministic
execution.

### Dashboards and Analytics

Deferred. Observability should start as stage-level traces/logs, not a UI.

### Multi-Agent Systems and Team Coordination

Deferred. The core architecture requires centralized orchestration and bounded
autonomy. Parallel teams would obscure runtime correctness.

### Advanced Replay

Deferred. First implement latest-checkpoint resume. Deterministic replay requires
captured prompts, model outputs, tool outputs, filesystem state, and decisions;
the current module does not provide that.

### Rollback

Deferred. Safe rollback requires real workspace file restoration, checkpoint
coordination, validation after restore, and stable phase semantics. The current
rollback module is not operational.

### Enterprise Integrations

Deferred. They do not improve the core execution loop.

## 7. Architecture Risks

| Risk | Severity | Correction |
|---|---|---|
| Documentation overstates readiness | High | Keep statuses operational, not file-based |
| Validation is not authoritative | High | Wire ToolExecutor + ToolGate into submit path |
| Checkpoints exist without recovery | High | Implement latest checkpoint restore/resume |
| Too many scaffolded systems distract from MVP | High | Defer them explicitly |
| Non-feature workflows imply false support | Medium | Reject/defer until graph selection is real |
| LLM judge fail-open hides quality failures | Medium | Make fail policy explicit and test it |

## 8. MVP Readiness Rule

A subsystem can be marked operationally integrated only when:

- the app initializes it when needed,
- the authoritative runtime path calls it,
- its result can change accept/reject behavior,
- its state is persisted if recovery depends on it,
- an integration test covers success and failure behavior.

Anything else is `file exists`, `scaffolded`, or `partially wired`.
