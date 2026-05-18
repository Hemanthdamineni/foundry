# Foundry Documentation

> Production-grade engineering knowledge base for the Foundry autonomous SDLC runtime.

---

## Document Index

### Architecture

| Document | Purpose |
|---|---|
| [System Architecture](architecture/system-architecture.md) | 6-layer architecture, subsystem dependency graphs, configuration, security model |
| [Subsystem Boundaries](architecture/subsystem-boundaries.md) | Per-module ownership, interfaces, invariants, prohibited cross-concerns |
| [Execution Model](architecture/execution-model.md) | Phase execution cycle, validation pipeline, budget enforcement, retry semantics, determinism |
| [Design Philosophy](architecture/design-philosophy.md) | Ten invariants, rejected alternatives, architectural constraints, design tensions |

### Orchestration

| Document | Purpose |
|---|---|
| [Lifecycle & Phases](orchestration/lifecycle-and-phases.md) | Phase graphs, FSM, SDLC lifecycle, transitions, approval gates, authority governance |
| [Debate & Consensus](orchestration/debate-and-consensus.md) | 3-round debate protocol, agent roles, consensus engine, collapse detection, confidence gating |
| [Recovery & Retries](orchestration/recovery-and-retries.md) | 5-level escalation, failure classification, replanning, rollback safety, effectiveness tracking |

### Runtime

| Document | Purpose |
|---|---|
| [State & Persistence](runtime/state-and-persistence.md) | Atomic state writes, SQLite WAL, checkpoint chains, write queue, crash recovery |
| [Determinism & Replay](runtime/determinism-and-replay.md) | Execution snapshots, prompt locking, replay engine, regression detection |
| [Budget & Resource Control](runtime/budget-and-resource-control.md) | Token tracking, time limits, debate budgets, violation severities, hard ceilings |

### Execution

| Document | Purpose |
|---|---|
| [Execution & Validation](execution/execution-and-validation.md) | MCP server, tool surface, submit flow, tool gates, LLM providers |
| [Model Routing & Providers](execution/model-routing-and-providers.md) | LLMProvider protocol, Ollama/OpenAI, ModelRouter, per-role routing |
| [Repository & Context Indexing](execution/repository-and-context-indexing.md) | IndexPipeline, DependencyGraphEngine, symbol extraction, context retrieval |

### Memory

| Document | Purpose |
|---|---|
| [Memory Architecture](memory/memory-architecture.md) | Acervo storage, Engram model, structured retrieval, lifecycle |
| [Retrieval & Context](memory/retrieval-and-context.md) | Context harvesting, error pattern matching, phase context aggregation |

### MCPs

| Document | Purpose |
|---|---|
| [MCP Architecture](mcps/mcp-architecture.md) | Server bootstrap, tool registration, lifespan, request context, communication model |
| [Tool Adapters & Gateway](mcps/tool-adapters-and-gateway.md) | ToolAdapter protocol, 10 concrete adapters, ToolGate validation, capability model |

### Governance

| Document | Purpose |
|---|---|
| [Security & Trust Model](governance/security-and-trust-model.md) | Trust boundaries, threat model, fail-open/fail-closed analysis |
| [Runtime Policies & Permissions](governance/runtime-policies-and-permissions.md) | Authority model, phase restrictions, sandbox, spec-lock enforcement |

### Prompts

| Document | Purpose |
|---|---|
| [Prompting Architecture](prompts/prompting-architecture.md) | Phase prompts, judge prompts, debate prompts, prompt lifecycle |
| [Prompt Versioning & Registry](prompts/prompt-versioning-and-registry.md) | PromptRegistry, hash dedup, version management, compatibility tracking |

### Workflows

| Document | Purpose |
|---|---|
| [Workflow Reference](workflows/workflow-reference.md) | Build/debug/review/research workflows, subsystem activation matrix |
| [Workflow Internals](workflows/workflow-internals.md) | MCP tool call sequences, response schemas, approval gates |

### Observability

