# Foundry Architecture

> Autonomous engineering runtime for deterministic, recoverable software delivery.

---

## Core Principle

```
Users invoke workflows → Runtime hides complexity
```

Users interact with **outcomes** (`build`, `debug`, `review`).
The runtime internally manages orchestration, validation, retries, memory, governance, recovery, and tooling.

---

## System Layers

```
┌─────────────────────────────────────┐
│  USER LAYER                         │
│  Capabilities: build, debug, review │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  ORCHESTRATION LAYER                │
│  SDLC lifecycle, planning,         │
│  reasoning, budgets, retry          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  EXECUTION LAYER                    │
│  Code generation, validation,       │
│  workspace, patching, sandbox       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  TOOL GATEWAY                       │
│  Route → Policy → Execute → Validate│
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  MCP LAYER                          │
│  filesystem, shell, git, github,    │
│  docker                             │
└─────────────────────────────────────┘

Cross-cutting:
  ├── State & Memory (persistence, checkpoints, recovery)
  └── Observability (tracing, telemetry)
```

---

## Runtime Subsystems

### Orchestration (The Brain)

Controls the entire lifecycle. Reasoning (debate, judging, confidence) lives here as orchestration internals, not a separate layer.

| Module | Responsibility | File |
|---|---|---|
| SDLC Controller | Phase lifecycle FSM (SPEC→PLAN→CODE→TEST→REVIEW→DONE) | `engine/orchestrator.py` + `engine/phase_graph.py` |
| Planner | Task decomposition, dependency DAG, scheduling | `engine/dependency_graph.py` + `engine/hierarchical_graph.py` |
| Replanner | Recovery replanning when execution stalls | `engine/replanner.py` + `engine/recovery_engine.py` |
| Budget Controller | Token/time/retry budget enforcement | `runtime/budget_controller.py` |
| Debate Engine | Multi-round structured review with convergence | `engine/debate_runtime.py` + `engine/reviewer_debate.py` |
| Judge System | Hierarchical validation (tool → semantic → architecture) | `engine/judge.py` + `engine/judge_hierarchy.py` |
| Confidence Gate | Threshold enforcement + drift detection | `engine/confidence_gate.py` + `engine/drift_detector.py` |
| Retry Policy | 5-level graduated escalation | `engine/retry_policy.py` |

### Execution (Code Production)

Produces and validates code. Will grow over time to absorb workspace management, patch application, branch isolation, sandbox execution, and artifact handling.

| Module | Responsibility | File |
|---|---|---|
| MCP Server | Tool interface for host agent | `runtime/app.py` |
| Validator / Tool Gate | Sequential gate enforcement (lint→types→test→coverage→security) | `runtime/tool_gate.py` + `validators/` |
| Tool Executor | Reliable tool calls with timeout/retry/normalization | `runtime/tool_executor.py` |
| Execution Runtime | Deterministic execution context + replay-safe IDs | `runtime/execution_runtime.py` |

### State & Memory

| Module | Responsibility | File |
|---|---|---|
| State Manager | Canonical runtime state (disk is truth) | `runtime/state_manager.py` |
| Memory Store | Persistent knowledge + retrieval | `runtime/memory_store.py` + `runtime/store_sqlite.py` |
| Checkpoint Manager | Crash-safe atomic snapshots + recovery | `runtime/enhanced_checkpoint.py` |
| Rollback Manager | Git-coordinated, phase-safe rollback | `runtime/rollback_manager.py` |

### Observability

| Module | Responsibility | File |
|---|---|---|
| Tracing | OpenTelemetry spans for execution visibility | `runtime/tracing.py` |
| Dashboard | Runtime telemetry and phase timelines | `runtime/dashboard.py` |

### Tool Gateway

The runtime never calls MCPs directly. All external tool access flows through:

```
orchestrator → tool_router → policy_check → tool_executor → MCP → validate_output
```

This gives: replaceable MCPs, vendor independence, fallback support, centralized governance.

---

## Package Structure

```
foundry/                          # npx-installable package
├── skills/sdlc/SKILL.md          # Agent instructions
├── prompts/                      # Subagent prompt templates
├── install/                      # Bootstrap (installs skills + Python runtime)
└── agents/                       # Agent configurations

sdlc/                             # Python runtime (installed by foundry)
├── engine/                       # Orchestration + Reasoning
│   ├── orchestrator.py           # SDLC phase controller
│   ├── phase_graph.py            # FSM transitions
│   ├── dependency_graph.py       # Task DAG
│   ├── debate_runtime.py         # Structured debate
│   ├── reviewer_debate.py        # Review-specific debate
│   ├── judge.py                  # Base judge
│   ├── judge_hierarchy.py        # Multi-layer validation
│   ├── confidence_gate.py        # Threshold enforcement
│   ├── consensus.py              # Agreement synthesis
│   ├── drift_detector.py         # Specification drift
│   ├── replanner.py              # Recovery replanning
│   ├── retry_policy.py           # Graduated retry
│   ├── recovery_engine.py        # Crash recovery
│   ├── orchestrator_runtime.py   # Authority enforcement
│   └── ...
├── runtime/                      # State + Execution
│   ├── app.py                    # MCP server
│   ├── state_manager.py          # Canonical state
│   ├── memory_store.py           # Persistent memory
│   ├── enhanced_checkpoint.py    # Atomic checkpoints
│   ├── budget_controller.py      # Resource budgets
│   ├── tool_gate.py              # Validation sequence
│   ├── tool_executor.py          # Reliable tool calls
│   ├── rollback_manager.py       # Git-safe rollback
│   ├── execution_runtime.py      # Deterministic execution
│   ├── tracing.py                # OpenTelemetry
│   └── ...
└── validators/                   # Validation logic
```

---

## Architectural Invariants

These are permanent design decisions that must not be violated:

| Invariant | Rule |
|---|---|
| Users see workflows, not internals | Never expose orchestration, validators, retries, debate, or memory to users |
| Validation-first execution | Tool gates are law — no phase advances without passing gates |
| Deterministic phase transitions | Phase graph FSM enforces legal transitions only |
| Checkpoint-recoverable execution | Every phase transition creates an atomic checkpoint |
| Budget-bounded execution | Token/time/retry budgets are hard ceilings, never advisory |
| Tool gateway abstraction | No module directly calls an MCP — always route through tool gateway |
| Disk is truth | State manager is canonical — memory/runtime state derives from disk |
| Reasoning is orchestration | Debate, judging, confidence are orchestration internals, not separate layers |

---

## What This System Is NOT

- **Not a microservices platform** — it's a single-process runtime
- **Not a multi-agent system** — it's one agent (Foundry) with internal behavioral modes
- **Not an enterprise governance framework** — it's an engineering execution engine
- **Not a distributed system** — single-node, single-process, deterministic
- **Not a platform for platform builders** — it's a tool for shipping code
