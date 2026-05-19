# Lifecycle and Phases

MVP lifecycle is intentionally simple and operational.

## Lifecycle

1. `sdlc_create_task` creates a feature task in SQLite.
2. Runtime starts in `Chatting`.
3. User/model submits output through `submit_output`.
4. Submit validates the current phase and decides accept/reject.
5. Accepted output advances through the feature FSM.
6. Accepted transition writes phase history and latest checkpoint metadata.
7. `Done` marks the task complete.
8. `sdlc_resume_task(task_id)` can explicitly reconcile/restore latest accepted
   checkpoint state.

## Feature Phases

```text
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
```

`Review -> Coding` remains the only MVP back edge.

The existing `Chatting -> Done` graph edge must not operate as a normal shortcut
for feature work. It must be disabled or guarded by an explicit
early-completion decision with persisted reason and tests.

## Code-Phase Gate

Coding and Testing cannot advance unless:

1. ToolExecutor runs lint, types, and tests;
2. ToolGate evaluates the normalized results in order;
3. all required gates pass.

Coverage, security, benchmarks, replanning, rollback, and multi-level recovery
are post-MVP.

## Failure Outcomes

| Failure | MVP behavior |
|---|---|
| phase mismatch | reject submission |
| schema failure | reject submission |
| judge rejection | reject submission |
| ToolGate failure | reject submission; do not checkpoint accepted state |
| transient ToolExecutor failure | bounded retry |
| retry exhaustion | explicit failure or stalled task |
| checkpoint mismatch/corruption | explicit recovery failure |
