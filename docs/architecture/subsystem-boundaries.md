# Subsystem Boundaries

> Exhaustive specification of every module's ownership, prohibited cross-concerns, and interaction contracts.

---

## Boundary Enforcement Philosophy

Foundry enforces **strict single-responsibility boundaries**. No module may reach into another's internals. Cross-cutting concerns flow through explicit interfaces, not implicit coupling.

The goal: any module can be replaced without touching another module's implementation.

---

## Engine Subsystems

### OrchestratorFSM (`engine/orchestrator.py`, 65 lines)

**Owns:** Phase transition validation, next-phase resolution, ambiguity detection.

**Interface:**
```python
submit(current_phase: str, target: str | None = None) -> str
```

**Invariants:**
- The FSM is a **pure function** from `(current_phase, target) → next_phase`
- Never checks budget, retry, or failure state
- Raises `OrchestratorError` on invalid transitions
- When multiple outgoing transitions exist and no target is specified, resolves by:
  1. If single option → use it
  2. If two options and one is "Done" → pick non-Done
  3. Otherwise → raise ambiguity error

**Never touches:** Budget logic, retry logic, failure classification, consensus, debate, state persistence, LLM calls.

---

### PhaseGraph (`engine/phase_graph.py`, 124 lines)

**Owns:** Graph loading from YAML, structural validation, reachability analysis, progress calculation.

**Interface:**
```python
next_phases(phase: str) -> list[str]
is_valid_transition(from_phase: str, to_phase: str) -> bool
is_terminal(phase: str) -> bool
reachable_phases(start: str) -> set[str]
progress(phase: str) -> float  # 0.0 to 100.0
index_of(phase: str) -> int
```

**Validation at construction:**
1. At least one phase
2. `Done` phase declared
3. All transition endpoints exist
4. All phases reachable from start via DFS
5. `Done` has zero outgoing transitions

**Never touches:** Runtime state, task objects, LLM providers.

---

### ExecutionPolicy (`engine/execution_policy.py`, 88 lines)

**Owns:** Budget decisions, failure classification, retry decisions.

**Interface:**
```python
check_budget(task: Task) -> Decision
should_retry(failure_type: FailureType, attempt: int) -> Decision
classify_failure(error: str) -> FailureType
```

**Decision outputs:** `PROCEED`, `RETRY`, `ABORT`, `ESCALATE`

**Never touches:** Phase transitions, consensus, debate, state persistence.

---

### JudgeEngine (`engine/judge.py`, 160 lines)

**Owns:** Three-stage output evaluation (phase match → schema checks → LLM judge).

**Interface:**
```python
evaluate(task: Task, from_phase: str, to_phase: str, output: str) -> JudgeVerdict
```

**Three-stage gate:**
1. **Deterministic schema checks** (`schema_checks.py`) — run first, reject immediately on structural violations
2. **Prompt key lookup** — find the locked judge prompt for this transition
3. **LLM judge** — call the provider with temperature=0.0 and structured JSON output

**Fail-open behavior:** If the LLM judge is unavailable (timeout, error), the judge returns `passed=True` with a warning. This prevents LLM failures from blocking execution.

**Never touches:** Debate, consensus, phase transitions, retry logic.

---

### JudgeHierarchy (`engine/judge_hierarchy.py`, 403 lines)

**Owns:** Multi-dimension evaluation across 6 judge types.

**Judge types and responsibilities:**

| Judge | Type | What It Checks | Can Block? |
|---|---|---|---|
| `ToolJudge` | `tool` | Lint/type/test failure signals in output | Yes (error severity) |
| `SemanticJudge` | `semantic` | Spec alignment via LLM or structural fallback | No (warning) |
| `ArchitectureJudge` | `architecture` | Anti-patterns (god class, circular imports, hardcoded values) | No (warning) |
| `SecurityJudge` | `security` | Dangerous patterns (eval, exec, pickle.loads, os.system) | Yes (critical severity) |
| `RiskJudge` | `risk` | Operational risks (breaking changes, migrations, data loss) | No (warning) |
| `IntegrationJudge` | `integration` | Test failures, import errors | Yes (error severity) |

**Phase → Judge mapping:**

