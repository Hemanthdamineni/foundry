# State Machines

This file is the MVP state-machine reference. It intentionally excludes
post-MVP replay, rollback, multi-workflow, and debate-state diagrams.

## Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> active : sdlc_create_task
    active --> active : submit_output rejected
    active --> done : Done accepted
    active --> stalled : budget/retry ceiling or unrecoverable failure
    active --> cancelled : explicit cancel
    done --> [*]
    stalled --> [*]
    cancelled --> [*]
```

| State | Meaning | Terminal |
|---|---|---|
| `active` | Task can accept submissions for its current phase | No |
| `done` | Feature workflow reached accepted Done | Yes |
| `stalled` | Runtime cannot proceed without user intervention | Yes |
| `cancelled` | User cancelled the task | Yes |

## Feature Phase FSM

MVP supports one workflow:

```mermaid
stateDiagram-v2
    [*] --> Chatting
    Chatting --> Specs : accepted
    Specs --> Planning : accepted
    Planning --> Coding : accepted
    Coding --> Review : ToolGate accepted
    Review --> Coding : review rejected
    Review --> Testing : accepted
    Testing --> Done : ToolGate accepted
    Done --> [*]
```

The source graph may contain `Chatting -> Done`. For MVP this edge is not a
normal feature-task path. It must be disabled for normal feature work or guarded
by an explicit early-completion decision that is persisted and tested.

Other YAML graph templates are not MVP execution paths.

## Submit Pipeline FSM

```mermaid
stateDiagram-v2
    [*] --> LoadTask
    LoadTask --> Reject : missing/inactive task
    LoadTask --> CheckPhase
    CheckPhase --> Reject : phase mismatch
    CheckPhase --> CheckSchema
    CheckSchema --> Reject : invalid output
    CheckSchema --> OptionalJudge
    OptionalJudge --> Reject : judge/debate rejected
    OptionalJudge --> ToolGateCheck : Coding or Testing
    OptionalJudge --> PersistAccepted : other phase
    ToolGateCheck --> Reject : gate failed
    ToolGateCheck --> PersistAccepted : gate passed
    PersistAccepted --> WriteCheckpoint
    WriteCheckpoint --> Done
    Reject --> Done
    Done --> [*]
```

Rejected attempts may be recorded, but rejected attempts do not advance phase or
write accepted checkpoints.

## ToolGate FSM

```mermaid
stateDiagram-v2
    [*] --> Lint
    Lint --> Types : passed
    Lint --> Failed : failed
    Types --> Tests : passed
    Types --> Failed : failed or unsupported
    Tests --> Passed : passed
    Tests --> Failed : failed
    Passed --> [*]
    Failed --> [*]
```

The ToolExecutor runs commands. ToolGate evaluates normalized command results.

## Recovery/Resume FSM

```mermaid
stateDiagram-v2
    [*] --> Requested : sdlc_resume_task(task_id)
    Requested --> LoadSQLite
    LoadSQLite --> LoadCheckpoint
    LoadCheckpoint --> NotRecoverable : missing checkpoint
    LoadCheckpoint --> Failed : corrupt checkpoint
    LoadCheckpoint --> Mismatch : checkpoint/SQLite disagreement
    LoadCheckpoint --> Resumed : compatible latest checkpoint
    Mismatch --> Failed : no silent overwrite
    Resumed --> [*]
    NotRecoverable --> [*]
    Failed --> [*]
```

MVP recovery restores or confirms the latest accepted state. It does not perform
advanced replay, version-chain selection, git rollback, structural replanning,
or workspace snapshot restoration.

## Write Queue FSM

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : write enqueued
    Processing --> Processing : more writes
    Processing --> Idle : queue empty
    Processing --> Draining : shutdown requested
    Draining --> Shutdown : queue drained
    Shutdown --> [*]
```

The write queue preserves accepted-state write ordering. It is not a distributed
queue and does not imply parallel workflow execution.
