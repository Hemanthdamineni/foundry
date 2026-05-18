# Runtime & State Management

> How Foundry persists state, manages checkpoints, handles crash recovery, enforces budgets, and maintains execution determinism.

---

## State Management Architecture

### The Three State Files

Foundry maintains three categories of persistent state files, each written atomically via `tmp+rename` to prevent corruption:

```
data/state/
├── state.json           → Global runtime state
├── task_{id}.json       → Per-task execution state
└── phase_{id}.json      → Current phase execution state
```

### Global State

```python
class GlobalState(BaseModel):
    version: int = 1                      # Schema version for migration
    active_tasks: list[str]               # Currently executing task IDs
    server_started_at: str                # Server start timestamp
    last_checkpoint_at: str               # Last global checkpoint
    total_tasks_completed: int = 0        # Lifetime completion count
    total_tasks_failed: int = 0           # Lifetime failure count
```

The global state tracks system-wide metrics and the set of active tasks. On startup, the state manager reads this file to discover which tasks were in-progress when the server last shut down.

### Per-Task State

```python
class TaskState(BaseModel):
    task_id: str
    status: str = "active"                # active, done, stalled, cancelled
    current_phase: str = "Chatting"       # Current FSM position
    mode: str = "feature"                 # Graph template
    iteration_count: int = 0              # Total retry iterations
    retry_counts: dict[str, int]          # Per-phase retry counts
    phase_outputs: dict[str, str]         # Phase → output content
    validator_results: dict[str, Any]     # Phase → validation results
    unresolved_risks: list[str]           # Outstanding risk items
    files_modified: list[str]             # Files touched by this task
    last_stable_checkpoint: str | None    # Checkpoint to resume from
    git_branch: str | None                # Git branch for isolation
    last_commit_sha: str | None           # Last known clean commit
```

This file contains everything needed to resume a task after a crash. The `last_stable_checkpoint` field points to the checkpoint version that should be restored on recovery.

### Phase State

```python
class PhaseState(BaseModel):
    task_id: str
    phase: str                            # Current phase name
    sub_phase: str = ""                   # Sub-phase for complex phases
    started_at: str                       # Phase start timestamp
    integration_state: dict[str, Any]     # Adapter/integration state
    micro_task_index: int = 0             # Progress through micro-tasks
    total_micro_tasks: int = 0            # Total micro-tasks in phase
    validation_tier: str = "microtask"    # microtask, phase, milestone
```

Phase state captures fine-grained progress within a phase. This enables mid-phase recovery — if the system crashes during a coding phase that has 5 micro-tasks, it can resume from micro-task #3 rather than restarting the entire phase.

### Atomic Write Protocol

All state file writes use the same atomic pattern:

```python
def _atomic_write(self, path: Path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)  # atomic on POSIX
```

**Why this matters:** `rename()` is atomic on POSIX filesystems. If the process crashes during `write_text()`, the `.tmp` file is corrupt but the original `.json` file is untouched. If it crashes during `rename()`, the filesystem guarantees either the old or new file exists — never neither, never a partial file.

---

## Checkpoint System

### Base vs Enhanced Checkpoints

Foundry has two checkpoint managers:

| Manager | Module | Features |
|---|---|---|
| `CheckpointManager` | `engine/checkpoint.py` | Single latest checkpoint per task |
| `EnhancedCheckpointManager` | `runtime/enhanced_checkpoint.py` | Versioned chains, restore points, replay |

The MCP server uses the base `CheckpointManager` for the main write queue. The enhanced manager is available for advanced recovery scenarios.

### Versioned Checkpoint Chains

The enhanced checkpoint manager maintains a **version chain** per task:

```
data/checkpoints/
├── task_abc123_chain.json      → Chain metadata (versions, restore points)
├── task_abc123_v1.json         → Checkpoint at Specs phase
├── task_abc123_v2.json         → Checkpoint at Planning phase
├── task_abc123_v3.json         → Checkpoint at Coding phase (marked stable)
├── task_abc123_v4.json         → Checkpoint at Testing phase (failed)
└── ...
```

Each checkpoint version records:

