# Observability & Tracing

> Tracing architecture, span model, retention policy, telemetry schema, debugging workflows, metrics, and replay analysis.

---

## Tracing Architecture

### Overview

Foundry uses a lightweight JSONL-based distributed tracing system. Each trace is a collection of related spans representing the execution of a single logical operation (e.g., a submit_output call).

```
data/traces/
├── {trace_id_1}.jsonl      → Spans for trace 1
├── {trace_id_2}.jsonl      → Spans for trace 2
├── errors/                 → Error traces (preserved indefinitely)
│   └── {trace_id_3}.jsonl
└── summaries.jsonl         → Aggregated trace summaries
```

### Trace ID Generation

```python
def create_trace_id(self) -> str:
    return uuid.uuid4().hex[:16]
```

Trace IDs are 16-character hex strings. They correlate all spans within a single logical operation.

### Span ID Generation

```python
def create_span_id(self) -> str:
    return uuid.uuid4().hex[:12]
```

Span IDs are 12-character hex strings. Each span is unique within its trace.

---

## Span Model

### Full Span Schema

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

### Span Levels

| Level | Meaning | Retention Impact |
|---|---|---|
| `info` | Normal operation | Standard retention (7 days) |
| `warning` | Degraded operation (fallback, timeout, skip) | Standard retention |
| `error` | Failed operation | Moved to `errors/` directory (indefinite retention) |

### Span Metadata Examples

**submit_output span:**
```json
{
    "task_id": "abc123",
    "phase": "Coding",
    "judge_verdict": {"passed": true, "reason": "..."},
    "debate_transcript": {"rounds": 3, "consensus_reached": true},
    "iteration_count": 2,
    "next_phase": "Testing"
}
```

**create_task span:**
```json
{
    "task_id": "abc123",
    "mode": "feature",
    "description": "Add user authentication..."
}
```

**index span:**
```json
{
    "files_indexed": 42,
    "symbols_found": 186,
    "duration_ms": 1200
}
```

---

## Retention Policy

```python
ERROR_RETENTION_DAYS = None      # Errors preserved indefinitely
NORMAL_RETENTION_DAYS = 7        # Successful traces: 7 days
RAW_SPAN_RETENTION_DAYS = 30     # Raw span files: 30 days
SUMMARIES_RETENTION = "forever"  # Summaries are append-only, never deleted
```

### Enforcement Flow

```
enforce_retention()
    │
    ├── Scan data/traces/ directory
    │
    ├── For each trace file:
    │   ├── Parse creation time from first span
    │   ├── Check for error-level spans
    │   │
    │   ├── Has errors?
    │   │   ├── Yes → Move to data/traces/errors/ (preserve indefinitely)
    │   │   └── No → Check age
    │   │
    │   ├── Age > 30 days → Delete file
    │   ├── Age > 7 days → Delete if no errors
    │   └── Age ≤ 7 days → Keep
    │
    └── Append summary to summaries.jsonl (never deleted)
```

### Manual Trigger

```
MCP tool: sdlc_enforce_retention()
```

This triggers immediate retention cleanup. Normally, retention is enforced at server startup.

---

## Trace Summary System

### Summary Record

After retention processing, each trace gets a summary appended to `summaries.jsonl`:

```json
{
    "trace_id": "abc123def456...",
    "task_id": "task_abc",
    "phase": "Coding",
    "tool": "sdlc_submit_output",
    "status": "success",
    "duration_ms": 3200,
    "span_count": 5,
    "error_count": 0,
    "created_at": "2025-01-15T10:30:00Z",
    "retained": true
}
```

### Summary Queries

Summaries are read as raw JSONL lines. Common queries:

```python
# All summaries for a task
summaries = [s for s in all_summaries if s["task_id"] == task_id]

# Error summaries
errors = [s for s in all_summaries if s["error_count"] > 0]

# Slow operations
slow = [s for s in all_summaries if s["duration_ms"] > 5000]
```

---

## MCP Debug Tools

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `sdlc_get_trace(trace_id)` | trace_id | List of spans | Read all spans for a specific trace |
| `sdlc_list_traces(task_id?)` | Optional task_id filter | List of trace IDs | List all available traces |
| `sdlc_get_summaries()` | None | List of summaries | Read aggregated trace summaries |
| `sdlc_enforce_retention()` | None | Cleanup stats | Trigger retention enforcement |

### Example Debug Session

```
Agent: sdlc_list_traces(task_id="abc123")
→ [{"trace_id": "t1", "phase": "Coding", "tool": "sdlc_submit_output", "has_error": false},
   {"trace_id": "t2", "phase": "Coding", "tool": "sdlc_submit_output", "has_error": true}]

Agent: sdlc_get_trace(trace_id="t2")
→ [
    {"span_id": "s1", "phase": "Coding", "tool": "sdlc_submit_output", "level": "info", ...},
    {"span_id": "s2", "phase": "Coding", "tool": "judge_evaluate", "level": "error",
     "error": "Judge rejected: Missing ## Files Modified section", ...},
  ]
```

---

## Debugging Workflows

### Workflow 1: Why Did a Phase Transition Fail?

```
1. sdlc_get_status(task_id) → Check current_phase, iteration_count, history
2. sdlc_list_traces(task_id) → Find trace IDs for submit_output calls
3. sdlc_get_trace(failing_trace_id) → Read spans
4. Find span with tool="sdlc_submit_output" → Check metadata.judge_verdict
5. If judge rejected:
   - Check judge_verdict.issues for specific problems
   - Check judge_verdict.severity for blocking level
6. If debate ran:
   - Check metadata.debate_transcript
   - Look for sycophantic collapse signal
   - Check minority reports for dissenting views
```

