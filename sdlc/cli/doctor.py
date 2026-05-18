"""sdlc-mcp doctor — validate environment and configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _info(msg: str) -> None:
    print(f"  · {msg}")


def _check_file(path: Path, label: str) -> bool:
    if path.exists():
        _ok(f"{label}: {path}")
        return True
    _warn(f"{label}: {path} not found")
    return False


def _check_env_var(name: str) -> None:
    if os.environ.get(name):
        _ok(f"${name} set")
    else:
        _info(f"${name} not set (optional)")


def _check_mcp_server(root: Path) -> bool:
    opencode_json = root / "opencode.json"
    if not opencode_json.exists():
        _fail("opencode.json not found — run `sdlc-mcp init` first")
        return False

    try:
        config = json.loads(opencode_json.read_text())
        servers = config.get("mcpServers", {})
        sdlc_server = servers.get("sdlc-orchestrator")
        if sdlc_server:
            cmd = sdlc_server.get("command", "")
            _ok(f"MCP server registered: {cmd}")
            # Try to find the actual binary
            if shutil.which(cmd):
                _ok(f"MCP binary found: {cmd}")
            else:
                _warn(f"MCP binary not in PATH: {cmd}")
            return True
        _fail("No sdlc-orchestrator MCP server in opencode.json")
        return False
    except json.JSONDecodeError:
        _fail("opencode.json is not valid JSON")
        return False


def _check_sqlite(db_path: Path) -> bool:
    if not db_path.exists():
        _fail(f"Database not found: {db_path}")
        return False
    size = db_path.stat().st_size
    _ok(f"Database: {db_path} ({size} bytes)")

    import aiosqlite

    try:
        import asyncio

        async def _check() -> bool:
            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.execute("PRAGMA journal_mode;")
                row = await cursor.fetchone()
                mode = row[0] if row else "unknown"
                if mode == "wal":
                    _ok("SQLite WAL mode enabled")
                else:
                    _warn(f"SQLite journal mode: {mode} (expected wal)")

                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
                )
                tables = [r[0] for r in await cursor.fetchall()]
                expected = {"traces", "engrams", "debate_logs"}
                missing = expected - set(tables)
                if missing:
                    _warn(f"Missing tables: {missing}")
                else:
                    _ok(f"Tables: {tables}")
                return not missing

        return asyncio.run(_check())
    except Exception as exc:
        _fail(f"Database check failed: {exc}")
        return False


def _check_llm_providers(root: Path) -> bool:
    config_yaml = root / "config" / "llm_config.yaml"
    if config_yaml.exists():
        import yaml

        try:
            config = yaml.safe_load(config_yaml.read_text()) or {}
            providers = config.get("llm", {}).get("providers", {})
            if providers:
                _info(f"Configured providers: {list(providers.keys())}")
                for name, cfg in providers.items():
                    base_url = cfg.get("base_url", "")
                    api_key = cfg.get("api_key", "")
                    masked = api_key[:8] + "..." if len(api_key) > 8 else "(not set)"
                    _info(f"  {name}: {base_url} key={masked}")
            else:
                _warn("No providers configured in config/llm_config.yaml")
        except Exception as exc:
            _warn(f"Could not parse config/llm_config.yaml: {exc}")

    # Check env-based fallback
    env_providers = {"OL": False, "OP": False}
    for key in os.environ:
        if "SDLC_LLM__PROVIDERS__OLLAMA" in key:
            env_providers["OL"] = True
        if "SDLC_LLM__PROVIDERS__OPENAI" in key:
            env_providers["OP"] = True

    if env_providers["OL"]:
        _info("Ollama provider configured via env")
    if env_providers["OP"]:
        _info("OpenAI provider configured via env")

    if not providers and not any(env_providers.values()):
        _warn("No LLM providers configured — add config/llm_config.yaml or set env vars")
        return False
    return True


def _check_plugins() -> None:
    opencode_dir = Path.home() / ".opencode"
    plugins_dir = opencode_dir / "plugins"
    if plugins_dir.exists():
        plugins = list(plugins_dir.iterdir())
        if plugins:
            _info(f"Installed plugins: {len(plugins)}")
            for p in plugins:
                _info(f"  {p.name}")
        else:
            _info("No plugins installed")
    else:
        _info("No OpenCode plugins directory found")


def _check_graph_templates(root: Path) -> bool:
    graphs_dir = root / ".opencode" / "graphs"
    if not graphs_dir.exists():
        _warn("No .opencode/graphs/ directory")
        return False
    yaml_files = list(graphs_dir.glob("*.yaml")) + list(graphs_dir.glob("*.yml"))
    if yaml_files:
        _ok(f"Graph templates: {len(yaml_files)}")
        for f in yaml_files:
            _info(f"  {f.name}")
        return True
    _warn("No graph templates found in .opencode/graphs/")
    return False


def _check_prompts(root: Path) -> bool:
    prompts_dir = root / ".opencode" / "skills" / "sdlc" / "prompts"
    if not prompts_dir.exists():
        _warn("No .opencode/skills/sdlc/prompts/ directory")
        return False
    md_files = list(prompts_dir.glob("*.md"))
    if md_files:
        _ok(f"Prompt files: {len(md_files)}")
        return True
    _warn("No prompt files found")
    return False


def run_doctor() -> int:
    root = Path.cwd()
    print("╭─────────────────────────────────────╮")
    print("│  SDLC-MCP — Doctor                  │")
    print("╰─────────────────────────────────────╯")

    issues = 0

    # Python
    if sys.version_info < (3, 12):
        _fail(f"Python >= 3.12 required (have {sys.version_info.major}.{sys.version_info.minor})")
        issues += 1
    else:
        _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # Project structure
    print("\nProject structure:")
    for p in [
        root / ".opencode" / "skills" / "sdlc",
        root / ".opencode" / "skills" / "sdlc" / "prompts",
        root / "config",
        root / "data",
    ]:
        _check_file(p, p.name if p.parent == root else str(p.relative_to(root)))

    # opencode.json
    if _check_file(root / "opencode.json", "opencode.json"):
        try:
            config = json.loads((root / "opencode.json").read_text())
            agents = config.get("agents", {})
            if "dev-sdlc" in agents:
                _ok("Primary agent dev-sdlc registered")
            else:
                _warn("Primary agent dev-sdlc not found in opencode.json")
        except json.JSONDecodeError:
            _fail("opencode.json is not valid JSON")

    # MCP server
    print("\nMCP server:")
    _check_mcp_server(root)

    # Database
    print("\nDatabase:")
    _check_sqlite(root / "data" / "sdlc.db")

    # LLM providers
    print("\nLLM providers:")
    _check_llm_providers(root)

    # Plugins
    print("\nOpenCode plugins:")
    _check_plugins()

    # Graphs & prompts
    print("\nTemplates:")
    _check_graph_templates(root)
    _check_prompts(root)

    # Tools
    print("\nTools:")
    for cmd in ("opencode", "node", "ollama", "ocx"):
        if shutil.which(cmd):
            _ok(f"{cmd} available")
        else:
            _warn(f"{cmd} not found (optional)")

    print(f"\n{'All checks passed!' if issues == 0 else f'{issues} issue(s) found'}")
    return 0 if issues == 0 else 1
