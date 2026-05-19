---
name: sdlc
description: "SDLC — Structured Software Development Lifecycle with phase-gated reviews, validation, and checkpoint recovery."
trigger: /sdlc
---

# SDLC — Structured Development Lifecycle Server

SDLC is an MCP server that enforces a phase-gated software development process. It provides tools for creating tasks, transitioning through phases, evaluating outputs, and maintaining task state via SQLite and checkpoint persistence.

Run `sdlc-mcp` from your PATH.

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

## Full Tool Reference

### Workspace Management

**`sdlc_detect_workspace(path?, workspace?)`**
- Detects execution and Foundry workspace roots
- Parameters: `path` (optional, ignored), `workspace` (optional, ignored)
- CLI `--workspace` flag or `FOUNDRY_WORKSPACE` env var override auto-detection
- Returns: `{execution_root: str, workspace_root: str, detection_reason: str}`
- Auto-detection: Searches from CWD upward for `.sdlc/` directory, `pyproject.toml`, `setup.py`, or `.git`
- Error: If no workspace found, detection_reason explains what was missing. Run `bootstrap_workspace` to create one.

**`sdlc_bootstrap_workspace(path?, workspace?)`**
- Idempotently creates or repairs `.sdlc/` infrastructure
- Creates directory structure: `config/`, `graphs/`, `checkpoints/`, `traces/`
- Creates SQLite database at `.sdlc/sdlc.db`
- Generates workflow graph templates
- Idempotent: Safe to run multiple times; existing valid state is preserved

**`sdlc_upgrade_workspace(path?, workspace?)`**
- Upgrades `.sdlc/` schema and generated files to match the current server version
- Usage: After updating `sdlc-mcp` package to a newer version

### Task Lifecycle

**`sdlc_create_task(description: str, mode: str = "feature")`**
- Creates a new SDLC task
- `description` (required): Free-text description of what the task should accomplish
- `mode` (optional, default `"feature"`): Workflow mode. Only `"feature"` supports full execution.
- Returns: `{task_id: str, phase: str, status: str, created_at: str}`
- The task starts in `chatting` phase with `active` status
- Error: If workspace is not found, returns error. Call `bootstrap_workspace` first.

**`sdlc_get_next_action(task_id: str)`**
- Returns the current phase and any context for the task
- Returns: `{task_id: str, phase: str, status: str, context: dict}`
- `context` includes: previous phase output, task description, current FSM state
- Usage: After `resume_task` to know where to continue

**`sdlc_get_status(task_id: str)`**
- Returns current task status
- Returns: `{task_id: str, phase: str, status: str, retry_count: int, error_info: str | null}`
- `status` can be: `"active"`, `"completed"`, `"stalled"`, `"cancelled"`
- `retry_count`: Number of ToolGate retries attempted (0 if not in gate)
- `error_info`: Details when status is `"stalled"`

**`sdlc_list_tasks(status: str | null = null)`**
- Lists all tasks, optionally filtered by status
- `status` values: `"active"`, `"completed"`, `"stalled"`, `"cancelled"`
- Returns: Array of `{task_id, description, phase, status, created_at}`

**`sdlc_cancel_task(task_id: str)`**
- Cancels a task immediately
- Sets status to `"cancelled"`, writes final checkpoint
- Usage: When task is STALLED or user wants to abandon

### Phase Validation & Submission

**`sdlc_submit_output(task_id: str, phase: str, output: str, next_phase: str | null = null)`**
- **Primary submission path.** Submits phase output through the 8-stage validation pipeline:
  1. **Load task**: Verify task exists and is in an active state
  2. **Phase match**: Verify `phase` matches the task's current phase
  3. **FSM resolution**: Compute next phase from workflow graph
  4. **Schema validation** (deterministic): Check required Markdown section headers via `schema_checks.py`
     - Schema checks are pure string matching — mismatched header names cause hard rejection
  5. **LLM Judge**: LLM evaluates completeness, quality, spec alignment
  6. **ToolExecutor** (Coding/Testing only): Write files to disk per the output
  7. **ToolGate** (Coding/Testing only): Run validation toolchain
     - Coding: `ruff check .` → `mypy src/` → `pytest` → coverage → `bandit -r src/`
     - Testing: `ruff check .` → `mypy src/` → `pytest` → coverage
     - Transient failures: retry 3× with exponential backoff (1s, 2s, 4s)
     - Non-transient failures: reject immediately
  8. **WriteQueue**: Commit to SQLite + write checkpoint file
