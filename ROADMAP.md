# Foundry Roadmap

> Priority: make `build` work end-to-end reliably. Everything else follows.

---

## Phase 1: End-to-End Build Loop (NOW)

**Goal:** A user says "build X" and Foundry autonomously delivers working, validated code.

```
requirements → planning → implementation → validation → retries → recovery → working output
```

| Task | Module | Status |
|---|---|---|
| Wire SDLC loop end-to-end | `engine/orchestrator.py` + `engine/phase_graph.py` | Modules exist, needs integration |
| Connect tool gates after coding | `runtime/tool_gate.py` | Module exists, needs wiring |
| Checkpoint after each phase transition | `runtime/enhanced_checkpoint.py` | Module exists, needs wiring |
| Recovery from crash → restore from checkpoint | `engine/recovery_engine.py` | Module exists, needs wiring |
| Budget enforcement (stop runaway execution) | `runtime/budget_controller.py` | Module exists, needs wiring |
| MCP server serves tools to host agent | `runtime/app.py` | Working |
| Foundry installer bundles Python runtime | `foundry/install/install.js` | Needs update |

**Success criteria:** Given a natural language requirement, Foundry produces code that passes lint, types, and tests — autonomously, with no human intervention during execution.

---

## Phase 2: Reliability (SOON)

**Goal:** The build loop handles failures gracefully without human rescue.

| Task | Module |
|---|---|
| Retry escalation on failures | `engine/retry_policy.py` |
| Replanning when stuck | `engine/replanner.py` |
| Rollback to last-green on unrecoverable | `runtime/rollback_manager.py` |
| State persistence across sessions | `runtime/state_manager.py` + SQLite |
| GitHub adapter (create PRs, respond to reviews) | New: `adapters/github.py` |
| Review debate integration | `engine/reviewer_debate.py` |

**Success criteria:** Foundry recovers from tool failures, model errors, and test regressions without human intervention. Execution is resumable after crashes.

---

## Phase 3: Reasoning Quality (LATER)

**Goal:** Improve the quality of generated code through structured reasoning.

| Task | Module |
|---|---|
| Confidence gating (reject low-quality outputs) | `engine/confidence_gate.py` |
| Judge hierarchy during review | `engine/judge_hierarchy.py` |
| Context harvesting for smarter prompts | `engine/context_harvester.py` |
| Error memory (learn from past failures) | `runtime/memory_store.py` |
| Drift detection (catch specification drift) | `engine/drift_detector.py` |

**Success criteria:** Code quality improves measurably. Fewer retry cycles. Debates catch real issues.

---

## Phase 4: Scalability (FUTURE)

**Goal:** Handle larger projects, multiple repos, and longer autonomous runs.

| Task | Module |
|---|---|
| Tool gateway with MCP routing/fallback | New: `runtime/tool_gateway.py` |
| Observability dashboard | `runtime/dashboard.py` + `runtime/tracing.py` |
| Prompt registry (versioned, replay-safe) | `engine/prompt_registry.py` |
| Multi-project support | New architecture work |
| Docker-sandboxed execution | MCP integration |

---

## Deferred Indefinitely

These are expansion points, not requirements:

| Category | Reason to defer |
|---|---|
| Distributed execution | No multi-node scenario exists |
| Chaos/simulation testing | System must work first |
| Compliance/governance frameworks | No enterprise customers |
| Learning/adaptation engines | Premature optimization |
| 30+ memory/validator/security types | Methods on existing modules suffice |
| Enterprise integrations (Jira, Slack, etc.) | Only if users request |

---

## MCP Integration Timeline

| Tier | MCPs | When |
|---|---|---|
| **Tier 1 (Now)** | filesystem, shell, git | Available via host agent tools |
| **Tier 2 (Phase 1)** | github, docker | PR workflows + sandboxed execution |
| **Tier 3 (Phase 3+)** | postgres, playwright/browser | Persistent memory + research |
| **Tier 4 (Phase 4+)** | qdrant, brave-search | Semantic retrieval |
| **Tier 5 (On-demand)** | jira, linear, slack, terraform | Enterprise requests only |

---

## Architecture Validation Criteria

The architecture is validated when this sequence works autonomously:

1. User provides natural language requirements
2. Foundry generates a specification (SPEC phase)
3. Foundry decomposes into a dependency-ordered plan (PLAN phase)
4. Foundry implements each task via subagent prompts (CODE phase)
5. Tool gates validate: lint → types → tests → coverage (TEST phase)
6. If validation fails: retry with escalation, then replan, then rollback
7. If validation passes: structured review debate (REVIEW phase)
8. Output: working implementation + completion report (DONE)
9. All of this is checkpoint-recoverable and budget-bounded
