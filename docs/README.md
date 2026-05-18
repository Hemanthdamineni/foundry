# Foundry Documentation

> Production-grade technical documentation for the Foundry autonomous engineering runtime.

---

## Document Index

### Architecture

| Document | Lines | Purpose |
|---|---|---|
| [System Architecture](architecture/system-architecture.md) | ~350 | 6-layer architecture, subsystem dependency graphs, configuration, security model, performance |
| [Subsystem Boundaries](architecture/subsystem-boundaries.md) | ~450 | Exhaustive per-module ownership, interfaces, invariants, prohibited cross-concerns |

### Orchestration

| Document | Lines | Purpose |
|---|---|---|
| [Lifecycle & Orchestration](orchestration/lifecycle.md) | ~530 | Phase graphs, SDLC lifecycle, execution policy, 5-level retry, debate protocol, consensus, confidence gating, authority governance, replanning |

### Runtime

| Document | Lines | Purpose |
|---|---|---|
| [State & Recovery](runtime/state-and-recovery.md) | ~530 | Atomic state persistence, versioned checkpoint chains, replay, budget enforcement, execution determinism, rollback safety, memory, write queue, observability |

### Execution

| Document | Lines | Purpose |
|---|---|---|
| [Validation & Tools](execution/validation-and-tools.md) | ~380 | MCP server bootstrap, 14-tool surface, submit flow, tool gates, LLM providers, model routing, workspace indexing, MCP tiering |

### Memory

| Document | Lines | Purpose |
|---|---|---|
| [Memory Architecture](memory/memory-architecture.md) | ~330 | Acervo storage backend, Engram model, structured retrieval, error pattern matching, memory adapter, lifecycle management |

### Prompts

| Document | Lines | Purpose |
|---|---|---|
| [Prompting Architecture](prompts/prompting-architecture.md) | ~320 | Phase prompts, judge prompt locking, debate prompts, prompt registry with versioning, compatibility management, model routing, anti-patterns |

### Governance

| Document | Lines | Purpose |
|---|---|---|
| [Security & Safety](governance/security-and-safety.md) | ~320 | Authority model, trust boundaries, threat model, sandboxing, runtime policies, validation system, auditability, failure safety analysis |

### Observability

| Document | Lines | Purpose |
|---|---|---|
| [Tracing & Debugging](observability/tracing-and-debugging.md) | ~330 | JSONL tracing architecture, span model, retention policy, telemetry schema, debugging workflows, metrics, replay analysis |

### Workflows

| Document | Lines | Purpose |
|---|---|---|
| [Workflow Reference](workflows/workflow-reference.md) | ~280 | Build/debug/review/research workflows, subsystem activation matrices, MCP tool sequences, get_next_action schema, installation bootstrap |

### Development

| Document | Lines | Purpose |
|---|---|---|
| [Contributing](development/contributing.md) | ~350 | Repository structure, dev setup, coding standards, debugging flows, adding components, known tradeoffs, technical debt |

### Roadmap

| Document | Lines | Purpose |
|---|---|---|
| [Evolution](roadmap/evolution.md) | ~290 | 4-phase implementation roadmap, deferred systems, kill list, expansion points, research ideas, deployment concepts |

### References

| Document | Lines | Purpose |
|---|---|---|
| [Glossary & Schemas](references/glossary-and-schemas.md) | ~380 | Glossary (50+ terms), 10 runtime invariants, state machine diagrams (Mermaid), all Pydantic model schemas, exception hierarchy, file format reference |

### Brainstorming (Archived)

| Document | Purpose |
|---|---|
| [ARCHITECHTRE.md](brainstorming/ARCHITECHTRE.md) | Original exploratory architecture draft (raw, unreviewed) |
| [SKILLS.md](brainstorming/SKILLS.md) | Original skill system brainstorm (500+ concepts, mostly rejected) |
| [MCPS.md](brainstorming/MCPS.md) | Original MCP integration brainstorm (raw) |

---

## Reading Order

### New Contributors
1. [System Architecture](architecture/system-architecture.md) — Understand the design
2. [Contributing](development/contributing.md) — Set up your environment
3. [Lifecycle & Orchestration](orchestration/lifecycle.md) — Understand the core loop
4. [Glossary & Schemas](references/glossary-and-schemas.md) — Learn the vocabulary

### Runtime Developers
1. [Subsystem Boundaries](architecture/subsystem-boundaries.md) — Module ownership rules
2. [State & Recovery](runtime/state-and-recovery.md) — Persistence internals
3. [Validation & Tools](execution/validation-and-tools.md) — MCP and tool details
4. [Tracing & Debugging](observability/tracing-and-debugging.md) — Debugging workflows

### Quality/Safety Engineers
1. [Security & Safety](governance/security-and-safety.md) — Governance model
2. [Lifecycle & Orchestration](orchestration/lifecycle.md) — Debate and consensus
3. [Prompting Architecture](prompts/prompting-architecture.md) — Prompt locking and safety

### Product/Planning
1. [System Architecture](architecture/system-architecture.md) — What exists today
2. [Workflow Reference](workflows/workflow-reference.md) — User-facing behaviors
3. [Evolution](roadmap/evolution.md) — Where it's going

---

## Project Overview

Foundry is a **deterministic, recoverable autonomous engineering runtime**. It transforms natural language engineering intent into working, validated code through:

- A **6-phase SDLC lifecycle** (Specs → Planning → Coding → Testing → Review → Done)
- **Structured multi-agent debate** for quality review
- **Sequential validation gates** (lint → types → tests → coverage → security)
- **Graduated retry escalation** (local → phase → structural → full recovery)
- **Checkpoint-recoverable execution** with versioned rollback chains
- **Budget-bounded autonomy** (token, time, retry hard ceilings)

The system exposes this as an **MCP server** — a set of tools that a host AI agent calls to drive the lifecycle. Users interact with high-level workflows (`build`, `debug`, `review`); all orchestration complexity is hidden.

### Documentation Stats

| Metric | Value |
|---|---|
| Total documents | 13 (+ 3 archived brainstorming) |
| Total documentation lines | ~4,900+ |
| Runtime modules documented | All 45+ Python files |
| Data models documented | All 30+ Pydantic models |
| Subsystem boundaries specified | All 20+ modules |
| State machines diagrammed | 4 (task, phase, graph, recovery) |
| Debugging workflows | 4 (transition failure, stuck task, state corruption, audit) |
| Workflow types covered | 4 (build, debug, review, research) |

### Architecture at a Glance

```
User → Workflow → Orchestration → Execution → Tool Gateway → MCPs
                                                              │
                          ┌───────────────────────────────────┘
                          │
                    filesystem, shell, git, github, docker
```

**Cross-cutting:** State & Memory, Observability

**Invariants:**
1. Users see workflows, not internals
2. Validation-first execution
3. Checkpoint-recoverable
4. Budget-bounded
5. Disk is truth
6. Single orchestrator, not agent swarm
7. Prompts locked per task
8. State writes are atomic
9. Rollback never corrupts stable phases
10. Authority is centralized
