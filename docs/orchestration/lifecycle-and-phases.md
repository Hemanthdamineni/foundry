# Orchestration & Lifecycle

> How Foundry drives tasks from intent to completion through deterministic phase transitions, structured reasoning, and graduated failure handling.

---

## Phase Graph System

### The SDLC Finite State Machine

Foundry's lifecycle is governed by a **directed acyclic phase graph** loaded from YAML at startup. The phase graph defines:

1. **All legal phases** — the set of states the system can be in
2. **All legal transitions** — which phase can follow which
3. **A terminal state** — `Done` has no outgoing transitions
4. **Reachability** — every phase is reachable from the start phase

```yaml
# graphs/feature.yaml
phases:
  - Chatting
  - Specs
  - Planning
  - Coding
  - Testing
  - Review
  - Done

transitions:
  - { from: Chatting, to: Specs }
  - { from: Specs, to: Planning }
  - { from: Planning, to: Coding }
  - { from: Coding, to: Testing }
  - { from: Testing, to: Review }
  - { from: Testing, to: Coding }    # test failure → re-code
  - { from: Review, to: Done }
  - { from: Review, to: Coding }     # review rejection → re-code
```

### PhaseGraph Validation Rules

The `PhaseGraph` class enforces these invariants at construction time:

1. **At least one phase exists** — empty graphs are rejected
2. **`Done` phase exists** — the terminal state must be declared
3. **All transitions reference declared phases** — no dangling references
4. **All phases are reachable** — unreachable phases from the start phase are rejected via DFS
5. **`Done` has no outgoing transitions** — the terminal state is truly terminal

If any invariant is violated, `PhaseGraphError` is raised and the server refuses to start.

### OrchestratorFSM: The Phase Controller

`OrchestratorFSM` is a **pure state machine** — it owns exactly one question: *"given the current phase, what comes next?"*

```python
class OrchestratorFSM:
    """Deterministic phase state machine. Answers only: what phase comes next?"""

    def submit(self, current_phase: str, target: str | None = None) -> str:
        # 1. Validate current_phase exists in graph
        # 2. Get possible next phases
        # 3. If target provided and valid, use it
        # 4. If single option, use it
        # 5. If two options with one being "Done", pick the non-Done option
        # 6. Otherwise: ambiguous — raise OrchestratorError
```

**Critical design decision:** The FSM never sees budget, retry, or failure logic. That separation exists because:
- Budget checking is a **policy** concern (`ExecutionPolicy`)
- Retry decisions are a **recovery** concern (`RetryPolicy`)
- The FSM is a **pure function** from `(current_phase, target) → next_phase`

This prevents the FSM from accumulating cross-cutting concerns and becoming an "everything class."

---

## Task Lifecycle

### Task States

```
┌──────────┐    create     ┌──────────┐
│          │ ────────────► │          │
│  (none)  │               │  ACTIVE  │◄──── resume after crash
│          │               │          │
└──────────┘               └────┬─────┘
                                │
                   ┌────────────┼────────────┐
                   │            │            │
                   ▼            ▼            ▼
              ┌────────┐  ┌─────────┐  ┌──────────┐
              │  DONE  │  │ STALLED │  │ CANCELLED│
              └────────┘  └─────────┘  └──────────┘
```

| State | Meaning | Trigger |
|---|---|---|
| `ACTIVE` | Task is executing through SDLC phases | Task creation, crash resume |
| `DONE` | Task completed successfully — final checkpoint marked stable | Phase reaches `Done` |
| `STALLED` | Task cannot make progress — budget exhausted, unrecoverable error | Budget violation (critical), max retries exceeded |
| `CANCELLED` | Task explicitly cancelled by user | `sdlc_cancel_task()` |

### Phase States

Each phase in a task's history has its own status:

```
PENDING → IN_PROGRESS → SUBMITTED → ACCEPTED
                                   → REJECTED → (retry or escalate)
                       → SKIPPED (if phase has no work)
```

### The Task Model

```python
class Task(BaseModel):
    task_id: str                           # Unique identifier
    description: str                       # Natural language requirement
    mode: str = "feature"                  # Graph template selector
    status: TaskStatus = TaskStatus.ACTIVE
    current_phase: str = "Chatting"        # Current FSM position
    history: list[PhaseRecord]             # Ordered phase execution log
    iteration_count: int = 0              # Total retry iterations
    budget: BudgetPolicy                   # Resource ceilings
    snapshot: ExecutionSnapshot | None      # Determinism snapshot
    locked_prompts: dict[str, str]         # Prompt hash locks per phase
    requires_approval: bool = False        # Human-in-the-loop flag
```

---

## Execution Policy

`ExecutionPolicy` is the **decision engine** for budget, retry, and failure classification. The FSM calls the Policy; the Policy never calls the FSM.

### Budget Checking

```python
async def check_budget(task: Task, budget: BudgetPolicy) -> Decision:
    # Check max_review_cycles (default: 8)
    if task.iteration_count >= budget.max_review_cycles:
        return Decision(action=ABORT, reason="max review cycles exceeded")
    
    # Check max_runtime_minutes (default: 60)
    elapsed = (now - task.created_at).total_seconds() / 60
    if elapsed > budget.max_runtime_minutes:
        return Decision(action=ABORT, reason="runtime exceeded")
    
    return Decision(action=PROCEED, reason="budget OK")
```

