# Foundry Architecture

> Authoritative reference for the modernized runtime. For design rationale
> (why decisions were made), see `docs/design/plan-original.md`. For the
> historical MVP build sequence, see `docs/history/PHASE-{0..4}-execution.md`.
> For deferred work, see `docs/TODO.md`.

## Overview

Foundry is a Python 3.12+ workspace-aware SDLC runtime. It exposes a phase-gated
development process (Specs → Planning → Coding → Review → Testing → Done) through an
MCP server and a CLI. The runtime is split across a core kernel, six sharable
packages, and eight feature modules.

## Layers

```
                  ┌─────────────────────────────────────────┐
                  │ CLI (src/foundry/cli/)                  │
                  │   12 commands: init, doctor, mcp,      │
                  │   serve, orchestrate, sdlc, dashboard,  │
                  │   eval, approve, workspaces, auth, ...  │
                  └────────────┬────────────────────────────┘
                               │
                  ┌────────────▼────────────────────────────┐
                  │ Features (src/foundry/features/)       │
                  │   sdlc_runtime, serve, mcp,              │
                  │   orchestrator, observability,           │
                  │   notifications, approval_gate,         │
                  │   eval_harness                           │
                  └────────────┬────────────────────────────┘
                               │
                  ┌────────────▼────────────────────────────┐
                  │ Core (src/foundry/core/)                │
                  │   auth, capability_router, checkpoint,  │
                  │   config, context_graph, debate,         │
                  │   event_bus, exceptions, governance,     │
                  │   guardrails, health, index, judge,      │
                  │   logging, memory, models, multi_agent,  │
                  │   orchestrator, permission_governor,     │
                  │   phases, plugins, sandbox, scheduler,   │
                  │   secrets, session, store, terminal,     │
                  │   tool_executor, tool_gate, tools,       │
                  │   tracing, turn_engine, workspace,        │
                  │   write_queue                            │
                  └────────────┬────────────────────────────┘
                               │
                  ┌────────────▼────────────────────────────┐
                  │ Shared packages (packages/)              │
                  │   sdlc-models, sdlc-store, sdlc-phases,  │
                  │   sdlc-judge, sdlc-debate, sdlc-mcp       │
                  └─────────────────────────────────────────┘
```

## Runtime Path

The authoritative task lifecycle:

```
User → foundry mcp (stdio) or foundry serve (HTTP)
     → sdlc_create_task → sdlc_get_next_action
     → [per phase: sdlc_harvest_context → generate output]
     → sdlc_schema_check (deterministic section-header validation)
     → sdlc_submit_output (phase match → FSM → schema → judge → ToolGate → WriteQueue)
     → sdlc_resume_task (on interrupt, from latest checkpoint)
     → next phase (or Done)
```

For phase transitions that require human approval, `sdlc_request_approval`
is called and the OpenCode plugin (`sdlc-enforcer.ts`) blocks file edits
until approval is granted.

## Key Boundaries

- **Core never imports LLM providers.** All model calls go through the
  `judge` / `turn_engine` modules. The MCP server's module-level docstring
  explicitly forbids LLM imports.
- **Features are siblings, not a chain.** `sdlc_runtime`, `serve`, `mcp`,
  `orchestrator`, `observability`, `notifications`, `approval_gate`,
  `eval_harness` are independent feature modules. The MCP server composes
  them; no feature imports from another.
- **Shared packages are pure libraries.** `packages/sdlc-*` are Python
  packages with their own `pyproject.toml`, installable via `pixi`. They
  contain Pydantic models, SQLite schema, phase graph validation, judge
  evaluation, debate consensus, and the legacy MCP server wrapper.

## Storage

- **SQLite (WAL mode)** is the source of truth. Located at
  `data/sdlc.db` by default; configurable via `SDLC_DB_PATH` env var.
- **WriteQueue** serializes all writes through a single async worker to
  prevent SQLite contention. Reads bypass the queue.
- **Checkpoints** are JSON files in `data/checkpoints/<task_id>.json`,
  written after every successful phase transition.
- **Traces** are JSONL files in `data/traces/`, keyed by `trace_id`,
  with retention policy (errors forever, successful 7d, raw spans 30d,
  compacted summaries permanent).

## Configuration

- `config/llm_config.yaml` — provider/model configuration
- `config/model_routing.yaml` — per-phase model routing
- `config/sandbox.yaml` — tool sandbox policy
- `config/phase_graph.yaml` — phase graph for the feature workflow
- `config/prompt_contracts.yaml` — prompt schema contracts
- `src/foundry/graphs/*.yaml` — phase graph templates (feature, bugfix,
  refactor, research, docs)

## Phase Graphs

Five workflows, defined in `src/foundry/graphs/`:

| Workflow | Path |
|---|---|
| `feature` | Chatting → Specs → Planning → Coding → Review → Testing → Done |
| `bugfix` | Chatting → Specs → Coding → Review → Testing → Done |
| `refactor` | Chatting → Planning → Coding → Review → Testing → Done |
| `research` | Chatting → Specs → Planning → Review → Done |
| `docs` | Chatting → Specs → Coding → Review → Done |

## OpenCode Integration

- `.opencode/skills/foundry/SKILL.md` — primary agent prompt
- `.opencode/skills/foundry/prompts/*.md` — 7 phase prompts
- `.opencode/context/{project,sdlc}/` — 8 LLM-stable context files
- `.opencode/graphs/sdlc-phases.yaml` — phase graph for the enforcer plugin
- `.opencode/plugins/sdlc-enforcer.ts` — TypeScript plugin that gates
  OpenCode tool calls (blocks file edits outside Coding/Testing, blocks
  edits during approval gates, anchored state compaction, session
  persistence)

## Tool Surface

29 MCP tools exposed by `src/foundry/features/mcp/server.py`, grouped:

- **Task lifecycle** (6): `sdlc_create_task`, `sdlc_get_next_action`,
  `sdlc_get_status`, `sdlc_list_tasks`, `sdlc_cancel_task`, `sdlc_resume_task`
- **Phase validation** (3): `sdlc_submit_output`, `sdlc_request_approval`,
  `sdlc_schema_check`
- **Tracing** (4): `sdlc_get_trace`, `sdlc_list_traces`,
  `sdlc_get_summaries`, `sdlc_enforce_retention`
- **Repository indexing** (9): `sdlc_index_repository`, `sdlc_index_files`,
  `sdlc_get_dependency_context`, `sdlc_get_index_stats`,
  `sdlc_query_symbols`, `sdlc_get_callers`, `sdlc_get_symbol_context`,
  `sdlc_harvest_context`, `sdlc_check_spec_drift`
- **Debate** (2): `sdlc_debate_get_turn`, `sdlc_debate_submit_turn`
- **Agent loop** (2): `sdlc_agent_get_turn`, `sdlc_agent_submit_turn`
- **Memory** (3): `sdlc_memory_store`, `sdlc_memory_query`, `sdlc_memory_stats`

Plus 1 resource: `sdlc://phase-graph`.

## Install & Run

```bash
git clone https://github.com/Hemanthdamineni/foundry.git
cd foundry
pixi install                          # creates the pixi env, installs all 6 packages + foundry
pixi run foundry init                 # bootstrap a workspace
pixi run foundry mcp                  # start the MCP server (stdio)
# or:
pixi run foundry serve                # start the FastAPI HTTP server
```

For OpenCode integration, point `opencode.json` at this checkout
(it already does) and run OpenCode from the project root.