| Document | Purpose |
|---|---|
| [Tracing & Debugging](observability/tracing-and-debugging.md) | JSONL span model, retention, 4 debugging workflows |
| [Metrics & Telemetry](observability/metrics-and-telemetry.md) | 17 logger categories, structured log schema, performance metrics |

### Development

| Document | Purpose |
|---|---|
| [Contributing](development/contributing.md) | Setup, coding standards, debugging workflows |
| [Repository Structure](development/repository-structure.md) | Full file tree, layer classification, config inventory |
| [Technical Debt & Tradeoffs](development/technical-debt-and-tradeoffs.md) | Known debt, accepted tradeoffs, migration paths, dependency inventory |

### Deployment

| Document | Purpose |
|---|---|
| [Installation & Configuration](deployment/installation-and-configuration.md) | NPX installer, Ollama setup, MCP registration, config reference, env vars |

### Roadmap

| Document | Purpose |
|---|---|
| [Evolution](roadmap/evolution.md) | 4-phase implementation roadmap, expansion points |
| [Deferred Systems](roadmap/deferred-systems.md) | Kill list rationale, deferred implementations, promotion conditions |
| [Future Research](roadmap/future-research.md) | Distributed runtime, advanced retrieval, multi-model evaluation, scaling |

### References

| Document | Purpose |
|---|---|
| [Glossary](references/glossary.md) | 55+ domain-specific term definitions |
| [Schemas & Contracts](references/schemas-and-contracts.md) | All Pydantic models, enums, file formats, exception hierarchy |
| [State Machines](references/state-machines.md) | Mermaid diagrams: task, phase, recovery, debate, write queue FSMs |
| [Runtime Invariants](references/runtime-invariants.md) | 10 non-negotiable invariants with enforcement and verification |

### Research

| Document | Purpose |
|---|---|
| [Related Systems](research/related-systems.md) | Comparison to Devin, SWE-Agent, OpenHands, AutoGPT, Aider |
| [Failed Approaches](research/failed-approaches.md) | 8 rejected designs with concrete rationale |

### Brainstorming (Archived)

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](brainstorming/ARCHITECHTRE.md) | Raw architecture brainstorming (unreviewed) |
| [SKILLS.md](brainstorming/SKILLS.md) | Raw skills brainstorming (unreviewed) |
| [MCPS.md](brainstorming/MCPS.md) | Raw MCP brainstorming (unreviewed) |

---

## Reading Orders

### New Contributor

1. [Design Philosophy](architecture/design-philosophy.md) — understand _why_
2. [System Architecture](architecture/system-architecture.md) — understand _what_
3. [Repository Structure](development/repository-structure.md) — understand _where_
4. [Execution Model](architecture/execution-model.md) — understand _how_
5. [Contributing](development/contributing.md) — start working

### Runtime Engineer

1. [Execution Model](architecture/execution-model.md)
2. [Lifecycle & Phases](orchestration/lifecycle-and-phases.md)
3. [State & Persistence](runtime/state-and-persistence.md)
4. [MCP Architecture](mcps/mcp-architecture.md)
5. [Determinism & Replay](runtime/determinism-and-replay.md)

### Quality / Validation

1. [Execution & Validation](execution/execution-and-validation.md)
2. [Debate & Consensus](orchestration/debate-and-consensus.md)
3. [Recovery & Retries](orchestration/recovery-and-retries.md)
4. [Budget & Resource Control](runtime/budget-and-resource-control.md)

### Operations / Debugging

1. [Installation & Configuration](deployment/installation-and-configuration.md)
2. [Tracing & Debugging](observability/tracing-and-debugging.md)
3. [Metrics & Telemetry](observability/metrics-and-telemetry.md)
4. [Technical Debt & Tradeoffs](development/technical-debt-and-tradeoffs.md)

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
1. Disk is truth
2. Validation-first execution
3. Budget ceilings are absolute
4. Phase transitions are validated
5. Rollback never corrupts stable phases
6. Checkpoint-recoverable
7. Single orchestrator, not agent swarm
8. Prompts locked per task
9. State writes are atomic
10. Authority is centralized
