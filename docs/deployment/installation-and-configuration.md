# Installation and Configuration

> NPX installer, Python runtime setup, MCP server registration, SKILL.md linkage, environment variables, Ollama setup, and configuration reference.

---

## Installation Methods

### Method 1: NPX Install (Recommended)

```bash
npx foundry@latest
```

The `foundry/install/install.js` postinstall script handles:

1. **Detect Python runtime** — checks `sdlc-mcp` on PATH, pipx installation, or local venv
2. **Register MCP server** — adds Foundry to `~/.config/opencode/opencode.json`
3. **Link skills** — copies SKILL.md to `~/.config/opencode/skills/foundry/`
4. **Link agents** — copies agent definitions to `~/.config/opencode/agents/`
5. **Link context** — copies context files to `~/.config/opencode/context/`

### Method 2: Manual Setup

```bash
# 1. Clone repository
git clone <repository> && cd Ai-Agent-Server

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Create data directories
python -c "from sdlc.config import settings; settings.ensure_dirs()"

# 5. Start Ollama
ollama serve &
ollama pull qwen3:8b

# 6. Run MCP server
python -m sdlc.runtime.app
```

---

## Ollama Setup

### Required

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama daemon
ollama serve

# Pull default model
ollama pull qwen3:8b
```

### Verify

```bash
curl http://localhost:11434/api/tags
# Should list qwen3:8b
```

### Model Requirements

| Model | VRAM | Quality | Speed | Use Case |
|---|---|---|---|---|
| `qwen3:8b` | ~6GB | Good | Moderate | Default for all roles |
| `qwen3:4b` | ~3GB | Acceptable | Fast | Fallback model |
| `qwen3:14b` | ~10GB | Better | Slow | Complex reasoning tasks |

---

## MCP Server Registration

### OpenCode Configuration

```json
// ~/.config/opencode/opencode.json
{
  "mcpServers": {
    "sdlc-server": {
      "command": ["python", "-m", "sdlc.runtime.app"],
      "env": {
        "PYTHONPATH": "/path/to/Ai-Agent-Server/sdlc"
      }
    }
  }
}
```

### Verification

Once registered, the host agent can discover Foundry's tools:

```
Available MCP tools:
- sdlc_create_task
- sdlc_get_next_action
- sdlc_submit_output
- sdlc_get_status
- sdlc_list_tasks
...
```

---

## Configuration Reference

### Settings (`sdlc/config.py`)

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SDLC_",
        env_nested_delimiter="__",
        extra="ignore",
    )
    
    debug: bool = False
    config_dir: str = "configs"
    db_path: str = "data/sdlc.db"
    plugin_state_dir: str = "data/plugin_state"
    checkpoint_dir: str = "data/checkpoints"
    log_path: str = "data/logs/sdlc.log"
    trace_dir: str = "data/traces"
    max_iterations: int = 8
    memory_enabled: bool = False
    index_dir: str = "data/index"
```

### Environment Variable Mapping

| Setting | Env Variable | Default |
|---|---|---|
| `debug` | `SDLC_DEBUG` | `false` |
| `db_path` | `SDLC_DB_PATH` | `data/sdlc.db` |
| `checkpoint_dir` | `SDLC_CHECKPOINT_DIR` | `data/checkpoints` |
| `trace_dir` | `SDLC_TRACE_DIR` | `data/traces` |
| `log_path` | `SDLC_LOG_PATH` | `data/logs/sdlc.log` |
| `max_iterations` | `SDLC_MAX_ITERATIONS` | `8` |
| `memory_enabled` | `SDLC_MEMORY_ENABLED` | `false` |
| `index_dir` | `SDLC_INDEX_DIR` | `data/index` |
| LLM default provider | `SDLC_LLM__DEFAULT_PROVIDER` | `ollama` |
| LLM default model | `SDLC_LLM__DEFAULT_MODEL` | `qwen3:8b` |
| OpenAI API key | `SDLC_LLM__PROVIDERS__OPENAI__API_KEY` | `""` |
| Store WAL mode | `SDLC_STORE__WAL_MODE` | `true` |
| Sandbox enabled | `SDLC_SANDBOX__ENABLED` | `false` |
| Logging level | `SDLC_LOGGING__LEVEL` | `INFO` |
| Logging JSON | `SDLC_LOGGING__USE_JSON` | `true` |

### YAML Configuration Files

| File | Required | Purpose |
|---|---|---|
| `sdlc/configs/model_routing.yaml` | Yes | Per-phase model + subagent assignment |
| `sdlc/configs/llm_config.yaml` | No | Provider definitions (falls back to env defaults) |
| `sdlc/configs/budget_policy.yaml` | No | Budget profiles (falls back to code defaults) |
| `sdlc/configs/prompts/*.txt` | No | Judge prompt templates (uses defaults if missing) |
| `sdlc/graphs/*.yaml` | Yes | Phase graph definitions (6 templates: feature, bugfix, refactor, research, docs, feature_harvesting) |

---

## Data Directory

Created automatically by `settings.ensure_dirs()`:

```
data/
├── sdlc.db              # SQLite database
├── checkpoints/         # Checkpoint JSON files
├── traces/              # JSONL trace files
├── logs/                # Rotating log files
├── index/               # Dependency graph + SHA cache
├── memory/              # Engram storage
└── plugin_state/        # Adapter state (reserved)
```

All paths are relative to `PACKAGE_ROOT` (the `sdlc/` directory) unless absolute paths are configured.

---

## Docker (Planned)

```dockerfile
# Conceptual — not yet implemented
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
RUN ollama pull qwen3:8b
EXPOSE 11434
CMD ["python", "-m", "sdlc.runtime.app"]
```

**Status:** Not implemented. Foundry is local-first; Docker is planned for reproducible development environments and CI integration.

---

## Production Deployment (Conceptual)

For shared/team use, production deployment would require:

1. **Authentication** — MCP transport doesn't support auth; needs a gateway
2. **Sandbox enforcement** — Enable `SandboxConfig` with strict paths
3. **Judge fail-closed** — Change default from fail-open to fail-closed
4. **Database backup** — Automated SQLite backup schedule
5. **Log rotation** — Already configured (10MB × 5 backups)
6. **Monitoring** — Export metrics to Prometheus/Grafana

**Status:** All conceptual. Not a near-term priority.

---

## CLI Tools

The `sdlc/cli/` directory contains command-line utilities for development and debugging:

### Available Commands

| Command | Module | Purpose |
|---|---|---|
| `python -m sdlc.runtime.app` | `runtime/app.py` | Start MCP server (primary entry point) |
| `python -m sdlc.cli.validate` | `cli/validate.py` | Run validation checks on configs/graphs |
| `python -m sdlc.cli.index` | `cli/index.py` | Index workspace from CLI |
| `python -m sdlc.cli.inspect_task` | `cli/inspect_task.py` | Inspect task state from SQLite |

### When to Use CLI vs MCP

| Scenario | Use |
|---|---|
| Normal operation | MCP server (host agent calls tools) |
| Debugging a stuck task | CLI `inspect_task` |
| Validating config changes | CLI `validate` |
| Pre-indexing a large workspace | CLI `index` |
