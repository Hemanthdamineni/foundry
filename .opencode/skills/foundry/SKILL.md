---
name: foundry
description: "Foundry: SDLC runtime with phase-gated development process, validation, checkpoint recovery, and SQLite persistence."
trigger: /foundry
---

# Foundry: Structured Development Lifecycle Server

Foundry is an MCP server that enforces a phase-gated software development process. It provides tools for creating tasks, transitioning through phases, validating outputs, and persisting state via SQLite and checkpoints.

Run `sdlc-mcp` from your PATH. With no arguments it starts the Foundry MCP server over stdio; `sdlc-mcp bootstrap` repairs the current workspace.

By default, all phase reasoning uses the model currently selected in OpenCode. Runtime LLM providers are disabled unless `.sdlc/config/llm_config.yaml` explicitly enables them.

## Phases

| Phase | Purpose | Gate |
|---|---|---|
| Chatting | Clarify task intent and scope via `question` tool | Schema validation + LLM Judge |
| Specs | Requirements, scope, constraints | Schema validation + LLM Judge |
| Planning | Implementation plan with risks and file list | Schema validation + LLM Judge |
| Coding | Write and modify code | Schema validation + LLM Judge + ToolGate (lint→types→tests→coverage→security) |
| Review | Code review for issues and spec alignment | Schema validation + LLM Judge |
| Testing | Run and evaluate tests | Schema validation + LLM Judge + ToolGate (lint→types→tests→coverage) |
| Done | Summarize accomplishments | Schema validation + LLM Judge |

## Supported Workflow

Only the `feature` workflow is supported:
```
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
                   ^                        |
                   +-- Review -> Coding (loop, max 3 iterations)
```

Bugfix, refactor, research, and docs workflow graph templates are scaffolded in `.sdlc/graphs/` but are **not executable**.

## Full Tool Reference

### Workspace Management

**`sdlc_detect_workspace(path?, workspace?)`**
- Detects execution and Foundry workspace roots
- Returns: `{execution_root, workspace_root, detection_reason}`
- Usage: Call without arguments to auto-detect. CLI `--workspace` flag or `FOUNDRY_WORKSPACE` env var override auto-detection.
- Error: If no workspace found, returns `detection_reason` with explanation. Call `sdlc_bootstrap_workspace` to create one.

**`sdlc_bootstrap_workspace(path?, workspace?)`**
- Idempotently creates or repairs `.sdlc/` infrastructure in the current workspace
- Creates: `.sdlc/` directory with config, graphs, schema templates, and SQLite database
- Usage: Run once per workspace, or to repair a corrupted `.sdlc/` directory
- Error: If the workspace already has a valid `.sdlc/`, it is a no-op (idempotent)

**`sdlc_upgrade_workspace(path?, workspace?)`**
- Upgrades workspace schema and generated integration files to the latest version
- Usage: After updating the Foundry package to a new version

### Task Lifecycle

**`sdlc_create_task(description, mode)`**
- Creates a new task with the given description
- `description` (required): Free-text user intent
- `mode` (optional, default `"feature"`): Workflow mode. Only `"feature"` is supported.
- Returns: `{task_id, phase, status}`
- Usage: Call after detecting workspace. Capture `task_id` for all subsequent calls.
- Error: If required context is missing (no workspace detected), returns error

**`sdlc_get_next_action(task_id)`**
- Returns the current phase and context for a task
- Returns: `{task_id, phase, status, context}`
- Usage: Call after resuming a task to know which phase to execute next

**`sdlc_get_status(task_id)`**
- Returns current task status including STALLED detection
- Returns: `{task_id, phase, status, retry_count, error_info}`
- Usage: Check after ToolGate failures to see if task entered STALLED state

**`sdlc_list_tasks(status?)`**
- Lists all tasks, optionally filtered by status
- `status` (optional): `"active"`, `"completed"`, `"stalled"`, `"cancelled"`
- Usage: Overview of all tasks in the workspace

**`sdlc_cancel_task(task_id)`**
- Cancels a task, regardless of current phase or state
- Usage: When a task is STALLED or the user wants to abandon it

### Phase Validation & Submission

