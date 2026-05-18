# Failed Approaches

> Design decisions that were tried, evaluated, and rejected during Foundry's development, with concrete rationale for each rejection.

---

## 1. Skill-Per-Behavior Architecture

**What was tried:** 500+ conceptual "skills" where each execution behavior (retry, validate, lint, plan, debate, review, test) was an independent skill module that could be composed at runtime.

**What happened:** The abstraction explosion created more coordination overhead than value. Most "skills" were really: prompt strategies, methods on existing modules, retrieval modes, or validator stages — not standalone runtime components.

**Why rejected:** Unnecessary micro-decomposition. A "validate output" skill, a "run lint" skill, and a "check types" skill are better expressed as sequential gates in a single ToolGate pipeline.

**What replaced it:** ~12 actual runtime subsystems with clear boundaries, plus behavioral modes via prompt strategies.

---

## 2. Plugin-Based Orchestration

**What was tried:** Orchestration as a plugin system where phase transitions, validation, and recovery were all pluggable behaviors.

**What happened:** Plugin interfaces required so many extension points that the "core" was nearly empty. Debugging plugin interactions was harder than debugging a monolithic orchestrator.

**Why rejected:** The orchestration logic is small enough (~400 lines) that plugin overhead exceeds the flexibility benefit. Direct implementation is simpler and more debuggable.

**What replaced it:** Single `OrchestratorFSM` with configurable policies (ExecutionPolicy, RetryPolicy).

---

## 3. Embedding-Based Context Retrieval

**What was tried:** Code embeddings using sentence-transformers for semantic code search, stored in a FAISS index.

**What happened:** Embedding quality for code was inconsistent. Variable names like `auth_handler` had disproportionate influence. Structural relationships (imports, dependents) were more reliable for finding relevant context.

**Why rejected:** Added GPU/CPU overhead, embedding model dependency, and vector store maintenance for marginally better retrieval compared to structural indexing.

**What replaced it:** `DependencyGraphEngine` with import edge analysis, symbol extraction, and keyword matching.

---

## 4. Multi-Process Agent Architecture

**What was tried:** Running debate agents as separate Python processes for true parallelism.

**What happened:** Process startup overhead (>1s per process) exceeded the LLM call time savings. Inter-process communication via pipes added serialization complexity. One agent's crash required the parent process to detect and handle it.

**Why rejected:** For 3 LLM calls that take 5-15s each, process-level parallelism saves <30% time while adding significant complexity.

**What replaced it:** Sequential async LLM calls within a single process. Simpler, more reliable, and the bottleneck is LLM inference time, not Python execution.

---

## 5. Streaming Output Validation

**What was tried:** Validating output as tokens streamed in, providing early feedback before generation completed.

**What happened:** Schema checks require the complete document structure. A section heading might appear in the first 20% of output, but its content appears in the middle. Judge evaluation requires holistic assessment.

**Why rejected:** Partial validation produces false positives (section heading exists, content doesn't) and false negatives (later content satisfies requirements). Full-output validation is more reliable.

**What replaced it:** Complete output collection, then full validation pipeline.

---

## 6. Git-Based State Persistence

**What was tried:** Using Git commits for state persistence — each phase transition creates a commit, rollback is `git reset`.

**What happened:** Git commits are heavyweight for state snapshots (full working tree diff). Checkpoint restoration requires `git checkout` which modifies the working directory. Mixing Foundry state with user code in the same Git history creates confusion.

**Why rejected:** Git is for user code versioning. Foundry state (task metadata, phase outputs, budgets) belongs in its own storage (SQLite + JSON files).

**What replaced it:** `SqliteStore` for structured data, JSON files for human-readable state, separate from the user's Git repository.

---

## 7. LangChain Integration

**What was tried:** Using LangChain's `ChatModel` and `Chain` abstractions for LLM interaction.

**What happened:** LangChain added ~15 transitive dependencies. The abstraction layer obscured error messages from Ollama. Debugging "why did the LLM call fail?" required navigating through 4 layers of wrappers. Configuration was more complex than direct HTTP calls.

**Why rejected:** The total LLM integration (base + providers + routing) is 230 lines of direct httpx calls. LangChain would add thousands of lines of abstraction for the same functionality.

**What replaced it:** `LLMProvider` ABC with `OllamaProvider` and `OpenAIProvider` implementations. Direct, transparent, debuggable.

---

## 8. Database-Per-Task

**What was tried:** Creating a separate SQLite database for each task to provide isolation and simplify cleanup.

**What happened:** Cross-task queries (list all tasks, find similar errors) required opening multiple database files. File descriptor limits became a concern for long-running sessions with many tasks.

**Why rejected:** Single database with WAL mode provides sufficient isolation (tasks are identified by `task_id`). Cross-task queries are simple SQL. Cleanup is a single `DELETE WHERE task_id = ?`.

**What replaced it:** Single `data/sdlc.db` with tables: `tasks`, `phase_history`, `checkpoints`.

---

## Lessons Learned

1. **Complexity is not the same as capability.** The system with 500 skills was less capable than the system with 12 subsystems.
2. **Frameworks add abstraction, not value** when the underlying operation is simple (HTTP call + JSON parse).
3. **Structural analysis beats semantic analysis** for code when the goal is finding dependencies and relationships.
4. **Sequential is fine** when the bottleneck is external (LLM inference), not internal (Python execution).
5. **Dedicated storage beats repurposed storage.** SQLite for Foundry state. Git for user code. Don't mix them.