- Returns: `{task_id, phase, status, next_phase, validation_results, gate_results}`
- On success: Task advances to `next_phase`
- On schema rejection: Response includes `missing_sections` list
- On judge rejection: Response includes `judge_feedback` with improvement suggestions
- On gate failure: Response includes `gate_results` with per-tool status

**`sdlc_validate_phase(task_id: str, phase: str, output: str, next_phase: str | null = null, include_llm: bool = false, include_debate: bool = false)`**
- **Dry-run validation** — runs stages 1-5 but does NOT advance the task or execute ToolGate
- `include_llm`: Run LLM Judge evaluation (default false)
- `include_debate`: Run multi-agent debate (default false)
- Returns validation results without side effects
- Usage pattern: Always validate before submit to catch issues early

**`sdlc_request_approval(task_id: str, phase: str, summary: str, approved: bool = false)`**
- Request human approval: Set `approved=false`, provide `summary` of what needs approval
- Grant approval: Call with `approved=true`
- Returns: Updated task state with approval status

### Recovery

**`sdlc_resume_task(task_id: str)`**
- Restores a task from its latest checkpoint
- Reconciliation algorithm: Merge SQLite state + checkpoint JSON, pick most recent consistent state per field
- Returns: `{task_id, phase, status, restored_phase, last_output}`
- Usage: After agent restart, process crash, or network interruption
- Error: If no checkpoint exists, returns raw SQLite state (least recent state)

### Multi-Agent & Memory

**`sdlc_debate_output(task_id: str, phase: str, output: str)`**
- Spawns multiple LLM subagents to evaluate the output from different perspectives
- Returns: `{transcript: str, agreements: list, disagreements: list}`
- Usage: Optional, for controversial outputs or when consensus is needed

**`sdlc_memory_store(content: str, task_id: str = "", phase: str = "", tags: list[str] | null = null, source: str = "unknown", importance: float = 0.5)`**
- Store a memory entry
- `importance`: 0.0 (trivial) to 1.0 (critical). Used for retrieval prioritization.
- `tags`: Free-form tags for filtering

**`sdlc_memory_query(phase: str | null = null, tags: list[str] | null = null, keywords: list[str] | null = null, source: str | null = null, min_importance: float = 0.3, limit: int = 10)`**
- Query stored memories with filters
- Returns: Matching entries sorted by importance desc, then recency

**`sdlc_memory_stats()`**
- Returns: `{total_entries, by_tag: dict, by_source: dict, avg_importance}`

### Repository Indexing

**`sdlc_index_repository(mode: str = "incremental")`**
- `mode`: `"incremental"` (only new/changed files) or `"full"` (re-index everything)

**`sdlc_index_files(file_paths: list[str])`**
- Index specific files by path

**`sdlc_get_dependency_context(file_path: str)`**
- Returns: `{file_path, imports, imported_by, dependencies}`
- Usage: Understand what a file depends on and what depends on it

**`sdlc_get_index_stats()`**
- Returns: `{total_files, total_symbols, last_indexed, index_version}`

### Tracing

**`sdlc_get_trace(trace_id: str)`**
- Returns full trace details

**`sdlc_list_traces(task_id: str | null = null)`**
- Lists traces, optionally filtered by task

**`sdlc_get_summaries()`**
- Returns summaries of all task traces

**`sdlc_enforce_retention()`**
- Cleans traces older than the configured retention policy

## The Submission Pipeline

```
sdlc_submit_output()
  │
  ├─ 1. Load Task ───────────── SQLite lookup
  ├─ 2. Phase Match ─────────── Verify phase == current phase
  ├─ 3. FSM Resolution ──────── Compute next phase from workflow graph
  ├─ 4. Schema Validation ───── Check Markdown headers (deterministic)
  │      FAIL → return missing_sections, REJECT
  ├─ 5. LLM Judge ───────────── Evaluate completeness & quality
  │      FAIL → return judge_feedback, REJECT
  ├─ [6. ToolExecutor] ──────── Write files (Coding/Testing only)
  ├─ [7. ToolGate] ──────────── Run toolchain (Coding/Testing only)
  │      ├─ lint (ruff)
  │      ├─ types (mypy)
  │      ├─ tests (pytest)
  │      ├─ coverage
  │      └─ security (bandit, Coding only)
  │      FAIL (transient) → retry 3× (1s, 2s, 4s backoff)
  │      FAIL (permanent) → REJECT immediately
  │      All retries exhausted → STALLED
  └─ 8. WriteQueue ──────────── SQLite commit + checkpoint file
         SUCCESS → advance phase, return updated task
```

