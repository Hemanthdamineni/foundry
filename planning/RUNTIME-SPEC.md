# Runtime Specification

> Authoritative runtime contract for building one operational deterministic
> feature workflow. This spec intentionally excludes speculative systems and
> module-existence claims.

## 1. Runtime Baseline

Foundry currently has a real MCP server, task lifecycle tools, SQLite-backed
task storage, a feature phase graph, basic phase advancement, schema checks
through the judge path, optional judge/debate calls, write queue persistence,
and latest-checkpoint writes.

Foundry does not yet have an operational autonomous execution loop because the
submit path does not enforce tool validation, recovery, resume, bounded retry,
or governed tool execution.

## 2. Authoritative Execution Path

The runtime path for MVP is:

```
User Workflow
  -> sdlc_create_task
  -> sdlc_get_next_action
  -> sdlc_submit_output
  -> deterministic validation
  -> optional judge
  -> ToolExecutor
  -> ToolGate
  -> FSM transition
  -> checkpoint
  -> SQLite persistence
  -> sdlc_resume_task
```

No subsystem is MVP-critical unless it participates in this path.

## 3. Submit Pipeline Contract

`sdlc_submit_output` is the single phase transition authority. The target MVP
pipeline is:

```
submit_output(task_id, phase, output, next_phase?):
  1. Load task from SQLite.
  2. Reject if task is missing, done, cancelled, or stalled.
  3. Reject if submitted phase does not equal task.current_phase.
  4. Check minimal budget/retry limits.
  5. Resolve candidate next phase through OrchestratorFSM.
     - For normal feature tasks, `Chatting -> Done` is rejected unless an
       explicit early-completion policy marks and persists the task as complete.
  6. Run deterministic schema validation for the submitted phase.
  7. Run judge only if configured and deterministic validation passed.
  8. For Coding/Testing, execute validation commands through ToolExecutor.
  9. Evaluate ToolGate result in deterministic order.
 10. If validation fails, persist rejected attempt and keep current phase.
 11. If validation passes, append accepted phase record.
 12. Advance task.current_phase to the resolved phase.
 13. Persist task update, phase output, validation result, and checkpoint.
 14. Return accepted result with next_phase and validation summary.
```

Rejected attempts are runtime events, not invisible failures. They must be
persisted enough for status, retry, and recovery decisions.

## 4. MVP Invariants

| Invariant | Required Enforcement |
|---|---|
| SQLite is task authority | All task status/history/current phase reads come from `SqliteStore` |
| `submit_output` is transition authority | No phase advancement outside the submit pipeline |
| FSM validates transitions | `OrchestratorFSM` resolves and rejects invalid next phases |
| Deterministic validation precedes LLM judgment | Schema checks run before judge |
| Tool validation is authoritative for code phases | Coding/Testing cannot advance unless ToolGate passes |
| Tool execution is governed | Validation commands run through ToolExecutor |
| Checkpoint follows accepted transition | Accepted transition writes latest checkpoint |
| Rejection does not advance phase | Failed validation keeps task in current phase |
| Retry is bounded | Transient failures have persisted retry counters and hard ceilings |
| Recovery resumes from persisted state | Restart/recovery reconstructs task from SQLite/checkpoint |

The existing `Chatting -> Done` graph edge is not a normal MVP shortcut. It is
either disabled for feature tasks or guarded by an explicit early-completion
decision with persisted reason and tests.

## 5. Operational Status by Runtime Concern

| Concern | Current Status | MVP Required Change |
|---|---|---|
| Task creation | operationally integrated | Keep |
| Feature FSM | operationally integrated | Keep |
| Phase submit | partially wired | Refactor into explicit staged pipeline |
| Schema validation | partially wired | Make deterministic stage explicit |
| Judge | partially wired | Keep bounded and optional/fail policy explicit |
| Debate | partially wired | Defer from MVP unless already harmless |
| ToolExecutor | scaffolded | Initialize and route validation calls through it |
| ToolGate | scaffolded | Enforce Coding/Testing gate before transition |
| Checkpoint write | partially wired | Keep latest checkpoint and add restore/resume |
| Enhanced checkpoints | scaffolded | Defer versioned chains |
| Recovery | scaffolded | Implement latest-checkpoint resume and stalled status |
| Retry policy | scaffolded | Implement minimal bounded retry in submit path |
| Rollback | non-operational concept | Defer |
| Replay | non-operational concept | Defer |
| Memory | partially wired/scaffolded | Defer phase-context injection |
| Dashboard | scaffolded | Defer |