| Phase | Active Judges |
|---|---|
| Specs | Semantic |
| Planning | Semantic, Architecture, Risk |
| Coding | Tool, Semantic, Security |
| Review | Tool, Semantic, Architecture, Security |
| Testing | Tool, Integration |

**Consensus rule:** Majority must pass AND no critical-severity blockers. A single `SecurityJudge` veto at `critical` severity blocks the entire transition.

**Never touches:** Debate runtime, retry logic, phase transitions.

---

### DebateRuntime (`engine/debate_runtime.py`, 360 lines)

**Owns:** 3-round debate protocol, agent configuration, debate orchestration, partial completion handling.

**Interface:**
```python
run_debate(task: Task, phase: str, output: str, budget: BudgetPolicy) -> DebateTranscript
```

**Agent configuration per phase:**
```python
PHASE_AGENTS = {
    "Specs":    [specs, planning],
    "Planning": [planning, coding, specs],
    "Coding":   [coding, review, testing],
    "Review":   [review, coding, testing],
    "Testing":  [testing, coding, review],
}
```

**Round protocol:**
- Round 1: Independent assessment (no context from other agents)
- Round 2: Deliberation (each agent sees all Round 1 responses)
- Round 3: Final positions (each agent sees all Round 2 responses)

**Partial completion:** If an agent times out or errors during a round, the debate continues with the remaining agents. The transcript records which agents participated in which rounds.

**Budget enforcement:** The debate runtime checks `budget.max_debate_rounds` and `budget.max_debate_budget_tokens` before starting and between rounds.

**Never touches:** Phase transitions, checkpoints, state persistence, tool gates.

---

### ConsensusEngine (`engine/consensus.py`, 286 lines)

**Owns:** Verdict synthesis, minority reports, collapse detection, residual objection tracking.

**Interface:**
```python
evaluate(responses, task, phase, round_number, max_rounds) -> ConsensusResult
detect_collapse(responses) -> CollapseSignal
extract_minority_reports(responses, agent_verdicts) -> list[MinorityReport]
extract_residual_objections(all_rounds) -> list[str]
```

**Two evaluation modes:**
1. **LLM consensus** (primary) — neutral judge evaluates all responses, returns structured JSON
2. **Majority vote fallback** — if LLM fails, extract PASS/FAIL tokens from text, count votes

**Collapse detection constants:**
- Keywords: "i agree", "i concur", "same here", "ditto", "echo", "second that", "nothing to add"
- Threshold: 60% of agents using collapse keywords triggers detection
- Minimum rounds for comparison: 2

**Never touches:** Debate protocol, agent calls, I/O, orchestration.

---

### ConfidenceGate (`engine/confidence_gate.py`, 178 lines)

**Owns:** Vote normalization, threshold enforcement, drift detection, gate decisions.

**Interface:**
```python
evaluate(votes: list[ConfidenceVote]) -> GateDecision
detect_drift(window: int = 5) -> dict
```

**Gate decision matrix:**

| Condition | Action | Approved |
|---|---|---|
| Unanimous + avg ≥ 0.7 | `approve` | ✓ |
| Non-unanimous, low-confidence disapprovals (<0.3) | `synthesize` | ✗ |
| Non-unanimous, high-confidence disapprovals | `continue_debate` | ✗ |
| Avg below threshold | `continue_debate` | ✗ |
| No votes | `reject` | ✗ |

**Never touches:** Debate runtime, consensus logic, phase transitions.

---

### RetryPolicy (`engine/retry_policy.py`, 177 lines)

**Owns:** 5-level escalation ladder, failure classification by pattern, effectiveness tracking, no-progress detection.

**Escalation levels:**
```
LOCAL_RETRY → LOCAL_REPLAN → PHASE_RETRY → STRUCTURAL_REPLAN → FULL_RECOVERY
```

**Classification rules:**

| Pattern | Failure Type | Recommended Level |
|---|---|---|
| `syntax`, `indent`, `parse` | Syntax error | LOCAL_RETRY |
| `test`, `assert`, `expect` | Test failure | LOCAL_RETRY |
| `lint`, `ruff`, `style` | Lint violation | LOCAL_RETRY |
| `timeout`, `timed out` | Timeout | PHASE_RETRY |
| `import`, `module` | Integration issue | STRUCTURAL_REPLAN |
| `crash`, `segfault`, `killed` | System crash | FULL_RECOVERY |

