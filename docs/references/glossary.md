# Glossary

> Definitions for all domain-specific terms used throughout Foundry documentation and source code.

---

| Term | Definition |
|---|---|
| **Acervo** | JSONL-based memory storage engine. Stores tagged `Engram` entries for cross-task pattern retrieval. |
| **Authority** | Centralized decision point (`OrchestratorAuthority`) that approves or rejects all runtime actions. |
| **Back-edge** | Phase graph edge that goes backward (e.g., Testing→Coding), creating retry loops. |
| **Budget ceiling** | Hard maximum for a resource dimension (tokens, time, retries). Hitting a ceiling aborts the task. |
| **Budget controller** | `BudgetController` — tracks token consumption, time elapsed, retry counts, and enforces ceilings. |
| **Capability** | `ToolCapability` enum value (LINT, TYPING, TESTING, etc.) that abstracts tool identity. |
| **Checkpoint** | Serialized snapshot of task state at a phase transition. Used for crash recovery and replay. |
| **Checkpoint chain** | Versioned sequence of checkpoints for a single task (v1, v2, ..., vN). |
| **Collapse** | Sycophantic collapse — debate agents agreeing without genuine independent analysis. |
| **Confidence gate** | `ConfidenceGate` — translates votes with confidence scores into binary approve/reject decisions. |
| **Consensus** | `ConsensusEngine` — synthesizes debate results into a collective verdict. |
| **Context chunk** | A segment of code (symbol-level or line-range) included in the agent's execution context. |
| **Context harvester** | `ContextHarvester` — gathers project structure and dependencies before specification phase. |
| **Debate** | Multi-agent quality review protocol. 3 rounds: independent → deliberation → final positions. |
| **Debate agent** | An LLM call with a role-specific prompt that evaluates output quality during debate. |
| **Dependency graph** | `DependencyGraph` — directed graph of file import relationships and symbol definitions. |
| **Determinism** | Property of producing the same behavior given the same inputs. Foundry guarantees orchestration determinism, not output determinism. |
| **Drift** | Unintended change in system behavior. Spec drift = scope changes. Prompt drift = prompt edits. Architecture drift = layer violations. |
| **Engram** | A tagged memory unit stored in Acervo. Contains content, tags, task reference, and metadata. |
| **Escalation** | Moving from a cheaper recovery level to a more expensive one (e.g., retry → replan). |
| **Execution policy** | `ExecutionPolicy` — decides whether to retry, escalate, or abort based on failure type and budget. |
| **Execution snapshot** | `ExecutionSnapshot` — captures deterministic configuration (graph hash, prompt hashes, model versions) at a point in time. |
| **Fail-closed** | Failure behavior where the system blocks/rejects on error. Used for schema checks and budget enforcement. |
| **Fail-open** | Failure behavior where the system allows/passes on error. Used for LLM judge when unavailable. |
| **FSM** | Finite State Machine. The `OrchestratorFSM` manages phase transitions. |
| **Gate** | A validation checkpoint in the ToolGate sequence (e.g., lint gate, test gate). |
| **Host agent** | The AI agent (e.g., OpenCode) that connects to Foundry as an MCP client and executes phases. |
| **Impact analysis** | Assessment of which files are affected by changes to a set of files, using dependency graph edges. |
| **Index pipeline** | `IndexPipeline` — manages workspace file indexing (full, incremental, targeted). |
| **Invariant** | A property that must hold at all times. Foundry has 10 design invariants. |
| **Judge** | `JudgeEngine` — LLM-based quality evaluator that produces pass/fail verdicts for phase outputs. |
| **Judge hierarchy** | `MultiJudge` — multiple specialized judges (Tool, Semantic, Security, Integration) with consensus gating. |
| **Locked prompt** | A judge prompt frozen at task creation time. Ensures consistent evaluation across the task's lifetime. |
| **MCP** | Model Context Protocol — the communication protocol between Foundry (server) and the host agent (client). |
| **Memory adapter** | `MemoryAdapter` — wraps Acervo behind the ToolAdapter interface. |
| **Minority report** | A dissenting view from a debate agent that disagreed with the majority verdict. Preserved for auditability. |
| **Model router** | `ModelRouter` — maps runtime roles (judge, debate, phase) to specific LLM provider + model combinations. |
| **Phase** | A named stage in the SDLC lifecycle (e.g., Specs, Planning, Coding, Testing, Review). |
| **Phase graph** | `PhaseGraph` — YAML-defined directed graph of phases with validated transitions. |
| **Phase record** | A historical entry recording a phase's output, verdict, and metadata. |
| **Prompt registry** | `PromptRegistry` — manages versioned prompt templates with hash-based deduplication. |
| **Recovery engine** | `RecoveryEngine` — classifies failures and determines the appropriate recovery level. |
| **Replay** | Re-execution of a task from stored traces or checkpoints for debugging/regression testing. |
| **Replanner** | `Replanner` — invalidates downstream phases while preserving stable work. |
| **Residual objection** | A concern raised in early debate rounds that persists through to the final round without resolution. |
| **Restore point** | A named bookmark within a checkpoint chain for semantic rollback targets. |
| **Rollback** | Reverting task state to a previous phase. `RollbackManager` ensures stable phases are protected. |
| **Schema check** | Deterministic validation that phase output contains required structural sections. |
| **Spec-lock** | Rule that specification content is frozen after approval. Downstream outputs are monitored for drift. |
| **Stable phase** | A phase explicitly marked as stable via `replanner.mark_stable()`. Protected from invalidation during replanning. |
| **Store backend** | `StoreBackend` ABC — persistence abstraction. Implemented by `SqliteStore`. |
| **Submit** | The act of submitting phase output for validation via `sdlc_submit_output`. |
| **Subagent** | The agent configuration (model + role) used for a specific phase. Not an independent process. |
| **Task** | A unit of work tracked by Foundry. Has an ID, description, mode, current phase, budget, and history. |
| **Tool adapter** | `ToolAdapter` ABC — interface for external tool integrations (lint, test, type check, etc.). |
| **Tool gate** | `ToolGate` — ordered sequence of validation gates with fail-fast semantics. |
| **Trace** | JSONL file recording execution spans (tool calls, phase transitions, verdicts) for debugging. |
| **Tracer** | `Tracer` — creates and manages trace spans with JSONL persistence. |
| **Verdict** | The pass/fail decision from a judge evaluation, with reason and confidence. |
| **Write op** | `WriteOp` — a queued state mutation (create task, save checkpoint, store memory). |
| **Write queue** | `WriteQueue` — async FIFO that decouples tool handlers from state persistence. |
