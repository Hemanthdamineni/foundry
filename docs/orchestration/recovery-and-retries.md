# Recovery and Retries

This document is MVP-scoped. Foundry does not implement five-level escalation,
structural replanning, advanced replay, or rollback for MVP.

## MVP Recovery Goal

Recovery must prove one concrete property:

> After an accepted phase transition, the runtime can restart or explicitly
> resume from the latest accepted persisted state without inventing progress or
> silently corrupting task authority.

SQLite remains task authority. Checkpoints are recovery inputs.

## Recovery Trigger

MVP recovery is explicit:

```text
sdlc_resume_task(task_id)
```

Normal status and next-action reads use SQLite. Resume may compare SQLite with
the latest checkpoint and restore only when the state is compatible or missing
in a way the implementation can prove safe.

If `sdlc_resume_task` does not yet exist, adding that minimal MCP tool is an MVP
integration requirement. It is not a new subsystem; it is the public entrypoint
for the existing checkpoint/recovery contract.

## Latest Checkpoint Rules

- accepted submissions write a latest checkpoint after validation passes;
- rejected submissions do not write accepted checkpoints;
- missing checkpoint returns explicit not-recoverable result;
- corrupt checkpoint returns explicit recovery failure;
- SQLite/checkpoint disagreement is reported, not silently overwritten;
- versioned checkpoint chains are deferred.

## Retry Policy

Retries are bounded and narrow.

Retryable:

- ToolExecutor timeout;
- adapter process interruption;
- temporary unavailable tool process;
- transient write queue or SQLite busy failure where transaction did not commit.

Terminal for the current submission:

- schema failure;
- phase mismatch;
- FSM transition rejection;
- judge/debate rejection;
- lint/type/test failure;
- missing required MVP adapter;
- checkpoint corruption;
- SQLite/checkpoint mismatch;
- budget exhaustion.

Terminal failures require new user/model output or explicit operator action.
They must not be auto-retried into acceptance.

## Runtime Invariants

- Retry counters are persisted or reconstructable from persisted rejection
  history.
- Retry exhaustion marks the task stalled or returns an explicit failure.
- Retry never bypasses ToolGate.
- Recovery never advances beyond the latest accepted phase.
- Recovery does not run git rollback, deterministic replay, structural replan,
  or workspace snapshot restoration.

## Validation Requirements

Minimum tests:

- accepted phase writes checkpoint metadata;
- rejected ToolGate result does not write accepted checkpoint;
- restart after checkpoint returns the last accepted phase;
- explicit resume succeeds with compatible latest checkpoint;
- missing/corrupt checkpoint returns explicit failure;
- SQLite/checkpoint mismatch does not silently overwrite either side;
- transient ToolExecutor failure retries up to the ceiling;
- lint/type/test failure is not retried as transient.
