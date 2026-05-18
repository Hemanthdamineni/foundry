# Determinism and Replay

> Execution snapshots, prompt locking, replay engine, checkpoint versioning, regression detection, and the boundaries of determinism in an LLM-driven system.

---

## Determinism Model

Foundry distinguishes between **orchestration determinism** (what we guarantee) and **output determinism** (what we cannot guarantee). The system is deterministic in its _reaction_ to outputs, even though the outputs themselves are non-deterministic.

### What Is Deterministic

| Component | Guarantee | Mechanism |
|---|---|---|
| Phase graph traversal | Same graph always produces same transition options | YAML-defined, validated at startup, hashed |
| Schema checks | Same output always produces same pass/fail | Regex-based section detection, no LLM involvement |
| Budget enforcement | Same token/time/retry counts always produce same decision | Integer comparison against hard ceilings |
| Failure classification | Same error message always maps to same failure type | Pattern matching against fixed keyword lists |
| Retry escalation | Same retry count always produces same escalation level | Counter-based level advancement |
| Phase restrictions | Same phase always has same tool permissions | Phase name lookup in static mapping |
| Rollback safety | Same stable set always protects same phases | Set intersection check |
| Authority decisions | Same request type + state always produces same approval | Rule-based decision engine |

### What Is NOT Deterministic

| Component | Source of Non-Determinism | Mitigation |
|---|---|---|
| LLM phase output | Model sampling, even at temperature=0 | Schema checks provide deterministic minimum quality bar |
| LLM judge evaluation | Model sampling | temperature=0.0 reduces variance; fail-open on error |
| Debate agent responses | temperature=0.7 for diversity | Consensus mechanism averages across agents |
| Context retrieval | Filesystem state changes between runs | SHA-based incremental indexing with cache |
| External tool results | Lint/test/type-check outputs vary with codebase state | Deterministic tool invocation; output is ground truth |

---

## Execution Snapshots

An `ExecutionSnapshot` captures the complete deterministic configuration at a point in time, enabling verification that a replay uses the same environment:

```python
class ExecutionSnapshot(BaseModel):
    snapshot_id: str                    # Unique identifier
    created_at: datetime               # When captured
    graph_template: str                # Phase graph template name ("feature")
    graph_hash: str                    # SHA256 of phase graph YAML
    prompt_hashes: dict[str, str]      # {prompt_name: content_hash}
    model_routing_hash: str            # SHA256 of model_routing.yaml
    judge_schema_hash: str | None      # SHA256 of judge response schema
    adapter_versions: dict[str, str]   # {adapter_name: version}
    ollama_models: dict[str, str]      # {model_name: digest}
```

### What Snapshots Capture

| Field | What It Verifies | Drift Detected |
|---|---|---|
| `graph_hash` | Phase graph hasn't changed | New phases, removed transitions |
| `prompt_hashes` | Judge prompts haven't been edited | Different evaluation criteria |
| `model_routing_hash` | Model assignments haven't changed | Different model per phase |
| `ollama_models` | Local models haven't been updated | Model quality changes |
| `adapter_versions` | Tool versions haven't changed | Different lint/test behavior |

### Snapshot Lifecycle

```
Task created
    │
    ├── Capture ExecutionSnapshot
    │   ├── Hash phase graph YAML
    │   ├── Hash all locked prompts
    │   ├── Hash model routing config
    │   ├── Record Ollama model digests
    │   └── Record adapter versions
    │
    ├── Store in task.snapshot
    │
    └── Attach to every checkpoint
```

On replay, the snapshot from the checkpoint is compared against the current environment. Mismatches produce warnings (not errors — replay proceeds but with reduced confidence in comparison).

---

## Prompt Locking

### How It Works

At task creation, all judge prompt templates are loaded from disk and frozen:

```python
# In task creation:
task = Task(
    locked_prompts=settings.load_all_judge_prompts(),
    # {"judge_specs_to_planning": "Evaluate the specs output for...",
    #  "judge_planning_to_coding": "Evaluate the planning output...",
    #  ...}
)
```

During execution, the judge engine checks for locked prompts:

```python
# In JudgeEngine.evaluate():
prompt_key = f"judge_{from_phase.lower()}_to_{to_phase.lower()}"
prompt = task.locked_prompts.get(prompt_key) or self._default_prompt(from_phase, to_phase)
```

### Why Locked Prompts Matter

Without locking:
```
Task A created → judge uses prompt v1 → passes review
                                        ↓
Prompt edited to v2 (stricter criteria)
                                        ↓
Task A replayed → judge uses prompt v2 → fails review → different outcome
```

With locking:
```
Task A created → locks prompt v1 → passes review
                                    ↓
Prompt edited to v2 (stricter criteria)
                                    ↓
Task A replayed → still uses locked v1 → passes review → same outcome
```

### Prompt Registry Integration

The `PromptRegistry` provides versioned prompt management that complements locking:

```python
# Register a new prompt version
v1 = registry.register("judge_specs", "Evaluate specs for completeness...")
v2 = registry.register("judge_specs", "Evaluate specs for completeness AND correctness...")

# Task creation locks the active version at that moment
task.locked_prompts["judge_specs"] = registry.get_active("judge_specs")

# Registry can rollback, but existing tasks keep their locked versions
registry.rollback("judge_specs", to_version=1)
```

---

## Replay Engine (`engine/replay.py`, 151 lines)

### Purpose

The replay engine reconstructs execution sequences from stored traces and checkpoints for debugging and regression testing.

### Replay Session Model

