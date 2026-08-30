---
name: foundry
description: "Foundry: SDLC runtime with phase-gated development process, validation, checkpoint recovery, debate, and SQLite persistence."
trigger: /foundry
---

# Foundry: Structured Development Lifecycle Server

Foundry is an MCP server that enforces a phase-gated software development process. It provides tools for creating tasks, transitioning through phases, validating outputs, running multi-agent debate, indexing the repository, and persisting state via SQLite and checkpoints.

Run `foundry mcp` from your PATH (or `pixi run mcp` inside the pixi env). With no arguments it starts the Foundry MCP server over stdio. Run `foundry init` once per workspace to bootstrap the `.sdlc/` directory and SQLite store before creating tasks.

The MCP server's tool surface is split into functional groups. By default, all phase reasoning uses the model currently selected in OpenCode. Runtime LLM providers are configured via `config/llm_config.yaml`.

## Phases

| Phase | Purpose | Gate |
|---|---|---|
| Chatting | Clarify task intent and scope | Schema validation |
| Specs | Requirements, scope, constraints | Schema validation |
| Planning | Implementation plan with risks and file list | Schema validation |
| Coding | Write and modify code | Schema validation + ToolGate (lint→types→tests→coverage→security) |
| Review | Code review for issues and spec alignment | Schema validation |
| Testing | Run and evaluate tests | Schema validation + ToolGate (lint→types→tests→coverage) |
| Done | Summarize accomplishments | Schema validation |

## Supported Workflows

| Workflow | Path |
|---|---|
| `feature` | Chatting → Specs → Planning → Coding → Review → Testing → Done (with Review→Coding iteration) |
| `bugfix` | Chatting → Specs → Coding → Review → Testing → Done |
| `refactor` | Chatting → Planning → Coding → Review → Testing → Done |
| `research` | Chatting → Specs → Planning → Review → Done |
| `docs` | Chatting → Specs → Coding → Review → Done |

Phase graphs are defined in `src/foundry/graphs/*.yaml`. All workflows are executable in the modernized runtime.

## Full Tool Reference

### Task Lifecycle

**`sdlc_create_task(description, mode="feature")`**
- Creates a new task with the given description.
- `description` (required): Free-text user intent.
- `mode` (optional, default `"feature"`): Workflow mode. One of `feature`, `bugfix`, `refactor`, `research`, `docs`.
- Returns: `{task_id, phase, status}`. Capture `task_id` for all subsequent calls.

**`sdlc_get_next_action(task_id)`**
- Returns the current phase and context for a task.
- Returns: `{task_id, phase, status, context, requires_approval}`.

**`sdlc_get_status(task_id)`**
- Returns current task status with history.
- Returns: `{task_id, phase, status, history, retry_count, error_info}`.

**`sdlc_list_tasks(status?)`**
- Lists all tasks, optionally filtered by status (`"active"`, `"completed"`, `"stalled"`, `"cancelled"`).

**`sdlc_cancel_task(task_id)`**
- Cancels a task, regardless of current phase.

**`sdlc_resume_task(task_id)`**
- Restores a task from its latest checkpoint.
- Returns: `{task_id, phase, status, restored_state}`.

### Phase Validation & Submission

**`sdlc_submit_output(task_id, phase, output, next_phase?)`**
- Primary submission path. Submits phase output through the validation pipeline:
  1. Load task (verify exists, not terminal)
  2. Phase match check
  3. FSM resolution
  4. Schema validation (deterministic section-header checks)
  5. Judge evaluation (when wired)
  6. ToolGate (Coding/Testing only): lint(ruff) → types(mypy) → tests(pytest) → coverage → security(bandit)
  7. WriteQueue persistence (SQLite + checkpoint)
- Returns: `{task_id, phase, status, accepted, judge_verdict, gate_results, next_phase}`.
- `output` must include required Markdown section headers for the phase.
- `next_phase` (optional): explicit override.

