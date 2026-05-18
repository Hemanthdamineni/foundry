# State Machines

> Mermaid diagrams for all finite state machines in the Foundry runtime.

---

## Task Lifecycle FSM

```mermaid
stateDiagram-v2
    [*] --> active : sdlc_create_task
    active --> active : submit_output (rejected → retry)
    active --> completed : submit_output (final phase accepted)
    active --> stalled : budget exhausted
    active --> cancelled : sdlc_cancel_task
    completed --> [*]
    stalled --> [*]
    cancelled --> [*]
```

### States

| State | Meaning | Terminal |
|---|---|---|
| `active` | Task is executing, phases being processed | No |
| `completed` | All phases passed, task reached Done | Yes |
| `stalled` | Budget exhausted or irrecoverable failure | Yes |
| `cancelled` | User explicitly cancelled | Yes |

### Transitions

| From | To | Trigger |
|---|---|---|
| `[init]` | `active` | `sdlc_create_task` |
| `active` | `active` | `submit_output` rejected (stays in same phase) |
| `active` | `completed` | `submit_output` accepted AND next phase is Done |
| `active` | `stalled` | Budget ceiling hit (critical violation) |
| `active` | `cancelled` | `sdlc_cancel_task` |

---

## Phase Transition FSM (Feature Workflow)

```mermaid
stateDiagram-v2
    [*] --> Chatting
    Chatting --> Specs : output accepted
    Specs --> Planning : output accepted
    Planning --> Coding : output accepted
    Coding --> Testing : output accepted
    Testing --> Coding : test failures (back-edge)
    Testing --> Review : output accepted
    Review --> Coding : review rejections (back-edge)
    Review --> Done : output accepted
    Done --> [*]
```

### Phase Graph Properties

| Property | Value |
|---|---|
| Entry phase | Chatting |
| Terminal phase | Done |
| Back-edges | Testing→Coding, Review→Coding |
| Minimum path | 7 transitions (no retries) |
| Maximum path | Unbounded (limited by budget) |

### Phase Validation Rules

1. All transitions must be explicitly defined in the graph
2. Every phase must be reachable from the entry phase
3. Done must have no outgoing edges
4. No self-loops (a phase cannot transition to itself)
5. Back-edges must target an earlier phase (not a later one)

---

## Recovery Escalation FSM

```mermaid
stateDiagram-v2
    [*] --> LOCAL_RETRY : retryable failure
    LOCAL_RETRY --> LOCAL_RETRY : retry succeeds → [*]
    LOCAL_RETRY --> LOCAL_REPLAN : retries exhausted
    LOCAL_REPLAN --> LOCAL_REPLAN : replan succeeds → [*]
    LOCAL_REPLAN --> PHASE_RETRY : replans exhausted
    PHASE_RETRY --> PHASE_RETRY : phase retry succeeds → [*]
    PHASE_RETRY --> STRUCTURAL_REPLAN : phase retries exhausted
    STRUCTURAL_REPLAN --> STRUCTURAL_REPLAN : replan succeeds → [*]
    STRUCTURAL_REPLAN --> FULL_RECOVERY : replan fails
    FULL_RECOVERY --> FULL_RECOVERY : recovery succeeds → [*]
    FULL_RECOVERY --> ABORT : recovery fails
    ABORT --> [*]
```

### Escalation Counters

| Level | Counter | Default Max | Reset On |
|---|---|---|---|
| LOCAL_RETRY | Per-phase retry count | 3 | Phase reset |
| LOCAL_REPLAN | Per-phase replan count | 2 | Phase reset |
| PHASE_RETRY | Per-phase phase-retry count | 1 | Never (consumed) |
| STRUCTURAL_REPLAN | Per-task replan count | 1 | Never |
| FULL_RECOVERY | Per-task recovery count | 1 | Never |

---

## Debate Protocol FSM

```mermaid
stateDiagram-v2
    [*] --> ROUND_1 : judge rejected, debate configured
    ROUND_1 --> ROUND_2 : round complete, budget remaining
    ROUND_1 --> CONSENSUS : budget exhausted
    ROUND_2 --> ROUND_3 : round complete, budget remaining
    ROUND_2 --> CONSENSUS : budget exhausted
    ROUND_3 --> CONSENSUS : round complete
    CONSENSUS --> ACCEPTED : consensus passed
    CONSENSUS --> REJECTED : consensus failed
    ACCEPTED --> [*]
    REJECTED --> [*]
```

### Round Protocol

| Round | Context Available | Purpose |
|---|---|---|
| ROUND_1 | Phase output only | Independent assessment |
| ROUND_2 | + All Round 1 responses | Deliberation |
| ROUND_3 | + All Round 2 responses | Final positions |
| CONSENSUS | All rounds | Verdict synthesis |

---

## Write Queue FSM

```mermaid
stateDiagram-v2
    [*] --> IDLE : initialized
    IDLE --> PROCESSING : WriteOp enqueued
    PROCESSING --> PROCESSING : more ops in queue
    PROCESSING --> IDLE : queue empty
    IDLE --> SHUTDOWN : shutdown requested
    PROCESSING --> DRAINING : shutdown requested
    DRAINING --> SHUTDOWN : queue drained
    SHUTDOWN --> [*]
```

### Queue Guarantees

1. **FIFO ordering** — operations processed in submission order
2. **At-least-once** — operations are retried on handler failure
3. **Graceful shutdown** — DRAINING processes remaining operations before stopping
4. **No loss** — operations in the queue at shutdown are processed
