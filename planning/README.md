# Foundry Implementation Program

> Authoritative execution blueprint for the Foundry runtime integration effort.

This planning system now treats the adversarial architecture audit as the
baseline. A file existing is not implementation. A module passing unit tests is
not runtime readiness. A subsystem is only implemented when it is wired into the
authoritative execution path and verified end-to-end.

## Authoritative Runtime Path

All near-term work must strengthen one operational loop:

```
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> persistence
  -> recovery
```

The architecture remains:

```
User Workflows -> Orchestration Runtime -> Execution Runtime -> Tool Gateway -> MCP Ecosystem
```

Do not add subsystems, agent layers, workflow families, dashboards, memory
systems, or speculative orchestration until this loop is operational.

## Navigation

| Document | Role |
|---|---|
| `MASTER-ROADMAP.md` | Current status, MVP boundary, implementation phases, priorities |
| `RUNTIME-SPEC.md` | Authoritative runtime contract and operational semantics |
| `TOOLING-AND-WORKFLOWS-SPEC.md` | Tool execution, validation gate, and feature workflow requirements |
| `DEPENDENCY-GRAPH.md` | Integration dependency order, blockers, deferred systems |
| `QUALITY-AND-VALIDATION.md` | Acceptance tests and readiness gates |
| `execution/` | Concrete phase-by-phase implementation tasks and MVP completion gates |

## Status Legend

| Status | Meaning |
|---|---|
| `file exists` | Code file/module exists, but is not necessarily used |
| `scaffolded` | Local API exists and may have unit tests; not on runtime path |
| `partially wired` | Called by runtime, but missing critical integration or recovery semantics |
| `operationally integrated` | On authoritative runtime path and covered by integration tests |
| `production-ready` | Operational, failure-tested, observable, recoverable, and bounded |
| `deferred` | Explicitly out of MVP scope |
| `non-operational concept` | Documentation or code shape exists, but no useful runtime behavior |

## Priority System

| Priority | Meaning |
|---|---|
| P0 | Blocks the single deterministic execution loop |
| P1 | Required for MVP reliability |
| P2 | Required after MVP before production use |
| P3 | Deferred enhancement |
| PX | Removed from current implementation program |

## MVP Boundary

MVP includes only:

- feature workflow
- deterministic FSM
- single submit pipeline
- authoritative validation gate
- ToolExecutor integration
- ToolGate enforcement
- checkpoint restore/resume
- bounded retry handling
- SQLite task authority
- recovery correctness

MVP explicitly excludes:

- distributed execution
- advanced memory
- dashboards
- multi-agent systems beyond optional judge/debate internals
- autonomous controllers
- advanced replay
- confidence analytics
- enterprise integrations

## Implementation Phases

```
Phase 0 [NOW]:    Baseline correction and status truth
Phase 1 [NOW]:    Single authoritative submit pipeline
Phase 2 [NEXT]:   ToolExecutor + ToolGate validation enforcement
Phase 3 [NEXT]:   Checkpoint restore/resume + bounded retry handling
Phase 4 [MVP]:    One feature workflow validated end-to-end
Phase 5 [POST]:   Hardening, observability, and production reliability
Phase 6 [DEFER]:  Memory, dashboards, replay, extra workflows, integrations
```

Any roadmap item that does not improve the authoritative runtime path is
deferred until after Phase 4.
