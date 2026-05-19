# Technical Debt and Tradeoffs

> MVP-aligned technical debt inventory.

## P0 Debt Blocking MVP

| Debt | Impact | Fix |
|---|---|---|
| Submit pipeline is implicit | Validation/recovery cannot be inserted safely | Refactor `submit_output` into explicit stages |
| ToolExecutor not wired | Validation commands are not governed | Initialize in app lifespan and pass to phase tools |
| ToolGate not wired | Code phases can advance without tool truth | Enforce Coding/Testing gates before transition |
| Rejected attempts partially persisted | Recovery/status cannot explain failures | Persist rejected phase records and phase outputs |
| Latest checkpoint restore missing | Checkpoints do not provide recovery | Implement latest-checkpoint resume/recovery |
| Retry state not persisted | Retry behavior is not recoverable | Persist count and last failure reason |
| Non-feature modes accepted | False workflow support | Reject non-feature modes before MVP |

## P1 After MVP Loop Works

| Debt | Impact | Fix |
|---|---|---|
| Judge fail-open policy implicit | Model failure can pass silently | Make policy explicit and testable |
| Adapter healthcheck policy unclear | Missing tools may appear as passing | Report healthy/unhealthy required adapters |
| Stage-level tracing partial | Harder debugging | Add spans after pipeline is stable |

## Deferred Debt

These are real but post-MVP:

- enhanced checkpoint chains;
- git rollback;
- deterministic replay;
- memory/context injection;
- dashboards;
- extra workflows;
- sandbox hardening;
- enterprise integrations.

## Accepted MVP Tradeoffs

- Workspace-root validation is acceptable before changed-file targeting.
- Latest checkpoint restore is enough before versioned checkpoint chains.
- Simple bounded retry is enough before five-level recovery.
- Feature-only workflow is required before workflow families.
