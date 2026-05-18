# Execution Model

> How Foundry transforms a natural-language engineering request into validated, working code through a deterministic phase-driven execution pipeline.

---

## Execution Philosophy

Foundry's execution model is built on a single principle: **deterministic, recoverable, budget-bounded phase execution**. Every task follows a finite state machine through a directed graph of phases, with each transition gated by validation, and every intermediate state persisted to disk for crash recovery.

The execution model is intentionally **NOT**:
- A free-form agent loop (no "think then act" cycle)
- A multi-agent swarm (one orchestrator, behavioral modes via prompts)
- An unbounded search process (hard budget ceilings)
- A probabilistic pipeline (deterministic schema checks before LLM evaluation)

---

## Execution Layers

```
┌────────────────────────────────────────────────────────────┐
│ Layer 1: Workflow                                          │
│   User intent → phase graph selection → task creation      │
├────────────────────────────────────────────────────────────┤
│ Layer 2: Orchestration                                     │
│   FSM transitions, authority approval, budget enforcement  │
├────────────────────────────────────────────────────────────┤
│ Layer 3: Phase Execution                                   │
│   Prompt generation, LLM call, output capture              │
├────────────────────────────────────────────────────────────┤
│ Layer 4: Validation                                        │
│   Schema checks → LLM judge → debate → consensus          │
├────────────────────────────────────────────────────────────┤
│ Layer 5: State Management                                  │
│   Write queue → atomic persistence → checkpointing         │
├────────────────────────────────────────────────────────────┤
│ Layer 6: Recovery                                          │
│   Retry → replan → structural → full recovery              │
└────────────────────────────────────────────────────────────┘
```

---

## The Phase Execution Cycle

### Complete Cycle Diagram

```
┌─────────────────────┐
│ sdlc_get_next_action │
│                     │
│ 1. Load task        │
│ 2. Check budget     │
│ 3. Route model      │
│ 4. Build prompt     │
│ 5. Gather context   │
│ 6. Return action    │
└────────┬────────────┘
         │
         │  Host agent executes phase with tools
         │
         ▼
┌─────────────────────┐
│ sdlc_submit_output   │
│                     │
│ 1. Verify phase     │
│ 2. Schema checks    │ ──→ REJECT (terminal)
│ 3. LLM judge        │ ──→ REJECT (retryable) ──→ Debate?
│ 4. Debate protocol   │ ──→ Can overturn judge
│ 5. Consensus eval    │
│ 6. Authority check   │
│ 7. FSM transition    │
│ 8. Checkpoint write  │
│ 9. Return result     │
└─────────────────────┘
```

### Step-by-Step Execution

**1. Task Creation (`sdlc_create_task`)**

```python
task = Task(
    task_id=uuid4().hex[:12],
    description=user_description,
    mode="feature",                    # Selects phase graph template
    status=TaskStatus.ACTIVE,
    current_phase="Chatting",          # Always starts at first phase
    budget=BudgetPolicy(...),
    locked_prompts=settings.load_all_judge_prompts(),  # Frozen at creation
)
```

The task is immediately persisted via the write queue. The host agent gets back the task_id and can begin the execution loop.

**2. Action Retrieval (`sdlc_get_next_action`)**

This assembles everything the host agent needs to execute the current phase:

```python
action = {
    "task_id": task.task_id,
    "phase": task.current_phase,
    "phase_index": graph.index_of(task.current_phase),
    "subagent": route.get("subagent", "dev-sdlc"),
    "model": route.get("model", "qwen3:8b"),
    "fallback_models": route.get("fallback_models", []),
    "prompt": _build_phase_prompt(task.current_phase, task.description),
    "context": await _gather_context(task, pipeline),
    "constraints": _build_constraints(task.current_phase, route),
    "progress": graph.progress(task.current_phase),
}
```

Context gathering includes:
- Previous phase outputs from task history
- Relevant code files from the index pipeline
- Code chunks with symbol-level granularity
- Dependency graph summary
- Memory context (if enabled)