**`sdlc_request_approval(task_id, phase, summary, approved=False)`**
- Requests or grants human approval for a phase transition.
- `summary`: what approval is being requested for.
- `approved` (optional, default `false`): grant approval.

**`sdlc_schema_check(task_id, phase, output)`**
- Dry-run schema validation only. Useful for catching section-header issues before `sdlc_submit_output`.

### Tracing & Observability

**`sdlc_get_trace(trace_id)`**
- Returns the JSONL trace for a given trace_id.

**`sdlc_list_traces(task_id?, since?, limit?)`**
- Lists available trace files.

**`sdlc_get_summaries(task_id?)`**
- Returns compacted trace summaries.

**`sdlc_enforce_retention()`**
- Runs the trace retention policy (errors forever, successful 7d, raw spans 30d, compacted summaries permanent).

### Repository Indexing

**`sdlc_index_repository(path, incremental=True)`**
- Indexes the workspace for symbol/dependency lookup.

**`sdlc_index_files(paths)`**
- Indexes specific files.

**`sdlc_get_dependency_context(workspace_path)`**
- Returns the dependency graph context for the workspace.

**`sdlc_get_index_stats()`**
- Returns index statistics.

**`sdlc_query_symbols(query, kind?, file_pattern?, limit?)`**
- Searches the symbol index.

**`sdlc_get_callers(symbol_id, depth=1)`**
- Returns callers of a given symbol.

**`sdlc_get_symbol_context(symbol_id, max_lines=50)`**
- Returns the surrounding context for a symbol.

**`sdlc_harvest_context(phase, task_id)`**
- Harvests relevant context for a phase.

**`sdlc_check_spec_drift(task_id)`**
- Detects drift between current state and the original spec.

### Multi-Agent Debate (turn-engine based)

**`sdlc_debate_get_turn(turn_id)`**
- Returns the current state of a debate turn.

**`sdlc_debate_submit_turn(turn_id, position, evidence_refs)`**
- Submits a debate position with structured evidence references.

### Agent Loop (turn-engine based)

**`sdlc_agent_get_turn(turn_id)`**
- Returns the current state of an agent-loop turn.

**`sdlc_agent_submit_turn(turn_id, output)`**
- Submits an agent-loop turn output.

### Memory

**`sdlc_memory_store(content, task_id?, phase?, tags?, source?, importance?)`**
- Stores a memory entry for cross-task recall.
- `importance`: 0.0 to 1.0 (default 0.5).

**`sdlc_memory_query(phase?, tags?, keywords?, source?, min_importance?, limit?)`**
- Queries stored memories with filters. Returns up to `limit` (default 10) entries.

**`sdlc_memory_stats()`**
- Returns memory storage statistics.

### Resources

- `sdlc://phase-graph` — the current phase graph definition.

## Task Loop

For each task, the agent should:
1. `sdlc_create_task(description, mode)` — create the task
2. `sdlc_get_next_action(task_id)` — get the current phase and context
3. `sdlc_harvest_context(phase, task_id)` — get relevant code context
4. Generate the phase output (see `prompts/{phase}.md` for the section-header template)
5. `sdlc_schema_check(task_id, phase, output)` — pre-validate section headers
6. `sdlc_submit_output(task_id, phase, output)` — submit
7. Repeat from step 2 until `next_phase == "Done"`

## Human-in-the-Loop

When a phase requires human approval (`sdlc_get_next_action` returns `requires_approval=true`), present the plan to the user and call `sdlc_request_approval`. The OpenCode plugin (`sdlc-enforcer.ts`) blocks file edits until approval is granted.

## Phase Prompts

See `prompts/chatting.md`, `prompts/specs.md`, `prompts/planning.md`, `prompts/coding.md`, `prompts/review.md`, `prompts/testing.md`, `prompts/done.md` for the section-header templates and output guidance for each phase.