**`sdlc_submit_output(task_id, phase, output, next_phase?)`**
- **Primary submission path.** Submits phase output through the 8-stage validation pipeline:
  1. **Load task**: Load task from SQLite, verify it exists and is not completed/cancelled
  2. **Phase match check**: Verify the submitted phase matches the task's current phase
  3. **FSM resolution**: Resolve the next phase based on workflow graph and current state
  4. **Schema validation (deterministic)**: Check output contains required Markdown section headers via `schema_checks.py`
  5. **LLM Judge**: Evaluate output quality, completeness, and spec alignment
  6. **ToolExecutor** (Coding/Testing only): Execute code changes on disk
  7. **ToolGate** (Coding/Testing only): Run lint(ruff) → types(mypy) → tests(pytest) → coverage → security(bandit)
  8. **WriteQueue persistence**: Commit phase transition to SQLite + checkpoint file
- Returns: `{task_id, phase, status, validation_results, gate_results}`
- `output`: Free-text Markdown. Must include required section headers for the phase being submitted (see Phase Prompts below).
- `next_phase` (optional): Explicit override for next phase (advanced use only)
- Error handling:
  - Schema rejection: Fix section headers and resubmit
  - LLM Judge rejection: Improve output quality and resubmit
  - ToolGate failure (transient): Up to 3 retries with exponential backoff
  - ToolGate failure (permanent): Immediate rejection, task stays in current phase
  - All retries exhausted: Task enters STALLED state

**`sdlc_validate_phase(task_id, phase, output, next_phase?, include_llm?, include_debate?)`**
- **Dry-run validation** without advancing the task or executing ToolGate
- Runs stages 1-5 only (load → phase match → FSM → schema → LLM Judge)
- `include_llm` (optional, default `false`): Run LLM Judge evaluation
- `include_debate` (optional, default `false`): Run multi-agent debate
- Usage: Call before `sdlc_submit_output` to check if output will pass schema and LLM validation
- Returns: Validation results without mutating task state

**`sdlc_request_approval(task_id, phase, summary, approved?)`**
- Requests or grants human approval for a phase transition
- `summary`: What approval is being requested for
- `approved` (optional, default `false`): Grant approval
- Usage: For phases that require human sign-off before proceeding

### Recovery

**`sdlc_resume_task(task_id)`**
- Restores a task from its latest checkpoint and returns resumable phase state
- Reconciliation: Merges SQLite state with latest checkpoint file
- Returns: `{task_id, phase, status, restored_state}`
- Usage: After interruption (agent restart, process crash, network failure)
- Error: If no checkpoint exists, returns the raw SQLite state

### Multi-Agent & Memory

**`sdlc_debate_output(task_id, phase, output)`**
- Runs multi-agent debate on a phase output
- Spawns multiple LLM subagents to critique the output from different perspectives
- Usage: Optional, when consensus is needed or the output is controversial
- Returns: Debate transcript with agreements and disagreements

**`sdlc_memory_store(content, task_id?, phase?, tags?, source?, importance?)`**
- Stores a memory entry for cross-task recall
- `content` (required): The memory content
- `task_id` (optional): Associate with a specific task
- `phase` (optional): Associate with a specific phase
- `tags` (optional): List of tags for retrieval
- `source` (optional, default `"unknown"`): Source identifier
- `importance` (optional, default `0.5`): 0.0 to 1.0 importance score

**`sdlc_memory_query(phase?, tags?, keywords?, source?, min_importance?, limit?)`**
- Queries stored memories with filters
- Returns: Up to `limit` (default 10) matching memory entries

**`sdlc_memory_stats()`**
- Returns memory storage statistics (total entries, by tag, by source)

### Repository Indexing

**`sdlc_index_repository(mode?)`**
- Indexes the repository for dependency-aware tooling
- `mode` (optional, default `"incremental"`): `"full"` or `"incremental"`

**`sdlc_index_files(file_paths)`**
- Indexes specific files (must be an array of paths)

**`sdlc_get_dependency_context(file_path)`**
- Returns dependency graph context for a specific file

**`sdlc_get_index_stats()`**
- Returns repository index statistics

### Tracing

**`sdlc_get_trace(trace_id)`**
- Returns a specific trace by ID

**`sdlc_list_traces(task_id?)`**
- Lists traces, optionally filtered by task

**`sdlc_get_summaries()`**
- Returns summaries of all tasks

**`sdlc_enforce_retention()`**
- Enforces trace retention policy (cleans old traces)

## The Submission Pipeline in Detail

When you call `sdlc_submit_output`, the following happens:

```
Caller → 1. Load Task → 2. Phase Match → 3. FSM Resolution
         → 4. Schema Validation (deterministic)
         → 5. LLM Judge
         → [6. ToolExecutor (Coding/Testing only)]
         → [7. ToolGate: lint → types → tests → coverage → security (Coding/Testing only)]
         → 8. WriteQueue: SQLite + Checkpoint
         → Response
```

