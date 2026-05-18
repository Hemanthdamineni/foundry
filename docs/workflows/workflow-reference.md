# Workflow Reference

> How Foundry's user-facing workflows map to internal subsystem orchestration. Build, debug, review, test, and research workflows.

---

## Workflow Architecture

Users interact with Foundry through high-level workflow commands. Each workflow maps to a specific phase graph template and a set of internal behaviors:

```
User: "foundry build <description>"
    │
    └── Workflow Layer (translates intent to lifecycle)
            │
            ├── Select phase graph template (feature, bugfix, refactor, etc.)
            ├── Configure budget policy
            ├── Determine approval requirements
            └── Create task → enter lifecycle
```

**Key principle:** Users see workflows; they never see orchestration internals (FSM, budget, retry, debate). The workflow layer is the abstraction boundary.

---

## Build Workflow

### Purpose
Transform natural language requirements into working, validated code.

### Phase Graph: `feature`

```
Chatting → Specs → Planning → Coding → Testing → Review → Done
                                           ↺        ↺
                                    (test failures) (review failures)
```

### Lifecycle

| Step | Phase | What Happens | Subsystems Active |
|---|---|---|---|
| 1 | **Chatting** | Clarify requirements, ask questions | Context input only |
| 2 | **Specs** | Generate specification with Requirements, Scope, Constraints | ContextHarvester, SchemaChecks, JudgeEngine |
| 3 | **Planning** | Decompose into implementation plan with file changes and risks | SchemaChecks, JudgeEngine, DriftDetector |
| 4 | **Coding** | Implement each planned change, modify files | ToolGate (lint, types), IndexPipeline |
| 5 | **Testing** | Run tests, validate coverage | ToolGate (tests, coverage, security) |
| 6 | **Review** | Multi-agent debate on code quality | DebateRuntime, ConsensusEngine, JudgeHierarchy |
| 7 | **Done** | Summarize results, output completion report | Memory store (phase summaries) |

### Budget (Default)

| Resource | Limit |
|---|---|
| Total tokens | 100,000 |
| Review cycles | 8 |
| Debate rounds | 3 per phase |
| Runtime | 60 minutes |

### Failure Handling

```
Coding test failure → Back to Coding (retry)
Coding lint failure → Fix and resubmit (retry)
Review rejection → Back to Coding (fix issues)
Budget exhausted → Abort task (status: stalled)
All retries exhausted → Escalate through recovery levels
```

### Approval Gate

By default, no human approval required. When `requires_approval=True`:
- After Specs phase, the system pauses for human review
- `sdlc_request_approval(task_id, phase, summary, approved=True)` continues
- No approval = task stays paused indefinitely

---

## Debug Workflow

### Purpose
Diagnose and fix a specific bug or issue.

### Phase Graph: `bugfix` (planned)

```
Chatting → Debugging → Coding → Testing → Done
                                    ↺
                             (test failures)
```

### Differences from Build

| Aspect | Build | Debug |
|---|---|---|
| Phases | 7 (full SDLC) | 5 (focused) |
| Specs phase | Yes (full requirements) | No (bug description is the spec) |
| Planning phase | Yes (implementation plan) | No (debugging plan embedded in Debugging phase) |
| Review phase | Yes (full multi-agent review) | No (testing is sufficient) |
| Context | Broad workspace context | Focused on affected files + stack trace |
| Budget | 100K tokens | 50K tokens (smaller scope) |

### Debugging Phase

The Debugging phase (not yet implemented) will:
1. Analyze the error message / stack trace
2. Search error memory for similar past failures
3. Identify affected files via index pipeline
4. Generate a focused diagnosis with root cause analysis
5. Propose a fix strategy

---

## Review Workflow

### Purpose
Review existing code changes (e.g., a PR or recent modifications) without the full build lifecycle.

### Phase Graph: `review` (planned)

```
Chatting → Review → Done
```

### Differences from Build

| Aspect | Build | Review |
|---|---|---|
| Phases | 7 | 3 |
| Code generation | Yes | No |
| Testing | Yes (runs tests) | No (checks existing test results) |
| Debate | Yes (after coding) | Yes (the entire workflow is debate) |
| Output | Working code | Review report with issues + recommendations |

---

## Research Workflow

### Purpose
Investigate a technical question without producing code.

### Phase Graph: `research` (planned)

```
Chatting → Research → Analysis → Done
```

### Key Differences

- No file editing in any phase
- No tool gates (nothing to lint/test)
- No debate (single agent research)
- Output: structured analysis document
- Budget: 50K tokens (research is cheaper than build)

---

## Workflow → Subsystem Mapping

### Which subsystems activate per workflow

