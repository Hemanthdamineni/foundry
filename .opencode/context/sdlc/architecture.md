# SDLC Architecture

## Layers

1. **Python Runtime** — MCP server providing SDLC tools
2. **OpenCode Integration** — auto-generated .opencode/ config
3. **Installer / Bootstrap** — sdlc-mcp CLI

## Key Components

- `ConsensusEngine` — pure logic for verdict aggregation
- `JudgeEngine` — LLM-based phase evaluation
- `DebateRuntime` — multi-agent debate orchestration
- `Acervo` — tag-based memory store
- `Engram` — structured memory entries
- `ModelRouter` — per-role LLM provider routing