**Effectiveness scoring:** `success_rate = succeeded_attempts / total_attempts` per phase.

**No-progress detection:** If the last N retries all failed, signal that escalation is needed regardless of remaining budget.

**Never touches:** Phase transitions, budget enforcement, consensus.

---

### RecoveryEngine (`engine/recovery_engine.py`, 168 lines)

**Owns:** Layered recovery classification, failure history tracking, counter management.

**Interface:**
```python
classify_recovery(phase, error, failure_type) -> RecoveryAction
reset_phase(phase) -> None
reset_all() -> None
```

**Recovery classification flow:**
```
failure_type → retryable + retries < max → LOCAL_RETRY
            → validation/phase + replans < max → LOCAL_REPLAN
            → consensus/dependency or exhausted → STRUCTURAL_REPLAN
            → everything else → FULL_RECOVERY
```

**Counter isolation:** Each phase has independent retry and replan counters. Resetting phase "Coding" doesn't affect phase "Testing" counters.

**Never touches:** Git operations, checkpoint management, state persistence.

---

### Replanner (`engine/replanner.py`, 108 lines)

**Owns:** Downstream invalidation, dependency-aware phase invalidation, stable-work preservation.

**Invariant:** `PRESERVE COMPLETED STABLE WORK`

**Interface:**
```python
plan_replan(task_id, trigger_phase, all_phases, reason) -> ReplanScope
apply_replan(scope) -> dict
mark_stable(task_id, phase) -> None
set_phase_dependencies(deps) -> None
```

**Invalidation logic:**
1. Find trigger phase index
2. Invalidate trigger + all downstream non-stable phases
3. Additionally invalidate phases that depend on invalidated phases (dependency graph)
4. Preserve all stable-marked phases

**Never touches:** Git operations, checkpoint versions, LLM calls.

---

### ContextHarvester (`engine/context_harvester.py`, 393 lines)

**Owns:** Pre-spec question generation, environment analysis, spec-lock enforcement.

**Interface:**
```python
harvest(task_description, repo_analysis=True) -> ContextBundle
is_ready_for_spec(bundle) -> (bool, list[str])
check_spec_drift(locked_spec, current_output) -> list[SpecLockViolation]
```

**Question categories:** requirements, constraints, environment, deployment, edge_cases, scalability, risk_tolerance, architecture, dependencies, coding_standards.

**Priority levels:** critical (blocks spec), high (strongly recommended), medium (optional).

**Spec-lock enforcement:** After spec approval, detects scope expansion ("additional feature", "while we're at it") and requirement changes ("changed requirement", "instead of") in downstream outputs.

**Never touches:** Phase transitions, debate, consensus, budget.

---

### DriftDetector (`engine/drift_detector.py`, 149 lines)

**Owns:** Layer violation detection, circular dependency detection, consistency scoring.

**Layer hierarchy:**
```
Layer 0: models, exceptions, log (pure utilities)
Layer 1: config (imports models)
Layer 2: adapters (imports models, config)
Layer 3: engine, validators (imports adapters, models)
Layer 4: runtime, cli (imports everything)
```

**Rule:** Higher layers may import from lower layers. Lower layers **MUST NOT** import from higher layers.

**Cycle detection:** Uses DFS-based cycle detection, capped at 10 cycles per analysis.

**Consistency score:** `1.0 - (violation_count / total_imports)`, clamped to [0.0, 1.0].

**Never touches:** Runtime state, LLM calls, phase transitions.

---

### PromptRegistry (`engine/prompt_registry.py`, 293 lines)

**Owns:** Versioned prompt storage, content-hash deduplication, rollback, compatibility tracking.

**Interface:**
```python
register(name, content, **metadata) -> PromptVersion
get(name, version=None) -> PromptVersion | None
rollback(name, to_version) -> bool
load_from_dir(prompts_dir) -> int
save_to_dir(prompts_dir) -> int
all_hashes() -> dict[str, str]
```

**Deduplication:** If a prompt's content hash matches an existing version, the existing version is returned without creating a duplicate.

