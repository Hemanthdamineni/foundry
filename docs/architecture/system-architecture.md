# System Architecture

> MVP-aligned architecture reference. `planning/` remains the implementation
> source of truth.

## Runtime Layers

```
User Workflows
  -> Orchestration Runtime
  -> Execution Runtime
  -> Tool Gateway
  -> MCP Ecosystem
```

## MVP Runtime Path

```
sdlc_create_task
  -> sdlc_get_next_action
  -> sdlc_submit_output
  -> schema validation
  -> optional judge
  -> ToolExecutor
  -> ToolGate
  -> OrchestratorFSM transition
  -> SQLite task/history write
  -> latest checkpoint write
  -> restore/resume when needed
```

## Operational Status

| System | MVP Status |
|---|---|
| Feature phase graph | operationally integrated |
| Task CRUD | operationally integrated |
| SQLite store | operationally integrated |
| WriteQueue | operationally integrated |
| Submit FSM transition | operationally integrated |
| Schema checks | partially wired |
| Judge | partially wired |
| ToolExecutor | scaffolded; must be wired |
| ToolGate | scaffolded; must be wired |
| Latest checkpoint | partially wired; restore/resume missing |
| Bounded retry | scaffolded/minimal; must be implemented |
| Recovery | scaffolded; latest-checkpoint recovery missing |

## Deferred Systems

These remain outside MVP even if files exist:

- enhanced checkpoint chains;
- git rollback;
- deterministic replay;
- dashboard/analytics;
- advanced memory;
- team coordination;
- autonomous controllers;
- non-feature workflows;
- enterprise integrations.

## Ownership

| Layer | Responsibility |
|---|---|
| Orchestration Runtime | Phase sequencing, validation order, accept/reject outcome |
| Execution Runtime | MCP handlers, ToolExecutor, ToolGate, persistence, checkpoint/resume |
| Tool Gateway | Governed validation command execution |
| MCP Ecosystem | External tool access through governed calls |

## Non-Negotiable Invariants

- `submit_output` is the only phase-transition authority.
- SQLite is normal task authority.
- Checkpoint is recovery snapshot authority only.
- Coding and Testing require ToolGate approval.
- Rejected submissions do not advance phase.
- Retry ceilings are hard.
- Feature is the only MVP workflow.
