# Deferred Systems

> Systems that were evaluated and intentionally deferred, with rationale for why they were not implemented and conditions under which they should be reconsidered.

---

## Kill List: Rejected Concepts

These were proposed in the original architecture brainstorming and explicitly rejected:

### Multi-Agent Swarm Orchestration

**Proposed:** Independent agent processes (researcher, coder, reviewer, tester) communicating via message passing.

**Rejected because:** Coordination overhead exceeded benefits. State synchronization between independent agents is harder than single-orchestrator behavioral modes. Recovery from one agent's crash requires distributed consensus.

**Reconsider when:** The system needs true parallel execution of independent subtasks across different codebases.

### Embedding-Based Code Retrieval

**Proposed:** Vector embeddings for semantic code search using ChromaDB/FAISS.

**Rejected because:** Code embedding quality is unreliable (variable names carry disproportionate weight). Structural indexing (imports, dependents) is more predictable. Adds GPU dependency or significant CPU overhead.

**Reconsider when:** Code-specific embedding models (CodeBERT, StarCoder embeddings) mature to reliable accuracy on dependency resolution tasks.

### Autonomous Skill Discovery

**Proposed:** Runtime that automatically discovers, installs, and composes skills from a marketplace.

**Rejected because:** Trust boundary violation. Autonomous tool installation introduces supply chain risk. Manual skill registration is safer and more predictable.

**Reconsider when:** A verified skill registry with cryptographic signing exists.

### Recursive Self-Improvement

**Proposed:** Agent modifies its own prompts and configuration to improve performance over time.

**Rejected because:** Prompt self-modification creates unpredictable behavior. A system that changes its own evaluation criteria cannot be audited. Prompt locking (invariant I8) explicitly prevents this.

**Reconsider when:** Never. This violates core design philosophy.

### Dynamic Phase Graph Generation

**Proposed:** LLM generates custom phase graphs per task instead of using fixed templates.

**Rejected because:** Generated phase graphs cannot be validated for correctness (cycles, unreachable states) without executing them. Fixed templates with validated structure provide predictable execution.

**Reconsider when:** A formal verification system for generated graphs is available.

---

## Deferred Implementations

These are planned but not yet prioritized:

### Bugfix and Review Phase Graphs

**What:** YAML graph templates for `bugfix` (Chatting→Debugging→Coding→Testing→Done) and `review` (Chatting→Review→Done) workflows.

**Status:** Phase graph infrastructure supports multiple templates. Only `feature.yaml` exists.

**Effort:** Low — write YAML files, register in config.

### ToolGate ↔ submit_output Integration

**What:** Wire the ToolGate validation sequence into the submit_output flow so that tool-based validation (lint, type check, test) runs automatically before judge evaluation.

**Status:** ToolGate exists with all adapters. submit_output calls schema checks and judge. Missing: insert ToolGate between schema checks and judge.

**Effort:** Medium — modify `tools/phase.py` to invoke ToolGate.

### Distributed Replay

**What:** Share replay sessions across machines for collaborative debugging.

**Status:** ReplayEngine loads from local traces/checkpoints only.

**Effort:** High — requires serializable replay sessions, network transport, session synchronization.

### Multi-Model Debate

**What:** Use different models for different debate agents (e.g., Agent A uses GPT-4o, Agent B uses Claude, Agent C uses Qwen).

**Status:** ModelRouter supports per-role overrides. DebateRuntime uses a single provider for all agents.

**Effort:** Medium — modify DebateRuntime to accept per-agent provider/model configuration.

### Budget Statistics API

**What:** Expose budget consumption statistics via an MCP tool for real-time monitoring.

**Status:** BudgetController tracks all stats. No MCP tool exposes them.

**Effort:** Low — add `sdlc_get_budget_stats` tool.

---

## Conditions for Promotion

A deferred system should be promoted to active development when:

1. **A concrete use case exists** — not speculative, an actual workflow is blocked
2. **The infrastructure supports it** — dependency modules are stable
3. **The effort is justified** — benefit outweighs implementation + maintenance cost
4. **It doesn't violate invariants** — all 10 design invariants remain intact