### Required Section Headers (Schema Validation)

| Phase | Required `##` Headers |
|---|---|
| Chatting | None (free-form) |
| Specs | `## Requirements`, `## Scope`, `## Constraints` |
| Planning | `## Implementation Plan`, `## File Changes`, `## Risks` |
| Coding | `## Files Modified` |
| Review | `## Issues Found`, `## Severity`, `## Must Fix` |
| Testing | `## Test Results`, `## Coverage`, `## Failed` |
| Done | None (free-form) |

**Warning:** Schema validation is purely string-based. `## Requirements` is a match, `## Requirements Overview` is NOT a match. Use the exact header names listed above.

## ToolGate Retry Semantics

1. Gate starts: Run `ruff check .`
2. If ruff fails with exit code ≠ 0:
   - Check if failure is transient (timeout, OOM, permission error)
   - Transient → wait 1s → retry
   - Non-transient (actual lint error) → FAIL immediately, return to caller
3. After 3 transient retries exhausted → task enters STALLED state
4. Same pattern for mypy, pytest, coverage, bandit
5. Gates run sequentially — if one gate fails, later gates are NOT executed

### Recovery from STALLED

1. `sdlc_get_status(task_id)` confirms STALLED and shows `error_info`
2. Fix the issue (code fix, dependency install, config change)
3. `sdlc_submit_output(task_id, phase, output)` — resubmission resets retry counter
4. Alternatively: `sdlc_cancel_task(task_id)` to abandon

## Checkpoint Recovery

If the agent process is interrupted:
1. `sdlc_detect_workspace()` to re-establish context
2. `sdlc_resume_task(task_id)` to restore state
3. `sdlc_get_next_action(task_id)` to get current phase
4. Continue execution

Checkpoint files are at `.sdlc/checkpoints/<task_id>.json`. Each checkpoint records:
- Task ID, phase, status
- FSM state
- Timestamp
- Last output summary

## Error Troubleshooting

| Error | Cause | Action |
|---|---|---|
| Schema validation failed | Missing `## Required Header` | Add exact header name to output |
| Phase mismatch error | Submitted phase ≠ current phase | Call `get_next_action` to check current phase |
| Task not found | Invalid/missing `task_id` | Verify `task_id` from `create_task` response |
| ToolGate lint failure | `ruff` found style/quality errors | Fix lint errors, resubmit |
| ToolGate types failure | `mypy` found type errors | Fix type annotations, resubmit |
| ToolGate tests failure | `pytest` found failures | Fix test failures, resubmit |
| ToolGate security failure | `bandit` found vulnerabilities | Fix security issues, resubmit |
| Task STALLED | All ToolGate retries exhausted | Fix issue, resubmit; or cancel |
| Workspace not detected | No `.sdlc/` in CWD or parents | Run `bootstrap_workspace` |

## Phase Prompt References

Each phase has a corresponding prompt file in:
- `.opencode/skills/foundry/prompts/<phase>.md` (Foundry workflow)
- `.opencode/skills/sdlc/prompts/<phase>.md` (SDLC workflow)

These prompt files contain detailed instructions for what to produce in each phase, including the exact section headers required for schema validation.

## Subagent Prompts

SDLC subagent prompts are in `.opencode/skills/sdlc/prompts/`:
- `specs.txt` — Requirements elicitation subagent
- `plan.txt` — Implementation planning subagent
- `code.txt` — Code generation subagent
- `review.txt` — Code review subagent
- `tester.txt` — Test generation subagent

These contain detailed input/output specifications for the subagent LLM calls used in SDLC mode.

## Usage

```
/sdlc
```

Then describe what you want to build. The agent will:
1. Detect workspace
2. Create a task
3. Step through Chatting → Specs → Planning → Coding → Review → Testing → Done
4. Submit each phase through the validation pipeline
5. Handle any rejections, retries, or stalls