### Failure Classification

The policy classifies errors into **retryable** vs **terminal** categories:

| Category | Type | Examples | Strategy |
|---|---|---|---|
| **Retryable** | `model_timeout` | Timeout, connection reset | Exponential backoff (2^attempt seconds) |
| **Retryable** | `infra_transient` | Database locked, disk full | Exponential backoff |
| **Retryable** | `debate_timeout` | Debate agent unresponsive | Retry with fallback model |
| **Terminal** | `validation_failed` | Schema error, missing section | Abort immediately |
| **Terminal** | `phase_mismatch` | Invalid phase transition | Abort immediately |
| **Terminal** | `sandbox_violation` | Permission denied, bwrap error | Abort immediately |
| **Terminal** | `dependency_gone` | Model not found, not pulled | Abort immediately |
| **Terminal** | `consensus_stalemate` | No consensus after max rounds | Abort immediately |

### Retry Decisions

```python
async def decide_retry(failure: FailureType, attempt: int) -> Decision:
    if failure is retryable and attempt < MAX_RETRY_ATTEMPTS:
        return Decision(action=RETRY, retry_after_s=2**attempt)
    if failure is retryable and attempt >= MAX_RETRY_ATTEMPTS:
        return Decision(action=ABORT, reason="max retries exceeded")
    if failure is terminal:
        return Decision(action=ABORT, reason="terminal failure")
```

---

## Graduated Retry System

The `RetryPolicy` extends basic retry logic with a **5-level escalation ladder**:

```
Level 1: LOCAL_RETRY      — Retry the same operation (syntax fix, lint fix)
Level 2: LOCAL_REPLAN     — Re-approach the same micro-task differently
Level 3: PHASE_RETRY      — Retry the entire phase from scratch
Level 4: STRUCTURAL_REPLAN — Re-plan downstream phases (Replanner)
Level 5: FULL_RECOVERY    — Restore from last stable checkpoint (RollbackManager)
```

### Escalation Logic

```
failure → classify → can_retry at recommended level?
                        ├─ YES → consume retry, execute at that level
                        └─ NO  → escalate to next level
                                    ├─ escalation possible? → consume + execute
                                    └─ no more levels → ABORT
```

### Failure Classification

```python
# Mapping: error pattern → (failure_type, recommended_level)
"syntax", "indent", "parse"   → (syntax,      LOCAL_RETRY)
"test", "assert", "expect"    → (test,        LOCAL_RETRY)
"lint", "ruff", "style"       → (lint,        LOCAL_RETRY)
"timeout", "timed out"        → (timeout,     PHASE_RETRY)
"import", "module"            → (integration, STRUCTURAL_REPLAN)
"crash", "segfault", "killed" → (crash,       FULL_RECOVERY)
```

### No-Progress Detection

The retry policy tracks effectiveness and detects when retries aren't making progress:

```python
def no_progress_detected(phase: str, window: int = 3) -> bool:
    """If the last N retries all failed, we're stuck."""
    recent = [a for a in self._attempts if a.phase == phase][-window:]
    return all(not a.succeeded for a in recent)
```

When no progress is detected, the system escalates to the next retry level regardless of remaining budget at the current level.

---

## Structured Debate System

### Why Debate Exists

Single-reviewer LLM evaluation is unreliable. A single reviewer tends to either:
- Approve everything (rubber-stamp)
- Reject everything (hypercritical)
- Focus on a single concern category (blind spots)

