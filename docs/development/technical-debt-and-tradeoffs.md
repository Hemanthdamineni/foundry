# Technical Debt and Tradeoffs

> Known debt items, accepted tradeoffs, migration paths, and architectural risks.

---

## Accepted Tradeoffs

### 1. Fail-Open Judge

**Tradeoff:** When the LLM judge is unavailable (Ollama not running, model timeout), the judge returns `passed=True` with a warning.

**Why accepted:** Foundry is a local development tool. Blocking all execution because Ollama is temporarily down produces worse outcomes than allowing potentially lower-quality output through. Schema checks still run (deterministic, no LLM required).

**Risk:** In a production/shared environment, fail-open judges would allow unvalidated code to advance. Needs hardening for any non-local deployment.

**Migration path:** Add `fail_mode: "open" | "closed"` to judge configuration. Default to open for local, closed for production.

### 2. Character-Based Token Estimation

**Tradeoff:** Token counts use `len(text) // 4` instead of a proper tokenizer.

**Why accepted:** Different models use different tokenizers (BPE, SentencePiece, etc.). Adding a tokenizer dependency for each provider adds complexity with marginal accuracy improvement. Budget enforcement is coarse-grained (100K ceiling); ±20% estimation error is acceptable.

**Risk:** For tasks near the budget ceiling, inaccurate estimation could cause premature abort or budget overrun.

**Migration path:** Add optional `tiktoken` integration for OpenAI models; keep character estimation as fallback for Ollama.

### 3. In-Memory Authority Log

**Tradeoff:** Authority decisions are logged in-memory, lost on server restart.

**Why accepted:** The authority log is primarily a debugging tool. For ongoing development, inspecting the current session's decisions is sufficient.

**Risk:** Cannot audit decisions from previous sessions. Post-mortem debugging of "why did the system do X?" is limited to the current session.

**Migration path:** Persist authority decisions as JSONL in `data/logs/authority.jsonl`.

### 4. Keyword-Based Collapse Detection

**Tradeoff:** Sycophantic collapse detection uses keyword matching (`"i agree"`, `"ditto"`), not semantic analysis.

**Why accepted:** Building a reliable semantic similarity detector for collapse adds significant complexity. Keyword matching catches obvious cases. Sophisticated sycophancy (paraphrasing agreement) is harder to detect regardless of method.

**Risk:** Subtle sycophantic collapse passes undetected. Debate produces false consensus without genuine independent analysis.

**Migration path:** Add cosine similarity between agent responses using sentence embeddings. Flag high similarity as potential collapse.

### 5. Single SQLite Database

**Tradeoff:** All tasks, history, and checkpoints share one SQLite database file.

**Why accepted:** SQLite is zero-infrastructure, ACID-compliant, and performant for single-user local workloads. WAL mode provides concurrent reads. For 100s of tasks with 10s of phases each, SQLite is more than sufficient.

**Risk:** Database corruption (unlikely with WAL + BEGIN IMMEDIATE but possible) loses all task data. No backup mechanism.

**Migration path:** Add periodic `VACUUM` and backup to `data/backups/`. The `StoreBackend` ABC already supports PostgreSQL migration — implement `PostgresStore`.

### 6. No Streaming Output

**Tradeoff:** Complete output is required before validation. No partial/streamed submission.

**Why accepted:** Schema checks require the complete document (section detection). Judge evaluation requires holistic quality assessment. Checkpoint semantics are phase-level, not token-level.

**Risk:** For large outputs (>10K tokens), the agent must wait for full generation before getting feedback. If the output direction is fundamentally wrong, tokens are wasted.

**Migration path:** Add optional "pre-check" endpoint that validates output structure before full generation. The agent can submit an outline for structural validation, then generate the full output.

---

## Known Technical Debt

### High Priority