| Subsystem | Build | Debug | Review | Research |
|---|---|---|---|---|
| OrchestratorFSM | ✓ | ✓ | ✓ | ✓ |
| PhaseGraph | ✓ | ✓ | ✓ | ✓ |
| ExecutionPolicy | ✓ | ✓ | ✓ | ✓ |
| JudgeEngine | ✓ | ✓ | ✗ | ✗ |
| JudgeHierarchy | ✓ | ✗ | ✓ | ✗ |
| DebateRuntime | ✓ | ✗ | ✓ | ✗ |
| ConsensusEngine | ✓ | ✗ | ✓ | ✗ |
| ConfidenceGate | ✓ | ✗ | ✓ | ✗ |
| ToolGate | ✓ | ✓ | ✗ | ✗ |
| ContextHarvester | ✓ | ✗ | ✗ | ✗ |
| DriftDetector | ✓ | ✗ | ✓ | ✗ |
| IndexPipeline | ✓ | ✓ | ✓ | ✓ |
| MemoryStore | ✓ | ✓ | ✗ | ✗ |
| CheckpointManager | ✓ | ✓ | ✓ | ✓ |
| BudgetController | ✓ | ✓ | ✓ | ✓ |
| RetryPolicy | ✓ | ✓ | ✗ | ✗ |
| RecoveryEngine | ✓ | ✓ | ✗ | ✗ |
| Replanner | ✓ | ✗ | ✗ | ✗ |
| RollbackManager | ✓ | ✓ | ✗ | ✗ |
| Tracer | ✓ | ✓ | ✓ | ✓ |

---

## MCP Tool Flow Per Workflow

### Build Workflow Tool Call Sequence

```
1. sdlc_create_task(description, mode="feature")
   → Returns: task_id, initial_phase="Chatting"

2. sdlc_get_next_action(task_id)
   → Returns: phase="Chatting", prompt, context, constraints

3. [Agent performs Chatting — clarifies requirements]

4. sdlc_submit_output(task_id, "Chatting", output)
   → Returns: accepted=True, next_phase="Specs"

5. sdlc_get_next_action(task_id)
   → Returns: phase="Specs", prompt, context, constraints

6. [Agent generates specification]

7. sdlc_submit_output(task_id, "Specs", output)
   → Judge evaluates → Schema checks → LLM judge
   → Returns: accepted=True/False

   If rejected:
     → Agent reads issues, fixes, resubmits (go to step 6)

8. [Repeat for Planning, Coding, Testing, Review]

9. When task.current_phase == "Done":
   → sdlc_submit_output(task_id, "Done", summary)
   → Task status → "done"
```

### Status Monitoring

At any point:
```
sdlc_get_status(task_id) → Full status with history
sdlc_list_tasks() → All tasks
sdlc_cancel_task(task_id) → Cancel if stuck
```

---

## The get_next_action Response

This is the most information-dense tool response — it tells the agent exactly what to do:

```python
{
    "task_id": "abc123",
    "phase": "Coding",
    "phase_index": 3,                          # Position in graph
    "subagent": "dev-sdlc",                    # Which subagent to invoke
    "model": "qwen3:8b",                       # Which model to use
    "fallback_models": ["qwen3:4b"],           # Fallback if primary fails
    "prompt": "You are executing the Coding phase...",  # Full phase prompt
    "context": {
        "task_description": "Add user auth...", # Original description
        "previous_outputs": [...],              # Specs + Planning outputs
        "relevant_files": ["auth.py", ...],     # From index pipeline
        "context_chunks": [...],                # Code chunks for context
        "graph_summary": {...},                 # Dependency graph
    },
    "constraints": {
        "must_produce": "Output must reference specific files modified.",
        "must_not_do": [],                      # Empty for Coding/Testing
        "bash_allowed_patterns": ["test", "build", "lint", "git *"],
    },
    "mode": "feature",
    "requires_approval": false,
    "progress": 50.0,                          # 0-100% through graph
}
```

---

## Installation & Bootstrap

### Current: Manual Setup

```bash
# Clone
git clone https://github.com/Hemanthdamineni/foundry.git
cd foundry

# Python runtime
pip install -e .

# Start
python -m sdlc
```

### Planned: npx Installation

```bash
npx --yes github:Hemanthdamineni/foundry
```

The installer (`foundry/install/install.js`) will:
1. Link skills to `~/.config/opencode/skills/foundry/`
2. Link agents to `~/.config/opencode/agents/`
3. Install Python runtime (pip or pixi)
4. Register MCP server in OpenCode config
5. Pull required Ollama models

After installation:
```
User: "foundry build <description>"
→ OpenCode loads SKILL.md instructions
→ Calls sdlc_create_task()
→ Enters autonomous lifecycle
```