```python
class ReplayStep(BaseModel):
    step_index: int                    # Position in sequence
    phase: str                         # SDLC phase
    tool: str                          # MCP tool that produced this step
    input_data: dict[str, Any]         # Input to the tool
    output_data: dict[str, Any]        # Output from the tool
    timestamp: str                     # When executed
    duration_ms: int                   # How long it took

class ReplaySession(BaseModel):
    session_id: str                    # Trace ID or checkpoint identifier
    task_id: str                       # Associated task
    steps: list[ReplayStep]            # Ordered execution steps
    source: str                        # "trace" or "checkpoint"
    status: str                        # pending, replaying, completed, failed
```

### Loading from Traces

```python
engine = ReplayEngine(trace_dir="data/traces")

# Load from a JSONL trace file
session = engine.load_from_trace("abc123def456")
# Parses each JSONL line into a ReplayStep
# Extracts task_id from first step's input_data
```

Each line in the JSONL trace file becomes a replay step. Invalid lines are silently skipped (tolerance for partial corruption).

### Loading from Checkpoints

```python
# Load from checkpoint files
session = engine.load_from_checkpoint("data/checkpoints", task_id="abc123")
# Scans for {task_id}_*.json files
# Each checkpoint file becomes a ReplayStep with tool="checkpoint"
# Ordered by filename (version number)
```

### Phase Filtering

```python
# Get all steps for a specific phase
coding_steps = engine.get_phase_replay(session_id, "Coding")
# Returns only steps where step.phase == "Coding"
```

### Regression Detection

```python
# Compare two replay sessions
diff = engine.compare_runs(session_a="trace_v1", session_b="trace_v2")
# Returns:
# {
#     "steps_a": 12, "steps_b": 15,
#     "phases_a": ["Specs", "Planning", "Coding"],
#     "phases_b": ["Specs", "Planning", "Coding", "Testing"],
#     "phase_diff": ["Testing"],  # Symmetric difference
# }
```

This identifies structural differences between runs: did the new run execute more phases? Fewer? Different ones?

---

## Checkpoint Versioning

### Chain Model

The `EnhancedCheckpointManager` maintains a versioned chain per task:

```
data/checkpoints/
├── abc123_chain.json          # Chain metadata
├── abc123_v1.json             # Version 1: after Specs
├── abc123_v2.json             # Version 2: after Planning
├── abc123_v3.json             # Version 3: after Coding
└── abc123_v4.json             # Version 4: after Testing
```

**Chain metadata:**
```json
{
    "task_id": "abc123",
    "current_version": 4,
    "versions": [
        {"version": 1, "phase": "Specs", "created_at": "...", "stable": true},
        {"version": 2, "phase": "Planning", "created_at": "...", "stable": true},
        {"version": 3, "phase": "Coding", "created_at": "...", "stable": false},
        {"version": 4, "phase": "Testing", "created_at": "...", "stable": false}
    ],
    "restore_points": {
        "after_planning": 2,
        "before_coding_retry": 3
    }
}
```

### Version Operations

```python
# Save a new version
checkpoint_mgr.save(task_id, checkpoint)
# Creates abc123_v5.json, updates chain metadata

# Restore a specific version
checkpoint = checkpoint_mgr.restore(task_id, version=2)
# Returns the Checkpoint from abc123_v2.json

# Get replay sequence
sequence = checkpoint_mgr.get_replay_sequence(task_id)
# Returns ordered list of all versions with metadata

# Compare versions
diff = checkpoint_mgr.get_diff_between(task_id, version_a=1, version_b=4)
# Returns: {"phase_a": "Specs", "phase_b": "Testing", "history_diff": 3, "iteration_diff": 5}
```

### Restore Points

Named bookmarks within the checkpoint chain:

```python
checkpoint_mgr.create_restore_point(task_id, name="before_risky_refactor")
# Records: restore_points["before_risky_refactor"] = current_version

checkpoint_mgr.restore_to_point(task_id, name="before_risky_refactor")
# Restores to the version number stored at that name
```

Restore points are semantic labels for checkpoint versions. They provide human-readable rollback targets.

---

## Replay Limitations

### LLM Non-Determinism

Same prompt + same model does NOT guarantee same output. Replay verifies **orchestration behavior** (did the system react correctly to the output?), not **output quality** (did the LLM produce the same text?).

### External State Not Recorded

Foundry does not record external state at the time of execution:
- Filesystem contents (files may have changed)
- Git state (branches, commits may differ)
- MCP tool outputs (lint/test results depend on current code)
- Network state (Ollama model weights may have been updated)

Replay uses **current** external state. This means a replay may produce different results if the codebase has changed.

### Prompt Hash Verification

On replay, prompt hashes from the checkpoint are compared to current prompts:

```python
snapshot = checkpoint.snapshot
current_hashes = registry.all_hashes()

for name, locked_hash in snapshot.prompt_hashes.items():
    current = current_hashes.get(name)
    if current != locked_hash:
        logger.warning(f"Prompt '{name}' has changed since checkpoint")
```

This warns about prompt drift but does not block replay.

---

## Implementation Status

| Component | Status |
|---|---|
| ExecutionSnapshot | **Implemented** — model fields defined, attached to tasks/checkpoints |
| Prompt locking | **Implemented** — locked_prompts dict on Task, used by JudgeEngine |
| ReplayEngine | **Implemented** — load from traces, load from checkpoints, compare runs |
| EnhancedCheckpointManager | **Implemented** — versioned chains, restore points, replay sequences |
| Snapshot verification on replay | **Partial** — snapshot fields exist but verification not automated |
| Automated regression testing | **Not implemented** — compare_runs exists but no automated test harness |
| External state recording | **Not implemented** — filesystem/git state not captured |