Multi-agent debate with structured rounds addresses these failure modes by:
1. Ensuring multiple perspectives (specs, coding, testing reviewers)
2. Detecting when agents are just agreeing without substance (sycophantic collapse)
3. Preserving minority positions (dissenting views that may be valid)
4. Forcing convergence through deliberation (agents see each other's reasoning)

### 3-Round Protocol

```
Round 1: INDEPENDENT
  ├─ Each agent reviews output independently
  ├─ No agent sees any other agent's response
  └─ Each agent provides PASS/FAIL with detailed reasoning

Round 2: DELIBERATION
  ├─ Each agent sees ALL Round 1 responses
  ├─ Agents may revise their position
  ├─ Agents must explain if they change their verdict
  └─ Explicit disagreement is encouraged

Round 3: FINAL
  ├─ Each agent provides definitive PASS/FAIL
  ├─ No further deliberation occurs
  └─ Residual objections are captured for the record
```

### Agent Role Assignment

Different phases get different reviewer panels:

```python
phase_agents = {
    "Specs":    [specs_reviewer, planning_reviewer],
    "Planning": [planning_reviewer, coding_reviewer, specs_reviewer],
    "Coding":   [coding_reviewer, review_reviewer, testing_reviewer],
    "Review":   [review_reviewer, coding_reviewer, testing_reviewer],
    "Testing":  [testing_reviewer, coding_reviewer, review_reviewer],
}
```

### Consensus Evaluation

After each round, the `ConsensusEngine` evaluates whether consensus has been reached:

1. **LLM-based consensus** (primary): A neutral judge LLM evaluates all agent responses and produces a structured verdict:
   ```json
   {
     "passed": true/false,
     "reason": "...",
     "disagreement_areas": ["..."],
     "agent_verdicts": {"specs": true, "coding": false},
     "minority_positions": [{"agent": "coding", "position": "...", "severity": "warning"}],
     "sycophancy_risk": "none|low|medium|high"
   }
   ```

2. **Majority vote fallback**: If the LLM consensus call fails, falls back to text-based PASS/FAIL extraction with majority rule.

### Sycophantic Collapse Detection

The system actively detects when agents are "just agreeing" without genuine reasoning:

```python
COLLAPSE_KEYWORDS = [
    "i agree", "i concur", "same here", "as previously stated",
    "ditto", "echo", "second that", "nothing to add",
    "no further comments", "i have no objections",
]

# If >= 60% of agents use collapse keywords, flag it
if match_count / total_agents >= COLLAPSE_THRESHOLD:
    return CollapseSignal(detected=True, confidence=ratio)
```

When collapse is detected:
- The debate continues for one more round (if rounds remain)
- The consensus result includes a collapse warning
- The confidence gate may reject the output despite unanimous approval

### Residual Objection Tracking

Objections raised in Round 1 that are still present in the final round are captured as **residual objections**:

```python
def extract_residual_objections(all_rounds):
    # If Round 1 mentioned "issue/problem/concern/bug/fail"
    # AND the final round still mentions "still/remains/not addressed/persists"
    # → This is a residual objection
```

These are attached to the consensus result for downstream visibility.

---

## Confidence Gating

The `ConfidenceGate` enforces quality thresholds on approval decisions:

### Gate Logic

```
Unanimous approval AND avg confidence >= 0.7 → APPROVE
Non-unanimous, low-confidence disapprovals   → SYNTHESIZE (merge concerns)
Non-unanimous, high-confidence disapprovals  → CONTINUE_DEBATE
Avg confidence below threshold               → CONTINUE_DEBATE
```

### Role-Based Confidence Normalization

Each voter role has confidence bounds:
- `tool`: [0.0, 1.0] — Tools should be binary (0 or 1)
- `reviewer`: [0.0, 1.0] — Full range
- `architect`: [0.0, 1.0] — Full range
- `security`: [0.0, 1.0] — Full range

Votes are clamped to their role bounds before aggregation.

### Confidence Drift Detection

The gate tracks approval decisions over time and detects drift:

```python
def detect_drift(window=5):
    recent_avg = average confidence of last 5 decisions
    older_avg  = average confidence of the 5 before that
    drift = recent_avg - older_avg
    
    if abs(drift) > 0.15:
        # Confidence is shifting — either improving or degrading
        return {"drift_detected": True, "direction": "improving" | "degrading"}
```

This signals to the orchestrator that review quality may be changing — either the system is getting better at producing good output, or the reviewers are getting lazy.

---

## Orchestrator Authority

`OrchestratorAuthority` is the **centralized governance engine** — no component may advance phases, continue debate, retry, replan, or rollback without explicit approval.

### Authority Request Types

| Type | Requester | Decision Logic |
|---|---|---|
| `phase_transition` | Phase controller | Check blocked transitions list |
| `debate_continue` | DebateRuntime | Always approved (debate is self-limiting) |
| `retry` | RetryPolicy | Track retry counts per phase, enforce max |
| `replan` | Replanner | Always approved with condition: preserve stable work |
| `recovery` | RecoveryEngine | Always approved with conditions: restore checkpoint, validate state |
| `rollback` | RollbackManager | Always approved with condition: never corrupt stable phases |
| `budget` | BudgetController | Check if task budget is exhausted |

### Explicit Blocking

The orchestrator can explicitly block specific transitions:

```python
authority.block_transition("Review", "Specs")  # Never allow review-to-specs regression
```

Blocked transitions are permanent for the lifetime of the authority instance.

---

## Dynamic Replanning

When execution stalls, the `Replanner` determines what work to invalidate and what to preserve:

### Invariant: PRESERVE COMPLETED STABLE WORK

```
Task: build-api
Phases: [Specs✓, Planning✓, Coding✓, Testing✗, Review, Done]
                                       ▲
                                  failure here

Replanner analysis:
  - Specs:    ✓ marked stable → PRESERVE
  - Planning: ✓ marked stable → PRESERVE
  - Coding:   ✓ not stable    → INVALIDATE (downstream of failure)
  - Testing:  ✗ failed        → INVALIDATE (trigger phase)
  - Review:   pending         → INVALIDATE
```

### Dependency-Aware Invalidation

The replanner considers phase dependencies:

```python
phase_deps = {
    "Testing": ["Coding"],      # Testing depends on Coding
    "Review":  ["Testing"],     # Review depends on Testing
}

# If Coding is invalidated, Testing and Review are also invalidated
# even if they haven't been reached yet
```

This prevents cascading failures where an invalidated upstream phase produces inconsistent downstream results.