**Compatibility manager:** Tracks which prompt versions have been tested with which models. Detects stale prompts (content changed since last test).

**Never touches:** LLM calls, phase transitions, debate, consensus.

---

## Runtime Subsystems

### StateManager (`runtime/state_manager.py`, 202 lines)

**Owns:** Global/task/phase state persistence, atomic writes, crash recovery discovery.

**Files managed:**
- `state.json` — global runtime state
- `task_{id}.json` — per-task state
- `phase_{id}.json` — current phase state

**Atomic write guarantee:** All writes use `tmp+rename` pattern (POSIX-atomic).

**Never touches:** Checkpoints, memory store, SQLite, LLM calls.

---

### EnhancedCheckpointManager (`runtime/enhanced_checkpoint.py`, 306 lines)

**Owns:** Versioned checkpoint chains, restore points, replay sequences.

**Files managed:**
- `{task_id}_chain.json` — chain metadata
- `{task_id}_v{N}.json` — individual checkpoint versions

**Never touches:** State files, memory store, phase transitions.

---

### RollbackManager (`runtime/rollback_manager.py`, 144 lines)

**Owns:** Phase-file tracking, stable phase protection, rollback planning/validation.

**Invariant:** `ROLLBACK MUST NEVER CORRUPT STABLE COMPLETED PHASES`

**Safety check:** If rollback plan shows overlap between `files_to_revert` and `protected_files`, the `safe` flag is `False` and execution should be refused.

**Never touches:** Checkpoints, state manager, LLM calls.

---

### BudgetController (`runtime/budget_controller.py`, 294 lines)

**Owns:** Token/time/retry/resource tracking and hard-ceiling enforcement.

**Violation severities:** `warning` (80% token), `error` (phase retry exhausted), `critical` (absolute ceiling hit — task must abort).

**Never touches:** Phase transitions, retry decisions (only tracks counts, doesn't decide what to do).

---

### ExecutionRuntime (`runtime/execution_runtime.py`, 248 lines)

**Owns:** Deterministic execution IDs, prompt hash locking, model routing locks, artifact contracts, transition recording.

**Never touches:** State persistence, checkpoints, LLM calls, debate.

---

### ToolGate (`runtime/tool_gate.py`, 133 lines)

**Owns:** Ordered validation gate definitions, fail-fast evaluation, phase-specific exceptions.

**Default gate sequence:** lint → types → tests → coverage → security → benchmarks

**Never touches:** LLM calls, phase transitions, budget enforcement.

---

### MemoryStore (`runtime/memory_store.py`, 260 lines)

**Owns:** Structured retrieval over Acervo (phase summaries, error memory, decision records).

**Never touches:** State files, checkpoints, phase transitions.

---

### Tracer (`runtime/tracing.py`, 279 lines)

**Owns:** JSONL span recording, retention enforcement, trace summaries.

**Retention policy:**
- Error traces: preserved indefinitely (moved to `errors/` directory)
- Successful traces: deleted after 7 days
- Raw spans: deleted after 30 days
- Summaries: append-only, never deleted

**Never touches:** Everything else (pure observability).

---

## Adapter Subsystems

### Acervo (`adapters/memory/acervo.py`, 163 lines)

**Owns:** JSONL-based engram storage, tag-based query, importance filtering.

**Storage format:** Append-only JSONL file (`engrams.jsonl`). Deletes trigger full rewrite.

**Query filtering chain:** phase → tags → keywords → source → min_importance → sort by importance desc → limit.

**Never touches:** State files, checkpoints, LLM calls.

---

### MemoryAdapter (`adapters/memory/engram.py`, 87 lines)

**Owns:** ToolAdapter wrapper over Acervo for the store/query interface.

**Two operations:** `store` (content-based) and `query` (tag/keyword-based).

**Never touches:** Direct file I/O (delegates to Acervo).

---

### LLMProvider (`adapters/llm/`)

**Owns:** Provider abstraction for LLM inference.

**Interface:**
```python
generate(messages, model, temperature, max_tokens, response_format) -> str
```

**Implementations:** `OllamaProvider`, `OpenAIProvider`

**Never touches:** Orchestration, state, debate protocol.
