# Architecture Patterns

## ToolAdapter Pattern
All external tool integrations implement `ToolAdapter` ABC:
- `name` property — unique human-readable identifier
- `capability` property — `ToolCapability` enum value
- `validate(task)` — check if the adapter can handle the task
- `execute(task)` — run the tool and return results
- `healthcheck()` — verify tool availability

## Wiring Pattern
All runtime dependencies are:
1. Created in the lifespan function (`runtime/app.py`)
2. Stored in `SDLCAppContext`
3. Retrieved via `_require_context(ctx)` in tool handlers
4. Passed explicitly to tool implementation functions

## Write Queue Pattern
All mutations go through `WriteQueue`:
1. Create `WriteOp(target, action, payload)`
2. Enqueue via `write_queue.enqueue(op)`
3. Call `write_queue.flush()` to drain
4. Background worker processes sequentially
5. Handler dispatches on `op.target`

## Checkpoint Pattern
Task state is snapshotted after each phase transition:
1. `Checkpoint` model serialized to JSON
2. Written atomically (tmp + rename) to disk
3. Also persisted to SQLite via write queue
4. Enables crash recovery and debugging

## Graceful Degradation
Optional dependencies are always guarded:
- `if tracer is not None:` before tracing
- `if judge_engine is not None:` before judging
- `if debate_runtime is not None:` before debating
- `if acervo is not None:` before memory operations