**3. Output Submission (`sdlc_submit_output`)**

This is the most complex operation — the core validation, transition, and persistence pipeline:

```
Phase validation → Budget check → Schema validation → Judge evaluation
    → [optional] Debate → [optional] Consensus → Authority approval
    → FSM transition → State persistence → Checkpoint creation
```

The submit handler in `tools/phase.py` orchestrates all of these in sequence. Each step can reject the output, causing the task to remain in its current phase for retry.

---

## Output Validation Pipeline

### Stage 1: Schema Checks (Deterministic)

Every phase output must contain required structural sections. These checks run before any LLM evaluation:

```python
# Example: Specs phase requires these sections
required_sections = {
    "Specs": ["## Requirements", "## Scope", "## Constraints"],
    "Planning": ["## Implementation Plan", "## File Changes", "## Risks"],
    "Review": ["## Issues Found", "## Severity", "## Must Fix"],
    "Testing": ["## Test Results", "## Coverage", "## Failed"],
}
```

**Section extraction algorithm:**
1. Search for `## <heading>` patterns using regex
2. Extract content between headings
3. Verify section is non-empty (not just whitespace)
4. If any required section is missing → `TERMINAL_VALIDATION` failure

Schema violations are terminal — they cannot be retried because they indicate the output is structurally wrong, not marginally insufficient.

### Stage 2: LLM Judge (Probabilistic)

If schema checks pass, the judge engine evaluates quality:

```python
verdict = await judge_engine.evaluate(
    task=task,
    from_phase=current_phase,
    to_phase=next_phase,
    output=output,
)
```

The judge uses:
- Temperature=0.0 (deterministic output)
- Locked prompts from task creation (reproducible evaluation)
- Structured JSON response format (parseable verdict)

**Fail-open behavior:** If the LLM is unavailable, the judge returns `passed=True` with a warning. This prevents infrastructure failures from blocking execution.

### Stage 3: Debate (Multi-Agent Review)

If the judge rejects AND debate is configured, a 3-round multi-agent debate runs:

```
Round 1: Independent assessment (no cross-agent context)
Round 2: Deliberation (agents see all Round 1 responses)
Round 3: Final positions (agents see all Round 2 responses)
```

**Debate can overturn judge rejection.** If consensus passes despite judge failure, the output advances. This provides a second opinion mechanism that prevents a single judge prompt from being the sole gatekeeper.

### Stage 4: Consensus Evaluation

The consensus engine synthesizes debate results through two mechanisms:

1. **LLM consensus judge** (primary) — neutral evaluator reviews all agent responses
2. **Majority vote fallback** — if LLM fails, count PASS/FAIL tokens from text

Additionally, the consensus engine detects:
- **Sycophantic collapse** — agents agreeing without substance
- **Minority positions** — valid dissenting views preserved as minority reports
- **Residual objections** — concerns raised but never resolved across rounds

---

## Budget Enforcement Model

### Hard Ceilings

Every budget parameter is a hard ceiling. When any ceiling is hit, the task is aborted:

```python
class BudgetPolicy(BaseModel):
    max_total_tokens: int = 100_000       # Total tokens across all phases
    max_review_cycles: int = 8            # Max judge rejections
    max_debate_rounds: int = 3            # Max debate rounds per phase
    max_runtime_minutes: int = 60         # Wall-clock limit
    fallback_depth: int = 2              # Model fallback chain depth
    max_debate_budget_tokens: int = 15_000 # Token budget for debate
```

### Enforcement Points

Budget is checked at multiple points in the execution cycle:

| Check Point | What's Checked | Violation Response |
|---|---|---|
| Before `get_next_action` | Token budget, runtime | ABORT |
| Before debate start | Debate token budget | Skip debate |
| Between debate rounds | Round count | End debate early |
| After judge rejection | Review cycle count | ABORT if exceeded |
| After any output | Total iterations | ABORT if exceeded |

### Violation Severities

```python
WARNING  = 80% of token budget consumed → log warning
ERROR    = Phase retry count exhausted → escalate recovery
CRITICAL = Absolute ceiling hit → abort task immediately
```