```python
class CheckpointVersion(BaseModel):
    version: int                  # Monotonically increasing
    phase: str                    # Phase at checkpoint time
    created_at: str               # ISO timestamp
    sha: str = ""                 # Git SHA at checkpoint time
    tag: str = ""                 # Git tag (if tagged)
    is_stable: bool = False       # Marked stable by orchestrator
    label: str = ""               # Human-readable label
```

### Restore Points

Named restore points provide **semantic rollback targets**:

```python
# Before a risky operation:
checkpoint_mgr.create_restore_point(task_id, "pre-refactor", reason="About to restructure API")

# If it goes wrong:
checkpoint = checkpoint_mgr.rollback_to_restore_point(task_id, "pre-refactor")
```

### Checkpoint Data Contents

Each checkpoint file contains the full task state needed for recovery:

```python
class Checkpoint(BaseModel):
    task_id: str
    phase: str                            # Phase at checkpoint time
    history: list[PhaseRecord]            # Complete phase execution history
    iteration_count: int                  # Current iteration
    adapter_states: dict[str, Any]        # LLM adapter state
    created_at: datetime
    snapshot: ExecutionSnapshot | None     # Determinism snapshot
    debate_active: list[str]              # Active debate phases
```

### Replay Sequences

The checkpoint chain supports **replay** — re-executing a task from any checkpoint version:

```python
sequence = checkpoint_mgr.get_replay_sequence(task_id)
# Returns ordered list: [v1, v2, v3, ...] with phase + timestamp + stability

diff = checkpoint_mgr.get_diff_between(task_id, version_a=2, version_b=4)
# Returns: {phase_a, phase_b, history_diff, iteration_diff}
```

---

## Budget Enforcement

### Budget Architecture

```
BudgetPolicy (configuration)
    │
    ├── max_total_tokens: 100,000
    ├── max_review_cycles: 8
    ├── max_debate_rounds: 3
    ├── max_runtime_minutes: 60
    ├── fallback_depth: 2
    └── max_debate_budget_tokens: 15,000

BudgetController (runtime enforcement)
    │
    ├── Token tracking (per-phase + total)
    ├── Runtime watchdog (elapsed vs max)
    ├── Retry budget (per-phase counts)
    ├── Phase timeout (per-phase timers)
    └── Resource limits (concurrent tasks, queue depth)
```

### Budget Violation Severities

| Severity | Meaning | Action |
|---|---|---|
| `warning` | Approaching limit (80%+ of token budget) | Log warning, continue execution |
| `error` | Limit exceeded for a single phase (retry budget exhausted) | Escalate to next retry level |
| `critical` | Hard ceiling hit (total tokens, total runtime) | Abort task immediately |

### The should_continue() Gate

Before every phase transition, the orchestrator calls:

```python
can_continue, reason = budget_controller.should_continue(task_id, phase)
if not can_continue:
    # Task is over — reason explains why
    # e.g., "Runtime budget exhausted: 3601s / 3600s"
```

This is the single point where budget enforcement meets execution flow.

### Phase-Level Token Distribution

Per-phase token budgets are auto-allocated as `total_tokens / 6` (one-sixth of total budget per phase). This is a heuristic — phases that generate more text (Coding) naturally consume more tokens than phases that produce structured output (Specs).

---

## Execution Determinism

### The Problem

Non-deterministic execution makes debugging impossible. If a task fails, you need to answer:
- Were the same prompts used?
- Was the same model used?
- Did the phases execute in the same order?
- Can I reproduce this execution?

### Deterministic Execution IDs

Every execution context gets either a **deterministic** or **replay-safe** ID:

```python
# Deterministic: same seed → same ID
exec_id = sha256(f"{task_id}:{phase}:{iteration}:{seed}")[:16]

# Replay-safe: timestamp + random (for unique tracing)
exec_id = f"{YYYYMMDDHHMMSS}_{uuid4_hex[:8]}"
```

### Prompt Hash Locking

When a task starts, all judge prompt templates are read and their hashes are locked:

