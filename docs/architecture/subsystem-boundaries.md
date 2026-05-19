# Subsystem Boundaries

This document defines MVP ownership boundaries. It intentionally removes older
claims that treated scaffolded modules as operational subsystems.

## Boundary Map

| Layer | Owns | Must not own |
|---|---|---|
| User Workflows | user-visible task creation/status/submit/resume tools | internal phase mutation rules |
| Orchestration Runtime | feature FSM, current phase, transition decision, retry ceiling | shell command execution |
| Execution Runtime | submit pipeline, persistence calls, checkpoint calls, validation sequencing | independent workflow strategy |
| Tool Gateway | ToolExecutor command execution, ToolGate result evaluation | phase advancement |
| MCP Ecosystem | external tool surface exposed to clients | state authority |

## Runtime Authority

| Authority | MVP owner |
|---|---|
| Task state | SQLite via `SqliteStore` |
| Phase transition | `submit_output` pipeline |
| Code validation command execution | ToolExecutor |
| Code validation accept/reject | ToolGate |
| Latest recovery snapshot | CheckpointManager + SQLite metadata |
| Resume entrypoint | minimal `sdlc_resume_task(task_id)` |

## Deferred Boundaries

These modules/concepts may exist, but are not MVP runtime authorities:

- `EnhancedCheckpointManager`;
- `RollbackManager`;
- `ReplayEngine`;
- `StateManager` JSON state authority;
- debate/team coordination;
- dashboard/metrics engines;
- memory/vector retrieval;
- security/coverage/benchmark gates beyond the MVP lint/type/test path.

Do not wire them before the single operational feature loop is complete.
