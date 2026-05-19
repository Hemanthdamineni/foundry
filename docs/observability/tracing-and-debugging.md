# Tracing and Debugging

Tracing for MVP is a debugging aid, not a runtime authority.

## MVP Trace Points

Useful stage-level trace points:

1. task loaded;
2. phase checked;
3. FSM target resolved;
4. schema validation result;
5. optional judge result;
6. ToolExecutor result;
7. ToolGate result;
8. persistence/checkpoint result;
9. recovery/resume result.

## Non-Goals

MVP tracing does not provide distributed tracing, deterministic replay, prompt
rollback, dashboard timelines, or cross-run analytics.

## Debugging Rule

If trace data disagrees with SQLite task state, SQLite wins for MVP. Trace data
can explain decisions; it cannot advance or recover tasks.