```python
# At task creation time:
locked_prompts = {
    "judge_specs_to_planning": hash(prompt_content),
    "judge_planning_to_coding": hash(prompt_content),
    ...
}

# At execution time:
if not execution_runtime.verify_prompt(phase, current_hash):
    raise DeterminismViolation("Prompt changed since task started")
```

This guarantees that if a task is replayed, the same prompts are used — even if the prompt files have been modified in the meantime.

### Model Routing Locks

Similarly, model assignments per phase are locked at task creation:

```python
execution_runtime.lock_model("Coding", "qwen3:8b")
execution_runtime.lock_model("Review", "qwen3:8b")

# Later:
model = execution_runtime.get_model("Coding")  # Always returns "qwen3:8b"
```

### Artifact Contracts

Phases can declare **artifact contracts** — expected outputs that must be produced:

```python
execution_runtime.register_artifact_contract("Specs", "specification.md", required=True)
execution_runtime.register_artifact_contract("Planning", "plan.yaml", required=True)

# After phase execution:
result = execution_runtime.validate_artifacts("Specs", {"specification.md": hash})
# result: {valid: True, validated: ["specification.md"], missing: []}
```

### Transition Recording

Every phase transition is recorded for replay:

```python
class PhaseTransition(BaseModel):
    from_phase: str
    to_phase: str
    execution_id: str
    reason: str          # Why this transition happened
    approved_by: str     # Who approved it (orchestrator, judge, etc.)
    timestamp: str
    deterministic: bool  # True if this was a deterministic transition
```

The full transition log can be extracted for debugging:

```python
log = execution_runtime.get_transition_log()
# [{"from_phase": "Specs", "to_phase": "Planning", "reason": "judge passed", ...}, ...]
```

---

## Rollback System

### The Invariant

**ROLLBACK MUST NEVER CORRUPT STABLE COMPLETED PHASES.**

If Specs and Planning passed and were marked stable, and then Coding fails — a rollback to Coding must leave Specs and Planning untouched. The rollback manager enforces this by:

1. **Tracking stable phases** — `mark_phase_stable(task_id, "Specs")`
2. **Tracking phase-file ownership** — `register_phase_files(task_id, "Coding", ["api.py", "tests.py"])`
3. **Planning rollbacks before executing** — `plan_rollback(target)` returns what will be reverted and what's protected

### Rollback Planning

```python
plan = rollback_manager.plan_rollback(RollbackTarget(
    task_id="abc",
    target_phase="Planning",
    reason="Coding produced unrecoverable errors",
))

# Returns:
{
    "files_to_revert": ["api.py", "tests.py"],     # Files owned by Coding+
    "phases_to_revert": ["Coding", "Testing"],      # Non-stable phases after target
    "protected_files": ["spec.md", "plan.yaml"],    # Files owned by stable phases
    "stable_phases_preserved": ["Specs", "Planning"],
    "safe": True  # No overlap between revert and protected sets
}
```

### Safety Check

The `safe` field indicates whether the rollback is conflict-free. If `safe` is `False`, it means a file would be both reverted and protected — the rollback manager refuses to execute unsafe rollbacks.

### Git Coordination

Rollback records include git state for external verification:

```python
class RollbackRecord(BaseModel):
    git_sha_before: str          # Git HEAD before rollback
    git_sha_after: str           # Git HEAD after rollback
    files_reverted: list[str]    # Files actually reverted
    phases_preserved: list[str]  # Stable phases that were untouched
    validation_passed: bool      # Post-rollback validation result
```

---

## Memory System

### Architecture

```
MemoryStore (structured retrieval API)
    │
    └── Acervo (storage backend)
            │
            ├── Phase summaries
            ├── Error memory
            ├── Decision records
            └── Pattern memory
```

### Memory Types

| Type | Purpose | Importance Score | Tags |
|---|---|---|---|
| **Phase Summary** | What happened in each phase (outcome, decisions, files, errors) | 0.8 | `phase_summary`, phase name, outcome |
| **Error Memory** | Past failures with resolutions for pattern matching | 0.9 | `error`, error type, phase |
| **Decision Record** | Why decisions were made, alternatives considered | 0.7 | `decision`, phase |
| **Pattern Memory** | Recurring patterns and anti-patterns | 0.6 | `pattern`, category |