---

## Retry and Recovery Semantics

### 5-Level Escalation Ladder

When a phase fails, the system escalates through increasingly aggressive recovery strategies:

```
Level 0: LOCAL_RETRY
    Same phase, same approach, fix the specific error
    
Level 1: LOCAL_REPLAN
    Same phase, but regenerate the approach with error context
    
Level 2: PHASE_RETRY
    Reset the phase entirely, try from scratch
    
Level 3: STRUCTURAL_REPLAN
    Invalidate downstream phases, replanner rebuilds plan
    
Level 4: FULL_RECOVERY
    Restore from checkpoint, attempt from last known good state
```

### Failure Classification

The retry policy classifies errors by pattern matching:

| Pattern | Classification | Starting Level |
|---|---|---|
| `syntax`, `indent`, `parse` | Syntax error | LOCAL_RETRY |
| `test`, `assert`, `expect` | Test failure | LOCAL_RETRY |
| `lint`, `ruff`, `style` | Lint violation | LOCAL_RETRY |
| `timeout`, `timed out` | Timeout | PHASE_RETRY |
| `import`, `module` | Integration issue | STRUCTURAL_REPLAN |
| `crash`, `segfault`, `killed` | System crash | FULL_RECOVERY |

### Replanning Invariant

**Preserve completed stable work.** When replanning:
1. Identify the trigger phase and all downstream phases
2. Mark them for invalidation
3. Check dependency graph for transitive invalidation
4. Protect any phase marked as stable

A phase is marked stable via `replanner.mark_stable(task_id, phase)`. Stable phases are never invalidated, even during full recovery.

---

## State Persistence Model

### Write Path

All state mutations flow through the write queue:

```
Phase tool produces WriteOp
    │
    ▼
WriteQueue (async FIFO)
    │
    ▼
WriteHandler dispatches by target:
    ├── target="task"    → store.create_task() or store.update_task()
    ├── target="phase"   → store.save_phase_output()
    ├── target="checkpoint" → checkpoint_mgr.save()
    └── target="memory"  → acervo.store()
```

### Atomicity Guarantees

All file writes use the `tmp+rename` pattern:
1. Write to `{filename}.tmp`
2. `os.rename()` atomically replaces the target file
3. On POSIX systems, `rename()` is atomic within the same filesystem

SQLite writes use `BEGIN IMMEDIATE` transactions:
1. Acquire write lock before modifying data
2. On success: `COMMIT`
3. On failure: `ROLLBACK`

### Checkpoint Strategy

A checkpoint is created after every accepted phase transition:

```python
checkpoint = Checkpoint(
    task_id=task.task_id,
    phase=new_phase,
    history=task.history,
    iteration_count=task.iteration_count,
    adapter_states={},
    snapshot=task.snapshot,
)
```

Checkpoints form a versioned chain. The enhanced checkpoint manager maintains:
- Chain metadata: `{task_id}_chain.json`
- Individual versions: `{task_id}_v{N}.json`
- Restore points: named bookmarks within the chain

---

## Execution Context Assembly

### What the Host Agent Receives

The `get_next_action` response is the most information-dense MCP tool output. It contains everything needed to execute a phase autonomously:

```python
{
    # Identity
    "task_id": "abc123",
    "phase": "Coding",
    "phase_index": 3,
    "mode": "feature",
    
    # Model routing
    "subagent": "dev-sdlc",
    "model": "qwen3:8b",
    "fallback_models": ["qwen3:4b"],
    
    # Prompt
    "prompt": "You are executing the Coding phase...",
    
    # Context
    "context": {
        "task_description": "...",
        "previous_outputs": ["Specs output...", "Planning output..."],
        "relevant_files": ["auth.py", "models.py"],
        "context_chunks": [{
            "file_path": "auth.py",
            "content": "class AuthService:\n    ...",
            "start_line": 1,
            "end_line": 50,
            "symbol_name": "AuthService",
        }],
        "graph_summary": {"file_count": 42, "symbol_count": 186},
    },
    
    # Constraints
    "constraints": {
        "must_produce": "Output must reference specific files modified.",
        "must_not_do": [],
        "bash_allowed_patterns": ["test", "build", "lint", "git *"],
    },
    
    # Progress
    "requires_approval": false,
    "progress": 50.0,
}
```