## 6. Orchestration Boundary

The Orchestration Runtime owns:

- task phase sequencing
- next-phase resolution
- validation ordering
- retry/recovery decisions
- acceptance/rejection outcome

It must not own:

- direct shell execution
- direct MCP/tool execution
- dashboard presentation
- memory analytics
- speculative parallel team coordination

The Execution Runtime owns:

- MCP tool handlers
- ToolExecutor initialization
- ToolGate execution and result shaping
- persistence calls through WriteQueue and SQLite
- checkpoint/resume mechanics
- minimal `sdlc_resume_task(task_id)` entrypoint if it is not already exposed

## 7. Tool Validation Contract

For MVP:

| Phase | Tool Gate |
|---|---|
| Chatting | none |
| Specs | none |
| Planning | none |
| Coding | lint -> types -> tests |
| Review | none |
| Testing | lint -> types -> tests |
| Done | none |

Rules:

- Tool commands are executed only by ToolExecutor.
- ToolGate receives normalized ToolExecutor results.
- ToolGate fails fast in configured order.
- A failed gate persists result and blocks transition.
- Missing required adapters fail closed for Coding/Testing.
- Optional tools are not part of MVP acceptance.

MVP ToolExecutor payload:

```python
{
    "task_id": task_id,
    "phase": phase,
    "path": workspace_path,
    "timeout_s": 30,
}
```

`path` is the workspace root for MVP. Changed-file targeting is post-MVP.

ToolResult to GateResult mapping:

| ToolExecutor result | ToolGate result |
|---|---|
| exit `0` and `passed=True` | pass |
| nonzero exit or `passed=False` | fail |
| timeout/process execution error | transient ToolExecutor failure |
| missing MVP adapter | fail/unsupported |
| malformed adapter output | terminal adapter contract failure |

Mypy policy: required if registered and healthy. If unavailable in local
test/dev environments, return explicit unsupported/failed result; never silently
pass the `types` gate.

## 8. State and Recovery Contract

SQLite is the authoritative task store for MVP. Checkpoint files are recovery
snapshots, not an alternate source of truth during normal execution.

Checkpoint behavior:

- Write one latest checkpoint after each accepted transition.
- Include task_id, current phase, accepted history, iteration count, and enough
  validation metadata to explain the last accepted state.
- Normal status reads load latest task from SQLite.
- Explicit resume is performed by `sdlc_resume_task(task_id)`.
- Startup may detect inconsistency, but must not silently mutate task state.

Recovery behavior:

- If SQLite task exists and checkpoint exists, confirm they are compatible.
- If task state is missing but checkpoint exists, restore task from checkpoint.
- If both exist but disagree, return an explicit recovery error or repair result;
  do not silently choose a divergent state.
- If validation/retry ceilings are exhausted, mark task `stalled` with reason.

Versioned checkpoint chains, restore points, git rollback, and deterministic
replay are post-MVP.

## 9. Retry Contract

MVP retry handling is bounded and simple:

- Retry transient ToolExecutor failures up to configured ceiling.
- Retry transient judge/model failures only if policy allows.
- Do not retry deterministic schema failures.
- Do not retry ToolGate failures caused by user code/test failure.
- Do not retry phase mismatches, missing MVP adapters, checkpoint corruption, or
  SQLite/checkpoint mismatches as transient failures.
- Persist retry count and last failure reason.
- On exhaustion, keep phase unchanged and return a terminal/stalled result.

Five-level escalation, replanning, rollback, and replay are deferred until this
minimal retry loop works.

## 10. Acceptance Criteria

MVP runtime is accepted only when all are true:

- A feature task can complete through all phases using the single submit path.
- Coding/Testing transitions are blocked by failing ToolGate results.
- Validation tools are executed through ToolExecutor.
- Rejected attempts are persisted and visible in task status/history.
- Checkpoints are written after accepted transitions.
- Latest checkpoint restore/resume works after process restart.
- Transient failures retry within a hard ceiling.
- Exhausted retries mark task stalled or return a non-advancing terminal failure.
- Non-feature workflow modes are either rejected or explicitly marked unsupported.

## 11. Deferred Systems

Deferred from MVP:

- distributed execution
- advanced memory
- dashboards
- team/multi-agent coordination
- autonomous controller modes
- advanced replay
- confidence analytics
- rollback to git state
- enterprise integrations
- non-feature workflows
- vector databases or semantic memory

These systems may remain as files, but they are not implementation priorities and
must not appear in MVP acceptance criteria.
