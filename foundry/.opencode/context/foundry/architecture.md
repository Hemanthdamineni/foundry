# Foundry Architecture

Foundry is a workspace-aware autonomous SDLC agent runtime for OpenCode.

## Layers

1. Node agent package: OpenCode agents, skills, prompts, install hooks, and MCP registration.
2. Python runtime: MCP server, orchestration engine, state machine, validators, tracing, persistence, recovery, and bootstrap.
3. Workspace state: `.sdlc/` database, traces, checkpoints, logs, config, graph indexes, and generated `.opencode/` files.

## Runtime Rules

- The runtime owns bootstrap, repair, upgrades, schema migrations, and generated infrastructure.
- The primary `foundry` agent owns orchestration and delegates to hidden agents.
- Deterministic validators run before LLM judgment.
- Debate runs only after deterministic validation, context retrieval, graph context, and tracing are available.

