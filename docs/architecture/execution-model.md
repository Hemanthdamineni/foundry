# Execution Model

> MVP execution model for one deterministic feature workflow.

## Principle

Foundry executes a finite phase workflow. It is not an open-ended agent loop and
not a distributed or multi-agent runtime for MVP.

## Feature FSM

```
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
                         ^                 |
                         +-- Review -> Coding
```

The existing graph also contains `Chatting -> Done`. For MVP this shortcut must
be governed explicitly: either reject it in `submit_output` for normal feature
tasks or treat it as an explicit early-completion path with deterministic
validation. It must not bypass validation by accident.

## Submit Pipeline

```
1. Load task from SQLite.
2. Reject missing/done/cancelled/stalled task.
3. Reject phase mismatch.
4. Check minimal budget/retry ceiling.
5. Resolve next phase through OrchestratorFSM.
6. Run schema validation.
7. Run optional bounded judge.
8. For Coding/Testing, run ToolExecutor validation commands.
9. Evaluate ToolGate.
10. Persist rejection or accepted transition.
11. Write checkpoint only after accepted transition.
12. Return structured result.
```

## Validation Order

Deterministic checks precede probabilistic checks. Tool validation is
authoritative for code phases.

| Stage | Authority |
|---|---|
| Phase/status guard | `submit_output` |
| FSM target | `OrchestratorFSM` |
| Schema | `schema_checks` |
| Judge | `JudgeEngine`, optional/bounded |
| Tool execution | `ToolExecutor` |
| Tool accept/reject | `ToolGate` |
| Persistence | `WriteQueue` + SQLite |
| Recovery snapshot | latest checkpoint |

## Retry and Recovery

MVP retry is bounded and simple:

- retry transient ToolExecutor or model/runtime failures;
- do not retry schema failures;
- do not retry real lint/type/test failures as runtime failures;
- persist retry count and last failure reason;
- stall or return terminal non-advancing failure on exhaustion.

Five-level recovery, replanning, rollback, and replay are post-MVP.