### Stage 4: Schema Validation
Checks that the output contains the required Markdown section headers for the current phase. The checks are deterministic (not LLM-based). Required headers per phase:

| Phase | Required Sections |
|---|---|
| Chatting | None (free-form) |
| Specs | `## Requirements`, `## Scope`, `## Constraints` |
| Planning | `## Implementation Plan`, `## File Changes`, `## Risks` |
| Coding | `## Files Modified` |
| Review | `## Issues Found`, `## Severity`, `## Must Fix` |
| Testing | `## Test Results`, `## Coverage`, `## Failed` |
| Done | None (free-form) |

If any required section header is missing, the submission is **rejected immediately** with a list of missing sections. Fix the headers and resubmit.

### Stage 5: LLM Judge
An LLM evaluates the output for:
- Completeness (are all aspects covered?)
- Quality (is the reasoning sound?)
- Spec alignment (does it match the task description?)
- Format (is the output well-structured?)

If the Judge rejects the output, it returns specific improvement suggestions. Fix and resubmit.

### Stages 6-7: ToolExecutor + ToolGate (Coding/Testing only)
ToolGate runs a deterministic pipeline of tools:
1. `ruff check .` — linting
2. `mypy src/` — type checking
3. `pytest` — test suite
4. Coverage check
5. `bandit -r src/` — security scan

**Retry semantics:**
- Transient failures (timeout, network, disk full): Retry up to 3 times with exponential backoff (1s → 2s → 4s)
- Non-transient failures (lint error, type error, test failure): Reject immediately
- All retries exhausted → Task enters STALLED state

**Recovery from STALLED:**
1. Call `sdlc_get_status(task_id)` to confirm STALLED state
2. Identify the failing gate (check `gate_results` in response)
3. Fix the underlying issue (code fix, config change, etc.)
4. Call `sdlc_submit_output` again with the fixed output
5. Or call `sdlc_cancel_task(task_id)` to abandon

## Checkpoint Recovery

If the agent is interrupted (process crash, restart, network failure):
1. Call `sdlc_detect_workspace()` to re-establish workspace context
2. Call `sdlc_resume_task(task_id)` to restore from latest checkpoint
3. Call `sdlc_get_next_action(task_id)` to determine current phase
4. Continue from where you left off

The checkpoint file is written to `.sdlc/checkpoints/<task_id>.json` after every successful phase transition. `sdlc_resume_task` reconciles this checkpoint with the SQLite database, picking the most recent consistent state.

## Error Codes and Troubleshooting

| Error | Likely Cause | Fix |
|---|---|---|
| Schema validation failed | Missing required section header | Add the missing `## Section` to output |
| Phase mismatch | Submitted phase ≠ current phase | Check `sdlc_get_next_action` for correct phase |
| Task not found | Invalid task_id | Verify task_id from `sdlc_create_task` response |
| ToolGate: lint failed | Code style/quality issues | Run `ruff check .` locally, fix errors |
| ToolGate: types failed | Type annotation errors | Run `mypy src/`, fix type errors |
| ToolGate: tests failed | Test failures | Run `pytest` locally, fix failing tests |
| Task STALLED | All ToolGate retries exhausted | Fix gate issue, resubmit, or cancel task |
| Workspace not detected | No `.sdlc/` directory | Run `sdlc_bootstrap_workspace` |

## Usage Example

```
User: /foundry Build a REST API for user management

Agent:
1. sdlc_detect_workspace() → workspace detected
2. sdlc_create_task(description="Build a REST API for user management", mode="feature")
   → task_id="abc123", phase="chatting"
3. Chatting phase: Use `question` tool to ask about tech stack, features, etc.
4. sdlc_submit_output(task_id="abc123", phase="chatting", output="...")
   → phase advances to "specs"
5. Specs phase: Write requirements, scope, constraints
6. sdlc_validate_phase(task_id="abc123", phase="specs", output="...")  ← dry-run first
7. sdlc_submit_output(task_id="abc123", phase="specs", output="...")
   → phase advances to "planning"
8. ... continue through planning → coding → review → testing → done
```

## Subagent Delegation

For specialized work within a phase, delegate to subagents via OpenCode's `task` tool:

| Subagent | When to Use |
|---|---|
| planner | Transform specs into a file-level implementation plan |
| architect | Evaluate design decisions and trade-offs |
| reviewer | Review code for bugs, security, quality |
| debugger | Root cause analysis of failures |
| validator | Run lint/type/schema validation tools |
| researcher | Look up API docs, best practices, dependency info |

Subagents are helpers, not automatic orchestration steps. Use them when specialized analysis is needed.
