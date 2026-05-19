# MCP Architecture

MVP MCP architecture exposes the smallest set of tools needed to operate one
deterministic feature workflow.

## Required MCP Tools

| Tool | Purpose |
|---|---|
| `sdlc_create_task` | create one feature task |
| `sdlc_get_status` | read SQLite-backed task status |
| `sdlc_get_next_action` | report current phase/action |
| `sdlc_submit_output` | run authoritative submit pipeline |
| `sdlc_list_tasks` | inspect tasks |
| `sdlc_resume_task` | explicit latest-checkpoint resume/reconciliation |

If `sdlc_resume_task` is absent in code, implementing it is an MVP wiring task.

## Non-MVP MCP Tools

Debate orchestration, memory tools, dashboard tools, replay tools, rollback
tools, distributed-worker tools, and enterprise integrations are deferred.

They must not be referenced by the MVP execution path.

## Runtime Boundary

MCP tools are request surfaces. They do not own task state. SQLite and the
submit pipeline remain authoritative.
