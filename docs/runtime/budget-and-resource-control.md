# Budget and Resource Control

MVP budget control is minimal and exists to prevent unbounded execution.

## Required

- hard retry ceiling;
- phase/task stalled or terminal result on exhaustion;
- no infinite ToolExecutor retry;
- no auto-retry for deterministic validation failures;
- retry state persisted or reconstructable from rejection history.

## Deferred

Token-accurate accounting, debate budgets, workflow-specific budgets, cost
optimization, provider-aware routing, and dashboards are post-MVP.

Budget modules may exist, but MVP readiness depends on bounded retry behavior in
the authoritative submit path.
