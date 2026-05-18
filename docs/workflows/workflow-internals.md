# Workflow Internals

> Deep build lifecycle, MCP tool call sequences, get_next_action response schema, approval gates, and workflow-to-subsystem mappings.

---

## Build Workflow: Complete Tool Call Sequence

### Phase 1: Task Creation

```
Host Agent                          Foundry
    │                                  │
    ├── sdlc_create_task ─────────►   │
    │   {description, mode="feature"} │
    │                                  ├── Create Task model
    │                                  ├── Lock judge prompts
    │                                  ├── Write to store
    │                                  ├── Create checkpoint v1
    │                                  │
    │   ◄──────────────────────────   │
    │   {task_id, phase="Chatting"}   │
```

### Phase 2: Execution Loop

```
LOOP until phase == "Done" or budget exhausted:
    │
    ├── sdlc_get_next_action ─────►  Foundry
    │   {task_id}                     ├── Load task from store
    │                                  ├── Check budget → should_continue()
    │                                  ├── Route model for phase
    │                                  ├── Build phase prompt
    │                                  ├── Gather context (index + memory)
    │                                  ├── Compute progress
    │   ◄──────────────────────────   │
    │   {phase, model, prompt,        │
    │    context, constraints}        │
    │                                  │
    │   Host executes phase with      │
    │   own LLM and tools             │
    │                                  │
    ├── sdlc_submit_output ────────►  Foundry
    │   {task_id, output}             ├── Verify correct phase
    │                                  ├── Schema checks (deterministic)
    │                                  ├── LLM judge evaluation
    │                                  ├── [If rejected] Debate protocol
    │                                  ├── [If rejected] Consensus evaluation
    │                                  ├── Authority approval
    │                                  ├── FSM transition
    │                                  ├── Save phase output
    │                                  ├── Create checkpoint
    │   ◄──────────────────────────   │
    │   {accepted, new_phase,         │
    │    rejection_reason}            │
```

### Phase 3: Completion

```
    ├── sdlc_get_status ──────────►  Foundry
    │   {task_id}                     ├── Load task
    │                                  ├── Compute final stats
    │   ◄──────────────────────────   │
    │   {status="completed",          │
    │    phase="Done",                │
    │    history=[...]}               │
```

---

## get_next_action Response Schema

```python
{
    # Identity
    "task_id": str,
    "phase": str,                      # Current phase name
    "phase_index": int,                # 0-based position in graph
    "mode": str,                       # "feature", "bugfix", etc.
    
    # Model routing
    "subagent": str,                   # "dev-sdlc" or phase-specific
    "model": str,                      # Primary model
    "fallback_models": list[str],      # Ordered fallback chain
    
    # Execution guidance
    "prompt": str,                     # Full phase prompt
    "context": {
        "task_description": str,
        "previous_outputs": list[str],
        "relevant_files": list[str],
        "context_chunks": list[dict],
        "graph_summary": dict,
    },
    "constraints": {
        "must_produce": str,           # Required output structure
        "must_not_do": list[str],      # Phase restrictions
        "bash_allowed_patterns": list[str],
    },
    
    # Progress
    "requires_approval": bool,         # Human approval gate?
    "progress": float,                 # 0.0 - 100.0
}
```

---

## submit_output Response Schema

```python
# Accepted
{
    "accepted": True,
    "phase": str,                      # New phase after transition
    "verdict_reason": str,             # Judge reasoning
    "debate_result": dict | None,      # Debate transcript if ran
    "consensus_result": dict | None,   # Consensus details if ran
}

# Rejected
{
    "accepted": False,
    "phase": str,                      # Same phase (no transition)
    "rejection_reason": str,           # Why rejected
    "recovery_action": str,            # "retry", "replan", "abort"
    "retry_context": str,              # Error details for retry prompt
}
```

---

## Approval Gates

### When Approval Is Required

```yaml
# Phase graph configuration
phases:
  Specs:
    requires_approval: true    # User reviews spec before planning
  Planning:
    requires_approval: false
  Coding:
    requires_approval: false
  Review:
    requires_approval: true    # User reviews final code
```

### Approval Flow

```
submit_output passes validation
    │
    ├── requires_approval = false → auto-transition → next phase
    │
    └── requires_approval = true  → status = "awaiting_approval"
                                      │
                                      ├── sdlc_request_approval(task_id, approved=true)
                                      │   → transition to next phase
                                      │
                                      └── sdlc_request_approval(task_id, approved=false)
                                          → stay in current phase, retry
```

---

## Debug Workflow

```
sdlc_create_task(description, mode="bugfix")
    → Chatting → Debugging → Coding → Testing → Done

Debugging phase:
    - Receives: bug description + full codebase context
    - Produces: root cause analysis + fix strategy
    - No file editing allowed

Coding phase:
    - Receives: debugging analysis + relevant files
    - Produces: fix implementation
    - File editing + shell commands allowed
```

### Subsystem Activation

| Subsystem | Build | Debug | Review |
|---|---|---|---|
| PhaseGraph | feature graph | bugfix graph | review graph |
| JudgeEngine | All phases | Debugging + Coding | Review only |
| DebateRuntime | Configurable | Coding only | Not used |
| IndexPipeline | Full index | Targeted index | Full index |
| ContextHarvester | Pre-spec | Not used | Not used |
| BudgetController | Full enforcement | Reduced limits | Minimal |
| RecoveryEngine | Full escalation | 3-level (no replan) | 2-level (retry only) |

---

## Implementation Status

| Workflow | Status |
|---|---|
| Build (feature) | **Implemented** — full SDLC lifecycle |
| Debug (bugfix) | **Partial** — phase graph planned, not wired |
| Review | **Partial** — phase graph planned, not wired |
| Research | **Not implemented** — conceptual only |
