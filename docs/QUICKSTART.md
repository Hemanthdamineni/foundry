# Foundry Quickstart

> 5-minute install + first-task walkthrough. For the full architecture
> reference, see [ARCHITECTURE.md](./ARCHITECTURE.md). For the original
> design plan, see [design/plan-original.md](./design/plan-original.md).

## Prerequisites

- Linux or macOS
- `pixi` (install from [pixi.sh](https://pixi.sh))
- An Ollama installation (or any OpenAI-compatible endpoint)

## Install

```bash
git clone https://github.com/Hemanthdamineni/foundry.git
cd foundry
pixi install
```

This creates the pixi env, installs all 6 split `sdlc-*` packages and
the `foundry` package, and sets up the workspace. `pixi install`
takes ~2 minutes on a fresh machine.

## Bootstrap a workspace

```bash
pixi run foundry init
```

This writes `config/{llm_config,model_routing,sandbox,phase_graph,prompt_contracts}.yaml`
and creates the `.sdlc/` directory with the SQLite store.

## Start the MCP server

```bash
pixi run foundry mcp
```

This starts the FastMCP server over stdio. OpenCode (or any
MCP-compatible client) can now connect to it.

## Start the HTTP server (optional)

```bash
pixi run foundry serve --host 127.0.0.1 --port 8000
```

This starts the FastAPI server with the model gateway and the
Continue bridge.

## Run the tests

```bash
pixi run test
```

504 tests, ~7 seconds.

## Your first task

In OpenCode with the foundry MCP server running:

```
foundry: "Add a hello-world endpoint at GET /hello that returns JSON"
```

OpenCode will:
1. Call `sdlc_create_task(description="...", mode="feature")` →
   `task_id`
2. Walk the phase graph: Chatting → Specs → Planning → Coding →
   Review → Testing → Done
3. At Coding, the OpenCode plugin (`sdlc-enforcer.ts`) gates
   file edits to the Coding phase only
4. At each phase, `sdlc_submit_output(task_id, phase, output)`
   validates the output through schema check → judge →
   ToolGate (lint → types → tests → coverage → security)
5. Final output is at the Done phase with a summary

## Try other workflows

```python
# In OpenCode:
sdlc_create_task(description="Fix the auth bug", mode="bugfix")
sdlc_create_task(description="Extract the parser module", mode="refactor")
sdlc_create_task(description="Survey LLM eval frameworks", mode="research")
sdlc_create_task(description="Document the CLI", mode="docs")
```

All 5 workflows are wired and executable.

## Next steps

- Read the [architecture doc](./ARCHITECTURE.md) for the runtime layout
- Read [TODO.md](./TODO.md) for post-MVP work (memory, observability, etc.)
- Read the [kernel ADRs](https://github.com/Hemanthdamineni/Helix/tree/master/docs/adr)
  for the design rationale behind the kernel contracts

## Troubleshooting

- **`foundry: command not found`** — `pixi run foundry` instead, or
  activate the pixi env with `pixi shell`
- **`ModuleNotFoundError: No module named 'sdlc_*'`** — re-run
  `pixi install`
- **`SQLite database locked`** — only one foundry process can hold
  the write lock; kill any orphan python processes
- **MCP server won't start** — check `config/llm_config.yaml` is valid
  YAML and the `default_provider` is reachable
