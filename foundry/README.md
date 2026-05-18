# Foundry

A workspace-aware autonomous SDLC agent runtime for OpenCode.

Foundry follows the same harness-native packaging idea used by Impeccable:
OpenCode reads the `.opencode/` bundle directly, while the npm package can also
ship helper commands and install hooks.

## Install

```bash
npx skills add hemanthdamineni/foundry -a opencode -g
```

For local testing before publishing:

```bash
npx skills add ./foundry -a opencode -g --copy -y
```

The skills CLI installs the Foundry skill into OpenCode. To also install the
runtime, agent definitions, and MCP registration from this npm package:

```bash
npx @hemanthdamineni/foundry
```

The installer sets up the Python runtime with `uv tool install sdlc-mcp`, falling
back to `pipx install sdlc-mcp`, installs OpenCode agents under
`~/.config/opencode/agents`, and registers the local MCP server under
`~/.config/opencode/opencode.json`.

## Use

Open any project folder in OpenCode, select `foundry`, and describe the task.
Foundry detects workspace state, creates or repairs `.sdlc`, installs local
OpenCode integration, creates the task, and starts the SDLC lifecycle.

No manual `init` command is required.

Foundry uses the folder where OpenCode launches the MCP process as the
authoritative workspace root. It does not walk upward to find `.git`,
`opencode.json`, package manifests, or monorepo roots. To intentionally use a
different workspace, launch the runtime with `--workspace <path>` or set
`FOUNDRY_WORKSPACE`.

Foundry does not set a model on its agents by default. OpenCode uses the model
you selected in the OpenCode UI or configured in `opencode.json`. Python-side
LLM providers stay disabled unless you explicitly enable them in
`.sdlc/config/llm_config.yaml`.
