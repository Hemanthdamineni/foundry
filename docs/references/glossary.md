# Glossary

| Term | Meaning |
|---|---|
| Authoritative submit path | `submit_output -> ToolExecutor -> ToolGate -> validation -> checkpoint -> persistence -> recovery` |
| Feature workflow | The only MVP workflow: Chatting, Specs, Planning, Coding, Review, Testing, Done |
| SQLite authority | Rule that task state lives in SQLite, not checkpoints or JSON state files |
| ToolExecutor | Runtime-owned component that executes validation commands |
| ToolGate | Runtime-owned component that evaluates lint/type/test gate results |
| Latest checkpoint | Most recent accepted-state recovery snapshot |
| Resume | Explicit latest-checkpoint reconciliation via `sdlc_resume_task(task_id)` |
| File exists | Code file is present, but no operational claim is made |
| Scaffolded | API/module exists but is not part of the runtime path |
| Partially wired | Runtime initializes or calls part of a subsystem |
| Operationally integrated | Runtime depends on the subsystem and tests cover it |
| Production-ready | Operational, failure-tested, observable, bounded, and documented |
| Deferred | Explicitly outside MVP |

## Deferred Terms

Rollback, deterministic replay, distributed execution, dashboards, vector memory,
multi-agent coordination, enterprise integrations, and autonomous controllers
are post-MVP unless a later roadmap explicitly promotes them.