| Item | Location | Impact | Effort |
|---|---|---|---|
| ToolGate not fully wired | `runtime/tool_gate.py` ↔ `tools/phase.py` | Adapters exist but aren't invoked in submit flow | Medium |
| ExecutionRuntime not integrated | `engine/execution_runtime.py` ↔ `runtime/app.py` | Execution coordination exists but not used | Medium |
| Adapter healthcheck at startup | `adapters/tools/*.py` | Unhealthy adapters aren't detected until first use | Low |
| Model fallback chain | `adapters/llm/routing.py` | `fallback_models` field exists but auto-fallback not wired | Medium |

### Medium Priority

| Item | Location | Impact | Effort |
|---|---|---|---|
| Sandbox enforcement | `config.SandboxConfig` | Config exists but no filesystem interception | High |
| YAML budget profiles | `config.py` | Profiles not loadable from config | Low |
| Prompt persistence | `engine/prompt_registry.py` | Registry is in-memory only, rebuilt each startup | Medium |
| Cross-task memory injection | `adapters/memory/acervo.py` ↔ `tools/phase.py` | Acervo stores engrams but doesn't auto-inject into prompts | Medium |

### Low Priority

| Item | Location | Impact | Effort |
|---|---|---|---|
| Bugfix/review phase graphs | `graphs/` | Only `feature.yaml` exists | Low |
| Graphify/TreeSitter wiring | `adapters/tools/` | Adapters exist, not registered in lifespan | Low |
| Dashboard integration | `runtime/dashboard.py` | Dashboard exists, not connected to live data | Medium |
| Regression manager | `engine/regression_manager.py` | Module exists, not integrated | Medium |

---

## Architecture Risks

### 1. Phase Graph Rigidity

**Risk:** The fixed phase graph (`Chatting → Specs → Planning → Coding → Testing → Review → Done`) doesn't accommodate workflows that need to skip phases or add custom phases.

**Mitigation:** Phase graphs are YAML-defined and validated at startup. Adding new graph templates (bugfix, review, research) requires only new YAML files + registration.

### 2. Single-Model Evaluation

**Risk:** Using the same model for both phase execution (via host agent) and judge evaluation creates a self-evaluation loop. The model is unlikely to catch its own systematic blind spots.

**Mitigation:** ModelRouter allows different models per role. In practice, using a different model for judging vs execution produces better validation. The debate protocol provides additional perspectives.

### 3. Context Window Saturation

**Risk:** As projects grow, the assembled context (previous outputs + code chunks + memory) may exceed the model's context window, causing truncation or degraded quality.

**Mitigation:** Context caps (`context_file_count=10`, `context_chunk_count=20`) limit the total context size. Symbol-level chunking provides focused context rather than full files. Future: sliding window context with relevance-based prioritization.

### 4. Memory Leak in Long Sessions

**Risk:** In-memory collections (`_retry_counts`, `_history`, `_sessions`) grow unboundedly during long server sessions with many tasks.

**Mitigation:** Per-task counters are isolated and should be cleaned up on task completion. No automated cleanup currently exists — tasks that are never completed leak their counter state.

---

## Dependency Inventory

### Python (Core)

| Package | Version | Purpose |
|---|---|---|
| `pydantic` | 2.x | Data validation, serialization |
| `pydantic-settings` | 2.x | Environment-based configuration |
| `mcp` | 1.x | MCP server framework |
| `httpx` | 0.27+ | HTTP client for LLM APIs |
| `pyyaml` | 6.x | YAML config loading |

### Python (Optional)

| Package | Purpose | When Needed |
|---|---|---|
| `tiktoken` | Precise token counting | OpenAI token budgets |
| `tree-sitter` | AST parsing | Enhanced symbol extraction |

### System (External)

| Tool | Purpose | Adapter |
|---|---|---|
| Ollama | Local LLM inference | OllamaProvider |
| Ruff | Python linting | RuffAdapter |
| Mypy | Type checking | MypyAdapter |
| Pytest | Test execution | PytestAdapter |
| Bandit | Security analysis | BanditAdapter |
| Semgrep | Security scanning | SemgrepAdapter |
| Node.js 18+ | NPX installer | `foundry/install/install.js` |