### Workflow 2: Why Is a Task Stuck?

```
1. sdlc_get_status(task_id) → Check status
   - If "stalled" → Budget was exhausted (check budget stats)
   - If "active" → Still running, check what's happening

2. Check retry state:
   - Look at task history → Count rejected submissions per phase
   - If many rejections → Judge is blocking; read judge verdicts

3. Check budget consumption:
   - task.budget → See configured limits
   - iteration_count → How many attempts have been made

4. Last resort:
   - sdlc_get_trace for latest trace → See what the last operation was
   - If no recent traces → Server may have crashed; check checkpoint
```

### Workflow 3: How Do I Resume a Crashed Task?

```
1. After server restart, state is loaded from disk:
   - task_{id}.json contains current_phase, history, iteration_count
   - Checkpoint files contain full recoverable state

2. Call sdlc_get_status(task_id) → Verify task state
3. Call sdlc_get_next_action(task_id) → Get next step
4. Continue execution from last checkpoint
```

### Workflow 4: Auditing a Completed Task

```
1. sdlc_get_status(task_id) → Full task status with complete history
2. For each phase in history:
   - Check status (accepted/rejected)
   - Check iteration_count (how many attempts)
   - Check output (what was produced)
3. sdlc_get_summaries() → Trace summaries for timing and error counts
4. Checkpoint chain → Version history with stable markers
```

---

## Telemetry Schema

### Structured Log Format

All logs use structured JSON via `sdlc.log.get_logger()`:

```json
{
    "timestamp": "2025-01-15T10:30:00Z",
    "level": "info",
    "logger": "engine.orchestrator",
    "message": "Phase transition",
    "extra": {
        "task_id": "abc123",
        "from_phase": "Coding",
        "to_phase": "Testing",
        "iteration": 2
    }
}
```

### Log Categories

| Logger Name | Component | Key Events |
|---|---|---|
| `engine.orchestrator` | OrchestratorFSM | Phase transitions, ambiguity errors |
| `engine.debate_runtime` | DebateRuntime | Round starts, agent responses, timeouts |
| `engine.consensus` | ConsensusEngine | Collapse detection, verdict synthesis |
| `engine.confidence_gate` | ConfidenceGate | Gate decisions, drift detection |
| `engine.retry_policy` | RetryPolicy | Escalation events, effectiveness scores |
| `engine.recovery_engine` | RecoveryEngine | Recovery classification, counter resets |
| `engine.replanner` | Replanner | Invalidation scopes, stable preservation |
| `engine.drift_detector` | DriftDetector | Layer violations, cycle detection |
| `engine.context_harvester` | ContextHarvester | Question generation, environment analysis |
| `engine.prompt_registry` | PromptRegistry | Prompt registration, rollback, compatibility |
| `runtime.app` | MCP Server | Tool calls, lifespan events |
| `runtime.state_manager` | StateManager | State reads/writes |
| `runtime.write_queue` | WriteQueue | Queue operations |
| `runtime.tracing` | Tracer | Span recording, retention enforcement |
| `runtime.tool_gate` | ToolGate | Gate evaluations, failures |
| `runtime.budget_controller` | BudgetController | Budget checks, violations |
| `acervo` | Acervo | Engram storage/retrieval |

### Performance Metrics (Available from Components)

| Metric | Source | Access |
|---|---|---|
| Task iteration count | `Task.iteration_count` | `sdlc_get_status()` |
| Phase duration | `PhaseRecord.duration_ms` | Task history |
| Token estimate | `PhaseRecord.token_estimate` | Task history |
| Debate round count | `DebateTranscript.rounds` | Task history |
| Gate pass/fail counts | `ToolGate.history` | In-memory |
| Retry counts per phase | `RecoveryEngine._retry_counts` | `recovery_engine.get_stats()` |
| Budget consumption | `BudgetController` | `budget_controller.get_stats()` |
| Index file count | `IndexPipeline.stats` | `sdlc_get_index_stats()` |
| Engram count | `Acervo.stats` | In-memory |

---

## Replay Analysis

### What Replay Means

Replay is the process of re-executing a task from a specific checkpoint version. It is used for:
1. **Debugging** — Understanding why a task failed by replaying from a checkpoint
2. **Validation** — Verifying that a fix resolves the failure
3. **Regression testing** — Confirming that system changes don't break existing behavior

### Replay Sequence

```python
sequence = checkpoint_mgr.get_replay_sequence(task_id)
# [
#   {"version": 1, "phase": "Specs", "timestamp": "...", "stable": True},
#   {"version": 2, "phase": "Planning", "timestamp": "...", "stable": True},
#   {"version": 3, "phase": "Coding", "timestamp": "...", "stable": False},
# ]
```

### Version Diffing

```python
diff = checkpoint_mgr.get_diff_between(task_id, version_a=1, version_b=3)
# {
#   "phase_a": "Specs",
#   "phase_b": "Coding",
#   "history_diff": 2,        # Additional history entries
#   "iteration_diff": 3,      # Iteration count change
# }
```

### Replay Limitations

- **LLM non-determinism** — Same prompt produces different outputs. Replay verifies orchestration logic, not LLM quality.
- **No time machine** — External state (filesystem, git, MCP tool outputs) is not recorded. Replay uses current external state.
- **Prompt hash verification** — Replay checks that prompt hashes match the checkpoint. If prompts have changed, replay warns.
