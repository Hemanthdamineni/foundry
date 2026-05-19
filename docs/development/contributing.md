# Contributing

Until MVP completion, contributions should protect the single operational
feature loop.

## Development Priorities

1. Keep `submit_output` authoritative.
2. Wire ToolExecutor and ToolGate into Coding/Testing.
3. Preserve SQLite as task authority.
4. Write latest checkpoints only after accepted transitions.
5. Implement explicit `sdlc_resume_task(task_id)` latest-checkpoint recovery.
6. Add integration tests before expanding scope.

## Do Not Add Before MVP

- extra workflows;
- distributed execution;
- multi-agent coordination;
- dashboards;
- vector memory;
- advanced replay;
- git rollback;
- coverage/security/benchmark gates as required gates;
- autonomous controller modes.

## Testing Expectations

Minimum useful checks:

```bash
pixi run pytest
pixi run ruff check sdlc tests
pixi run mypy sdlc
```

If Mypy is not installed or not configured in a local environment, the runtime
gate behavior still must be explicit unsupported/failed. Silent success is not
acceptable.

## Review Checklist

- Does the change affect the authoritative submit path?
- Does it mutate task state outside SQLite/write queue?
- Does it add a deferred system as a hidden dependency?
- Does it distinguish file existence from operational integration?
- Does it include failure-path validation?
