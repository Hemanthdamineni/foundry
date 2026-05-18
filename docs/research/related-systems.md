# Related Systems

> Comparison to existing AI coding agents and agent frameworks, what Foundry learned from each, and where Foundry intentionally diverges.

---

## Comparison Matrix

| Feature | Foundry | Devin | SWE-Agent | OpenHands | AutoGPT | Aider |
|---|---|---|---|---|---|---|
| Execution model | Phase FSM | Free-form | Turn-based | Free-form | Recursive | Turn-based |
| Validation | Schema + Judge + Debate | Manual review | Tool output | Tool output | Self-eval | Tool output |
| Recovery | 5-level escalation | Manual | Retry only | Retry only | Retry only | None |
| State persistence | SQLite + JSON + Checkpoints | Cloud state | None | None | File-based | Git |
| Budget enforcement | Hard ceilings | API limits | Iteration cap | Iteration cap | Token limit | None |
| Determinism | Orchestration-level | None | None | None | None | None |
| Local-first | ✓ (Ollama default) | ✗ (Cloud) | ✗ (API) | ✓ | ✗ (API) | ✓ |
| Prompt locking | ✓ Per-task | ✗ | ✗ | ✗ | ✗ | ✗ |
| Replay | ✓ Trace + checkpoint | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## What We Learned

### From SWE-Agent

**Lesson:** Simple tool interfaces outperform complex ones. SWE-Agent's `edit`, `search`, `scroll` commands are more reliable than free-form file editing.

**Applied:** Foundry constrains tool access per phase. Only Coding and Testing phases can edit files and run shell commands. Other phases are read-only.

### From Devin

**Lesson:** Full autonomy requires significant infrastructure for recovery and verification. Devin's cloud-based approach enables long-running tasks but makes debugging opaque.

**Applied:** Foundry provides full auditability via traces, checkpoints, and authority logs. Every decision is recorded and replayable.

### From AutoGPT

**Lesson:** Recursive self-improvement loops are dangerous. Without budget constraints, agents loop indefinitely. Self-evaluation is unreliable.

**Applied:** Hard budget ceilings (invariant I3). No self-modification of prompts (invariant I8). External validation via schema checks and tool gates.

### From Aider

**Lesson:** Git-integrated code editing with diff-based output is effective for small changes. Turn-based interaction keeps the human in the loop.

**Applied:** Foundry's phase model provides a middle ground — autonomous execution within validated phases, with optional human approval gates at phase boundaries.

### From LangChain/LangGraph

**Lesson:** Framework abstraction adds significant overhead for simple LLM call patterns. Graph-based execution is powerful but hard to debug.

**Applied:** Direct `httpx` calls instead of framework wrappers. Validated phase graphs instead of arbitrary graph traversal.

---

## Key Differentiators

### 1. Validated Phase Execution

No other system provides deterministic structural validation before LLM-based evaluation. Schema checks catch structural problems that LLMs would miss or hallucinate away.

### 2. Debate-Augmented Quality Control

Multi-agent debate with consensus and collapse detection is unique to Foundry. Other systems use single-pass evaluation or no evaluation at all.

### 3. Checkpoint-Based Recovery

No other open-source coding agent provides versioned checkpoint chains with stable work preservation during rollback.

### 4. Budget-Bounded Execution

While other systems have iteration caps, Foundry enforces multi-dimensional budgets (tokens, time, retries, debate tokens) with graduated violation severities.

### 5. Prompt Locking

Freezing evaluation criteria per task ensures reproducible assessment. No other system provides this guarantee.
