# Runtime and State Management

> MVP state contract. SQLite is the task authority; latest checkpoint is the
> recovery snapshot.

## MVP State Authority

| State | Authority |
|---|---|
| task status | SQLite |
| current phase | SQLite |
| phase history | SQLite |
| accepted checkpoint snapshot | latest checkpoint file |
| recovery reconciliation | SQLite + latest checkpoint |

`StateManager` JSON files and `EnhancedCheckpointManager` version chains exist
as scaffolds/reference systems. They are not MVP task authority.

## Write Path

Accepted transition:

```
submit_output
  -> append accepted PhaseRecord
  -> update task.current_phase
  -> WriteQueue task update
  -> WriteQueue phase_output create
  -> WriteQueue checkpoint create
```

Rejected submission:

```
submit_output
  -> append rejected PhaseRecord
  -> keep task.current_phase unchanged
  -> WriteQueue task update
  -> WriteQueue phase_output create(status=rejected)
  -> no accepted checkpoint
```

## Checkpoint Contract

For MVP, write one latest checkpoint after each accepted transition. It must
contain enough data to restore the latest accepted state:

- task id;
- current phase after transition;
- accepted/rejected history as persisted on task;
- iteration/retry metadata needed for recovery;
- timestamp.

Versioned checkpoint chains, named restore points, rollback targets, and replay
sequences are post-MVP.

## Recovery Contract

Normal reads use SQLite. Recovery uses latest checkpoint only when:

- recovery is explicitly requested;
- startup/status detects missing task state with existing checkpoint;
- implementation detects a recoverable SQLite/checkpoint inconsistency.

If SQLite and checkpoint disagree, the runtime must report an explicit recovery
error or repair result. It must not silently choose divergent state.

## Atomicity

SQLite writes use transactions. Checkpoint writes use atomic temp-file rename.
The runtime must not report an accepted transition until the required writes are
complete or a write failure is returned.
