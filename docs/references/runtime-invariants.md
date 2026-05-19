# Runtime Invariants

This reference is MVP-scoped. It describes the invariants required for the
first operational Foundry runtime, not the larger deferred architecture.

Authoritative execution path:

```text
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> SQLite persistence
  -> recovery/resume
```

## I1: SQLite Is Task Authority

Task status, current phase, phase history, accepted outputs, retry counters, and
checkpoint metadata are authoritative only when persisted through `SqliteStore`
and the write queue.

`StateManager` files, checkpoint files, traces, and in-memory objects are not
competing authorities for MVP.

Verification: restart the runtime and confirm task state is reconstructed from
SQLite, with checkpoint files used only for explicit recovery/reconciliation.

## I2: One Feature FSM

MVP execution uses only the `feature` workflow:

```text
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
```

The existing `Chatting -> Done` edge is not a normal feature-task shortcut. It
must either be disabled for normal feature runs or accepted only by an explicit
early-completion policy that records why the task did not need the full graph.

Verification: a normal feature task cannot skip Specs, Planning, Coding, Review,
or Testing through accidental phase selection.

## I3: Submit Is The Only Phase-Mutation Path

No subsystem may advance a task phase except the authoritative submit pipeline.
Validators, tool adapters, checkpoints, and recovery helpers may report facts;
they do not decide accepted phase transitions independently.

Verification: search for direct phase writes outside `submit_output` and its
single persistence helper path.

## I4: Validation Precedes State Mutation

Accepted phase changes happen only after deterministic checks pass:

1. task exists and is active;
2. submitted phase matches current phase;
3. FSM transition is valid;
4. required schema/phase checks pass;
5. judge/debate checks pass where configured;
6. Coding/Testing ToolGate passes;
7. accepted output, next phase, history, and checkpoint metadata persist.

Rejected submissions may persist rejection history, but must not persist accepted
phase advancement or accepted checkpoint state.

## I5: ToolExecutor Owns Command Execution

Coding and Testing validation commands run through one runtime-owned
`ToolExecutor`. The submit pipeline must not shell out around it.

MVP adapter payload:

```python
{
    "task_id": task_id,
    "phase": phase,
    "path": workspace_path,
    "timeout_s": 30,
}
```

`path` is the workspace root for MVP. Changed-file targeting is post-MVP.

## I6: ToolGate Owns Code-Phase Acceptance

For Coding and Testing, the deterministic MVP gate order is:

```text
lint -> types -> tests
```

Gate mapping:

| Gate | Adapter |
|---|---|
| `lint` | Ruff |
| `types` | Mypy |
| `tests` | Pytest |

Mypy is required if registered and healthy. If unavailable in local test/dev
environments, the runtime must return an explicit unsupported or failed gate
result. Silent pass is forbidden.

## I7: Checkpoints Are Recovery Inputs, Not Task Authority

Accepted submissions write a latest checkpoint after validation succeeds.
Checkpoint restore is explicit and bounded:

- normal reads use SQLite;
- `sdlc_resume_task(task_id)` may reconcile/restore from the latest checkpoint;
- missing checkpoint returns an explicit not-recoverable result;
- corrupt checkpoint returns an explicit recovery failure;
- SQLite/checkpoint mismatch is reported, not silently overwritten.

Versioned checkpoint chains, rollback, and deterministic replay are deferred.

## I8: Retry Is Bounded And Narrow

Retries are allowed only for transient runtime failures such as timeout,
adapter process error, temporary unavailable tool, or interrupted persistence.

Validation failures from user output, lint/type/test failures, schema failures,
phase mismatches, budget exhaustion, and checkpoint corruption are terminal for
that submission. Retrying them without new user/model output would only hide the
real failure.

## I9: Writes Are Ordered And Atomic

All task, phase-output, rejection, and checkpoint metadata writes must go through
the write queue and SQLite transaction boundaries. A crash may lose an
unaccepted attempt, but it must not create a half-advanced accepted phase.

Verification: crash after validation but before checkpoint write and confirm the
task resumes from the last fully accepted persisted state.

## I10: Deferred Systems Cannot Be Runtime Dependencies

MVP must not require:

- distributed execution;
- advanced replay;
- git rollback;
- dashboards;
- vector/advanced memory;
- multi-agent coordination;
- autonomous controllers;
- enterprise integrations.

Files for these concepts may exist, but they are non-operational unless wired
into the authoritative runtime path and covered by integration tests.
