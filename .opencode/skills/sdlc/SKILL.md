---
name: sdlc
description: "SDLC — Structured Software Development Lifecycle with phase-gated reviews, multi-agent debate, and cross-task memory."
trigger: /sdlc
---

# SDLC — Structured Development Lifecycle Server

SDLC is an MCP server that enforces a phase-gated software development process.
It provides tools for creating tasks, transitioning through phases, evaluating
outputs, and maintaining cross-task context.

Run `python -m sdlc` or use `sdlc-mcp` from your PATH.

## Phases

| Phase | Purpose |
|---|---|
| Chatting | Clarify task intent and scope |
| Specs | Requirements, scope, constraints |
| Planning | Implementation plan with risks |
| Coding | Write and modify code |
| Review | Code review for issues and quality |
| Testing | Run and evaluate tests |
| Done | Summarize accomplishments |

## Tools

- `sdlc_create_task` — create a new task
- `sdlc_get_next_action` — get current phase context
- `sdlc_submit_output` — submit phase output for evaluation
- `sdlc_request_approval` — request or grant approval
- `sdlc_get_status` — current task status
- `sdlc_list_tasks` — list tasks filtered by status
- `sdlc_cancel_task` — cancel a task
- `sdlc_debate_output` — run multi-agent debate
- `sdlc_memory_store` / `sdlc_memory_query` / `sdlc_memory_stats` — cross-task memory
- `sdlc_index_repository` / `sdlc_index_files` — repository indexing
- `sdlc_get_dependency_context` — dependency graph for a file
- `sdlc_get_trace` / `sdlc_list_traces` / `sdlc_get_summaries` — trace inspection
- `sdlc_enforce_retention` — trace retention policy

## Usage

```
/sdlc
```

Then describe what you want to build.
