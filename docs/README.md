# Foundry Documentation

> Production-grade technical documentation for the Foundry autonomous engineering runtime.

---

## Quick Navigation

| Document | Purpose | Audience |
|---|---|---|
| [System Architecture](architecture/system-architecture.md) | Layers, subsystems, boundaries, invariants, security, performance | Architects, contributors |
| [Orchestration & Lifecycle](orchestration/lifecycle.md) | Phase graphs, SDLC lifecycle, debate, consensus, retry, replanning | Runtime developers |
| [Runtime & State](runtime/state-and-recovery.md) | State persistence, checkpoints, recovery, budgets, determinism, memory | Runtime developers |
| [Execution & Validation](execution/validation-and-tools.md) | MCP server, tool gates, LLM providers, workspace indexing | Integration developers |
| [Development Guide](development/contributing.md) | Repo structure, coding standards, debugging, tradeoffs | Contributors |
| [Roadmap & Evolution](roadmap/evolution.md) | Phases, deferred systems, expansion points, research, deployment | Product planning |

---

## Reading Order

**For new contributors:**
1. [System Architecture](architecture/system-architecture.md) — Understand the overall design
2. [Development Guide](development/contributing.md) — Set up your environment
3. [Orchestration & Lifecycle](orchestration/lifecycle.md) — Understand the core loop

**For runtime developers:**
1. [System Architecture](architecture/system-architecture.md) — Layers and boundaries
2. [Runtime & State](runtime/state-and-recovery.md) — State management internals
3. [Execution & Validation](execution/validation-and-tools.md) — MCP and tool details

**For product/planning:**
1. [System Architecture](architecture/system-architecture.md) — What exists today
2. [Roadmap & Evolution](roadmap/evolution.md) — Where it's going

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

### Key Stats

| Metric | Value |
|---|---|
| Runtime modules | ~45 Python files |
| Orchestration subsystems | 12 |
| Lines of runtime code | ~6,500 |
| Data models | 30+ Pydantic models |
| MCP tools | 14 |
| Configuration files | 5 YAML files |
| Phase graph templates | 1 (feature), planned: 5 |
| LLM providers | 2 (Ollama, OpenAI) |

---

## Architecture at a Glance

```
User → Workflow → Orchestration → Execution → Tool Gateway → MCPs
                                                              │
                          ┌───────────────────────────────────┘
                          │
                    filesystem, shell, git, github, docker
```

**Cross-cutting:** State & Memory, Observability

**Invariants:**
- Users see workflows, not internals
- Validation-first execution
- Checkpoint-recoverable
- Budget-bounded
- Disk is truth
- Single orchestrator, not agent swarm