### Error Memory Pattern Matching

When a new error occurs, the memory store searches for previously resolved similar errors:

```python
async def find_similar_error(error_message: str) -> ErrorMemory | None:
    # Extract top 5 keywords (length > 3 chars) from error message
    # Query Acervo with keywords + "error" tag
    # Return first resolved match
```

This enables the system to apply known fixes to recurring errors without re-discovering the solution.

### Phase Context Retrieval

Before executing a phase, the orchestrator can request all relevant context:

```python
context = await memory_store.get_context_for_phase(task_id, "Coding")
# Returns:
{
    "phase_summaries": [...],     # What happened in Specs, Planning
    "relevant_errors": [...],    # Past coding errors with resolutions
    "past_decisions": [...],     # Architecture decisions from earlier phases
    "total_memory_items": 12
}
```

### Engram Model

All memory is stored as **Engrams** — tagged, scored knowledge units:

```python
class Engram(BaseModel):
    engram_id: str            # Unique identifier
    task_id: str              # Owning task
    phase: str                # Phase where created
    content: str              # Natural language content
    tags: list[str]           # Retrieval tags
    source: str               # Origin (phase_summary, error_memory, etc.)
    importance: float = 0.5   # 0.0-1.0 retrieval priority
    created_at: str
    metadata: dict[str, Any]  # Structured data for deserialization
```

---

## Write Queue

### Async Write Pipeline

All writes to the store and checkpoint manager flow through an async write queue:

```
tool call → WriteOp → WriteQueue → WriteHandler → Store/Checkpoint/Memory
```

This decouples the MCP tool response from the actual write, ensuring:
1. Tool calls return quickly (no blocking on disk I/O)
2. Writes are ordered (FIFO queue)
3. Multiple write targets are handled atomically

### WriteOp Dispatch

```python
class WriteOp(BaseModel):
    target: str       # "task", "checkpoint", "phase_output", "memory"
    action: str       # "create", "update"
    payload: dict
    source_span: str  # Tracing span ID for correlation
```

The write handler dispatches based on `target`:

```python
if op.target == "task":
    await store.create_task(op.payload) or await store.update_task(...)
elif op.target == "checkpoint":
    checkpoint_mgr.save(Checkpoint(**op.payload))
    await store.save_checkpoint(...)
elif op.target == "phase_output":
    await store.save_phase_output(...)
elif op.target == "memory":
    await acervo.store(...)
```

---

## Observability

### Tracing Architecture

Foundry uses a lightweight distributed tracing system based on JSONL files:

```
data/traces/
├── {trace_id_1}.jsonl      → Spans for trace 1
├── {trace_id_2}.jsonl      → Spans for trace 2
├── errors/                 → Error traces (preserved longer)
│   └── {trace_id_3}.jsonl
└── summaries.jsonl         → Aggregated trace summaries
```

### Span Model

```python
class TraceSpan:
    trace_id: str              # Groups spans into a single trace
    span_id: str               # Unique within trace
    parent_span_id: str | None # Parent span (for nesting)
    phase: str                 # SDLC phase
    tool: str                  # MCP tool that triggered this span
    message: str               # Human-readable description
    level: str                 # info, warning, error
    task_id: str               # Associated task
    metadata: dict             # Arbitrary structured data
    timestamp: str             # ISO creation time
    duration_ms: int           # Execution duration
    error: str | None          # Error message if failed
```

### Retention Policy

```
Error traces:     Preserved indefinitely (moved to errors/ directory)
Successful traces: Deleted after 7 days
Raw spans:        Deleted after 30 days
Summaries:        Append-only JSONL (never deleted)
```

### MCP Debug Tools

The tracing system is exposed through MCP tools for the host agent:

| Tool | Purpose |
|---|---|
| `sdlc_get_trace(trace_id)` | Read all spans for a trace |
| `sdlc_list_traces(task_id?)` | List all trace IDs (optionally filtered by task) |
| `sdlc_get_summaries()` | Read aggregated summaries |
| `sdlc_enforce_retention()` | Manually trigger retention cleanup |
