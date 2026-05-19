---
name: foundry
description: "Foundry: SDLC runtime with phase-gated development process, validation, checkpoint recovery, and SQLite persistence."
trigger: /foundry
---

# Foundry: Structured Development Lifecycle Server

Foundry is an MCP server that enforces a phase-gated software development process.
It provides tools for creating tasks, transitioning through phases, validating
outputs, and persisting state via SQLite and checkpoints.

Run `sdlc-mcp` from your PATH. With no arguments it starts the Foundry MCP
server over stdio; `sdlc-mcp bootstrap` repairs the current workspace.

By default, all phase reasoning uses the model currently selected in OpenCode.
Runtime LLM providers are disabled unless `.sdlc/config/llm_config.yaml`
explicitly enables them.

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

## Supported Workflow

Only the `feature` workflow is supported:
```
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
                   ^                        |
                   +-- Review -> Coding (loop)
```

## Tools

- `sdlc_detect_workspace`: inspect workspace SDLC readiness
- `sdlc_bootstrap_workspace`: create or repair `.sdlc/`
- `sdlc_create_task`: create a new task
- `sdlc_get_next_action`: get current phase context
- `sdlc_validate_phase`: validate phase output without mutation (dry-run)
- `sdlc_submit_output`: submit phase output through the validation pipeline
- `sdlc_resume_task`: restore task state from latest checkpoint
- `sdlc_upgrade_workspace`: upgrade schema and generated integration files
- `sdlc_request_approval`: request or grant approval
- `sdlc_get_status`: current task status
- `sdlc_list_tasks`: list tasks filtered by status
- `sdlc_cancel_task`: cancel a task
- `sdlc_debate_output`: run multi-agent debate on output
- `sdlc_memory_store` / `sdlc_memory_query` / `sdlc_memory_stats`: cross-task memory
- `sdlc_index_repository` / `sdlc_index_files`: repository indexing
- `sdlc_get_dependency_context`: dependency graph for a file
- `sdlc_get_trace` / `sdlc_list_traces` / `sdlc_get_summaries`: trace inspection
- `sdlc_enforce_retention`: trace retention policy

## Usage

```
/foundry
```

Then describe what you want to build.
