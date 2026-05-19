# Repository Structure

This guide describes the repository from an MVP implementation-readiness
perspective. It does not imply every present file is operational.

## MVP Runtime Areas

| Area | MVP role |
|---|---|
| `sdlc/server.py` / app entrypoint | exposes MCP/runtime tools |
| `sdlc/runtime/app.py` | initializes runtime context, store, queue, executor, gate |
| `sdlc/tools/phase.py` | authoritative `submit_output` path |
| `sdlc/storage/sqlite_store.py` | task state authority |
| `sdlc/runtime/write_queue.py` | ordered persistence writes |
| `sdlc/engine/checkpoint.py` | latest checkpoint write/load |
| `sdlc/adapters/tools/ruff.py` | lint gate adapter |
| `sdlc/adapters/tools/mypy.py` | type gate adapter |
| `sdlc/adapters/tools/pytest.py` | test gate adapter |
| `sdlc/runtime/tool_executor.py` | governed command execution |
| `sdlc/runtime/tool_gate.py` | deterministic gate evaluation |

## Deferred Or Scaffolded Areas

Files for enhanced checkpoints, rollback, replay, dashboards, team coordination,
advanced memory, context indexing, coverage, security, and benchmarks may exist.
They are not MVP runtime dependencies unless explicitly wired into
`submit_output` and covered by integration tests.

## Status Rule

Use runtime status language:

- `file exists`
- `scaffolded`
- `partially wired`
- `operationally integrated`
- `production-ready`
- `deferred`
- `non-operational concept`

Do not write "implemented" when the real meaning is "module exists."
