# Foundry Architecture

> Final pre-implementation baseline. For MVP implementation, this file and
> `planning/` are authoritative. Older deep-dive docs are reference material
> only when they do not conflict with this baseline.

## Architecture

```
User Workflows
  -> Orchestration Runtime
  -> Execution Runtime
  -> Tool Gateway
  -> MCP Ecosystem
```

The MVP implementation must preserve this architecture and must not add new
runtime layers or subsystems.

## MVP Runtime Path

```
feature workflow
  -> sdlc_create_task
  -> sdlc_get_next_action
  -> sdlc_submit_output
  -> deterministic schema validation
  -> optional bounded judge
  -> ToolExecutor
  -> ToolGate
  -> FSM transition
  -> SQLite persistence
  -> latest checkpoint
  -> recovery/resume
```

`sdlc_submit_output` is the only phase-transition authority.

## MVP Scope

MVP includes:

- feature workflow only;
- deterministic feature FSM;
- single authoritative submit pipeline;
- ToolExecutor integration;
- ToolGate enforcement for Coding and Testing;
- SQLite task/history/status authority;
- latest-checkpoint write and restore/resume;
- bounded retry handling;
- deterministic validation ordering;
- recovery correctness.

MVP excludes:

- distributed execution;
- advanced replay;
- advanced rollback;
- dashboards;
- vector/advanced memory;
- multi-agent/team coordination;
- autonomous controller modes;
- enterprise integrations;
- advanced orchestration hierarchies;
- non-feature workflows.

## Runtime Ownership

| Layer | Owns | Does Not Own |
|---|---|---|
| User Workflows | Feature task intent | Runtime internals or extra workflow families |
| Orchestration Runtime | Phase sequencing, validation order, accept/reject decision | Direct tool execution |
| Execution Runtime | MCP tools, ToolExecutor, ToolGate, persistence, checkpoint/resume | New orchestration strategies |
| Tool Gateway | Governed validation command execution | Phase advancement |
| MCP Ecosystem | Filesystem/shell/git/tool access through governed execution | Runtime state authority |

## State Authority

SQLite is the MVP task authority for task status, current phase, and phase
history. Checkpoints are recovery snapshots. Normal runtime reads should not
treat checkpoint files or StateManager JSON files as competing task authority.

## Validation Authority

Validation order for MVP:

1. Task and phase guard.
2. FSM target validation.
3. Deterministic schema validation.
4. Optional bounded judge.
5. ToolExecutor validation command execution for Coding/Testing.
6. ToolGate fail-fast decision.
7. Persistence and checkpoint only after acceptance.

Coding and Testing cannot advance without passing the configured ToolGate path.

## Deferred Systems

The following files/modules may exist but are not MVP runtime dependencies:

- `runtime/enhanced_checkpoint.py`
- `runtime/rollback_manager.py`
- `engine/replay.py`
- `runtime/memory_store.py`
- `runtime/dashboard.py`
- `engine/team_coordinator.py`
- `runtime/autonomous_controller.py`
- non-feature graph templates

They must not appear in MVP acceptance criteria.

## Implementation Source of Truth

Use these documents for implementation:

1. `planning/MASTER-ROADMAP.md`
2. `planning/RUNTIME-SPEC.md`
3. `planning/DEPENDENCY-GRAPH.md`
4. `planning/TOOLING-AND-WORKFLOWS-SPEC.md`
5. `planning/QUALITY-AND-VALIDATION.md`
6. `planning/execution/`

Any older document that implies broader readiness is stale and must be updated
before being used for implementation decisions.
