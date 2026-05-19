# Foundry Documentation

> Documentation index aligned to the final pre-implementation MVP baseline.

For implementation, the authoritative documents are:

1. `ARCHITECTURE.md`
2. `ROADMAP.md`
3. `TODO.md`
4. `planning/`
5. `planning/execution/`

The deep-dive docs in this directory are reference material. If any deep-dive
doc conflicts with the authoritative baseline, the authoritative baseline wins.

## Authoritative MVP

```
User Workflows
  -> Orchestration Runtime
  -> Execution Runtime
  -> Tool Gateway
  -> MCP Ecosystem
```

MVP runtime path:

```
feature workflow
  -> submit_output
  -> deterministic validation
  -> ToolExecutor
  -> ToolGate
  -> checkpoint
  -> SQLite persistence
  -> latest-checkpoint recovery
```

## MVP Includes

- feature workflow only;
- deterministic FSM;
- single authoritative submit pipeline;
- ToolExecutor integration;
- ToolGate enforcement;
- SQLite task authority;
- latest-checkpoint restore/resume;
- bounded retry handling;
- deterministic validation flow;
- recovery correctness.

## Deferred From MVP

- distributed execution;
- advanced replay;
- advanced rollback;
- dashboards;
- vector/advanced memory;
- multi-agent/team coordination;
- autonomous controller;
- enterprise integrations;
- advanced orchestration hierarchies;
- non-feature workflows.

## Current Reading Order

### Implementers

1. `ARCHITECTURE.md`
2. `planning/MASTER-ROADMAP.md`
3. `planning/RUNTIME-SPEC.md`
4. `planning/DEPENDENCY-GRAPH.md`
5. `planning/TOOLING-AND-WORKFLOWS-SPEC.md`
6. `planning/QUALITY-AND-VALIDATION.md`
7. `planning/execution/PHASE-1.md`

### Reference Docs

These docs are useful only when interpreted through the MVP baseline:

| Area | Docs |
|---|---|
| Architecture | `architecture/` |
| Execution | `execution/` |
| Runtime state | `runtime/` |
| MCP/tooling | `mcps/` |
| Workflows | `workflows/` |
| References | `references/` |

### Archived Brainstorming

The `docs/brainstorming/` files are explicitly non-authoritative and may contain
rejected or speculative systems.

## Readiness Rule

A subsystem is not implemented because a file exists. It is implemented only
when it is initialized by runtime, called by the authoritative execution path,
can affect accept/reject behavior where relevant, persists required state, and
has integration tests for success and failure.