### Context Sources

| Source | What It Provides | When Used |
|---|---|---|
| Task history | Previous phase outputs | Always |
| Index pipeline | Relevant files + code chunks | When indexing enabled |
| Dependency graph | Import edges + dependents | When indexing enabled |
| Memory store | Past errors + decisions | When `memory_enabled=True` |
| Model routing config | Model + subagent per phase | Always |

---

## Execution Determinism

### What Is Deterministic

| Component | Determinism | How |
|---|---|---|
| Phase graph traversal | ✓ Fully | YAML-defined, validated at startup |
| Schema checks | ✓ Fully | Regex-based section detection |
| Budget enforcement | ✓ Fully | Integer comparison against hard ceilings |
| Failure classification | ✓ Fully | Pattern matching against keyword lists |
| Retry escalation | ✓ Fully | Counter-based level advancement |
| Phase restrictions | ✓ Fully | Phase name lookup |
| Rollback safety | ✓ Fully | Stable set protection |

### What Is NOT Deterministic

| Component | Non-determinism Source | Mitigation |
|---|---|---|
| LLM judge evaluation | Model temperature, sampling | `temperature=0.0` reduces but doesn't eliminate |
| Debate agent responses | Different models, different outputs | Consensus mechanism averages across agents |
| Context retrieval | Filesystem state changes between runs | SHA-based incremental indexing |
| LLM phase execution | Core non-determinism of language models | Schema checks provide deterministic minimum quality |

### Prompt Locking

To maximize reproducibility, judge prompts are locked at task creation:

```python
task.locked_prompts = settings.load_all_judge_prompts()
```

This means:
- If you modify `configs/prompts/judge_specs_to_planning.txt` after creating a task, the running task continues using the original prompt
- Replay from a checkpoint uses the same prompts as the original execution
- The `ExecutionSnapshot` records content hashes of all locked prompts for verification

---

## Execution Modes (Phase Graph Templates)

### Feature (Implemented)

```
Chatting → Specs → Planning → Coding → Testing → Review → Done
```

Full SDLC lifecycle with specification, planning, implementation, testing, and review. Back-edges allow Testing→Coding (test failures) and Review→Coding (review rejections).

### Bugfix (Planned)

```
Chatting → Debugging → Coding → Testing → Done
```

Abbreviated lifecycle focused on diagnosis and fix. Skips specification and formal review phases.

### Review (Planned)

```
Chatting → Review → Done
```

Minimal lifecycle for reviewing existing code without generating new code.

### Research (Planned)

```
Chatting → Research → Analysis → Done
```

No-code lifecycle for technical investigation. No tool gates, no file editing.

---

## Known Limitations

### Current Execution Gaps

| Gap | Impact | Status |
|---|---|---|
| No parallel phase execution | Phases execute sequentially | By design — simplicity over parallelism |
| No partial output streaming | Full output required for submission | Infrastructure limitation |
| No cross-task dependency | Tasks are independent | Planned for distributed runtime |
| Judge fail-open | LLM unavailability passes all checks | Acceptable for local dev; needs hardening for production |
| No incremental validation | Full output re-validated on retry | Performance concern for large outputs |

### Edge Cases

1. **Empty output submission:** Rejected by schema checks (minimum content requirement)
2. **Identical retry output:** Same output re-submitted — judge may pass or fail identically (no deduplication)
3. **Phase graph modification during task:** Task continues with original graph; new graph applies to new tasks only
4. **Concurrent task execution:** SQLite `BEGIN IMMEDIATE` serializes writes; reads are concurrent via WAL mode
5. **Server crash during checkpoint write:** Atomic `tmp+rename` ensures either old or new checkpoint exists, never a partial file
