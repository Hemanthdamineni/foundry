"""sdlc-mcp init — bootstrap SDLC in current project."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sdlc.cli.install import DEFAULT_PLUGINS, install_plugins
from sdlc.cli.merger import merge_opencode_json
from sdlc.templates import (
    CONTEXT_SDLC_FILES,
    GRAPH_FILES,
    OPENCODE_FRAGMENT,
    PROMPT_FILES,
    SKILL_MD,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _info(msg: str) -> None:
    print(f"  · {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _check_python() -> bool:
    if sys.version_info < (3, 12):
        _fail(f"Python >= 3.12 required, have {sys.version_info.major}.{sys.version_info.minor}")
        return False
    _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def _check_has_cmd(name: str, label: str | None = None) -> bool:
    label = label or name
    if shutil.which(name):
        _ok(f"{label} available")
        return True
    _warn(f"{label} not found (optional)")
    return False


def _check_opencode() -> bool:
    opencode = shutil.which("opencode")
    if opencode:
        try:
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = result.stdout.strip() or "unknown"
            _ok(f"OpenCode ({version})")
            return True
        except (subprocess.TimeoutExpired, OSError):
            pass
    _warn("opencode CLI not found — MCP still works standalone")
    return False


def _check_ollama_model(model: str) -> bool:
    if not shutil.which("ollama"):
        return False
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=15,
        )
        return model in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return False


def _check_models() -> None:
    if not shutil.which("ollama"):
        _warn("Ollama not installed — models cannot be validated")
        return
    for model in ("qwen2.5-coder:7b", "llama3.2:3b"):
        if _check_ollama_model(model):
            _ok(f"Ollama model {model}")
        else:
            _warn(f"Ollama model {model} not pulled (run `ollama pull {model}` or `sdlc-mcp models --pull {model}`)")


def _validate_env() -> bool:
    print("\nValidating environment...")
    ok = True
    ok &= _check_python()
    _check_opencode()
    _check_has_cmd("node", "Node.js")
    _check_has_cmd("bun", "Bun (optional)")
    _check_has_cmd("ollama", "Ollama (optional)")
    _check_models()
    _check_has_cmd("ocx", "ocx plugin manager")
    return ok


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _info(f"Created {path}/")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _ok(f"Wrote {path}")


def _create_project_structure(force: bool) -> Path:
    root = Path.cwd()
    print("\nCreating project structure...")

    _ensure_dir(root / ".opencode" / "skills" / "sdlc")
    _ensure_dir(root / ".opencode" / "skills" / "sdlc" / "prompts")
    _ensure_dir(root / ".opencode" / "context" / "project")
    _ensure_dir(root / ".opencode" / "context" / "sdlc")
    _ensure_dir(root / ".opencode" / "graphs")
    _ensure_dir(root / ".opencode" / "plugins")
    _ensure_dir(root / "data")
    _ensure_dir(root / "config")

    return root


def _install_skill_md(root: Path, force: bool) -> None:
    target = root / ".opencode" / "skills" / "sdlc" / "SKILL.md"
    if target.exists() and not force:
        _info("SKILL.md exists, skipping (use --force to overwrite)")
        return
    _write(target, SKILL_MD)


def _install_prompts(root: Path, force: bool) -> None:
    prompts_dir = root / ".opencode" / "skills" / "sdlc" / "prompts"
    for filename, content in PROMPT_FILES.items():
        target = prompts_dir / filename
        if target.exists() and not force:
            continue
        _write(target, content)


def _install_context(root: Path, force: bool) -> None:
    for subdir, files in CONTEXT_SDLC_FILES.items():
        for filename, content in files.items():
            target = root / ".opencode" / "context" / subdir / filename
            if target.exists() and not force:
                continue
            _write(target, content)


def _install_graphs(root: Path, force: bool) -> None:
    for filename, content in GRAPH_FILES.items():
        target = root / ".opencode" / "graphs" / filename
        if target.exists() and not force:
            continue
        _write(target, content)


def _merge_opencode_json(root: Path) -> None:
    target = root / "opencode.json"
    if target.exists():
        _info("Merging into existing opencode.json")
    else:
        _info("Creating opencode.json")

    changed = merge_opencode_json(target, OPENCODE_FRAGMENT)

    if changed:
        _ok("opencode.json updated")
    else:
        _info("opencode.json unchanged (already up to date)")


def _create_llm_config(root: Path) -> None:
    """Create llm_config.yaml if it doesn't exist."""
    from sdlc.templates import LLM_CONFIG_YAML

    target = root / "config" / "llm_config.yaml"
    if target.exists():
        _info("config/llm_config.yaml exists, skipping")
        return
    _write(target, LLM_CONFIG_YAML)


def _create_sdlc_db(root: Path) -> None:
    """Initialize SDLC database with WAL mode."""
    db_path = root / "data" / "sdlc.db"
    if db_path.exists():
        _info("data/sdlc.db exists, skipping")
        return

    import aiosqlite

    try:
        import asyncio
        async def _init() -> None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(str(db_path)) as conn:
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS traces ("
                    "  id TEXT PRIMARY KEY,"
                    "  task_id TEXT,"
                    "  phase TEXT,"
                    "  action TEXT,"
                    "  status TEXT,"
                    "  output TEXT,"
                    "  verdict TEXT,"
                    "  trace_data TEXT,"
                    "  created_at TEXT DEFAULT (datetime('now')),"
                    "  updated_at TEXT DEFAULT (datetime('now'))"
                    ");"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_task_id ON traces(task_id);"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_phase ON traces(phase);"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status);"
                )
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS engrams ("
                    "  id TEXT PRIMARY KEY,"
                    "  content TEXT,"
                    "  tags TEXT,"
                    "  source TEXT,"
                    "  importance INTEGER DEFAULT 1,"
                    "  metadata TEXT,"
                    "  created_at TEXT DEFAULT (datetime('now'))"
                    ");"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_engrams_tags ON engrams(tags);"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_engrams_source ON engrams(source);"
                )
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS debate_logs ("
                    "  id TEXT PRIMARY KEY,"
                    "  task_id TEXT,"
                    "  round_num INTEGER,"
                    "  agent_role TEXT,"
                    "  content TEXT,"
                    "  verdict TEXT,"
                    "  created_at TEXT DEFAULT (datetime('now'))"
                    ");"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_debate_logs_task_id ON debate_logs(task_id);"
                )

        asyncio.run(_init())
        _ok(f"data/sdlc.db initialized (WAL)")
    except Exception as exc:
        _warn(f"Failed to create database: {exc}")


def run_init(*, force: bool = False, no_plugins: bool = False) -> int:
    print("╭─────────────────────────────────────╮")
    print("│  SDLC-MCP — Bootstrap               │")
    print("╰─────────────────────────────────────╯")

    # 1. Validate environment
    _validate_env()

    # 2. Create project structure
    root = _create_project_structure(force)

    # 3. Install SKILL.md
    _install_skill_md(root, force)

    # 4. Install prompt files
    _install_prompts(root, force)

    # 5. Install context files
    _install_context(root, force)

    # 6. Install graph templates
    _install_graphs(root, force)

    # 7. Merge opencode.json
    _merge_opencode_json(root)

    # 8. Create LLM config
    _create_llm_config(root)

    # 9. Initialize database
    _create_sdlc_db(root)

    # 10. Install OpenCode plugins
    if not no_plugins:
        print("\nInstalling OpenCode plugins...")
        failures = install_plugins(DEFAULT_PLUGINS)
        for plugin in DEFAULT_PLUGINS:
            if plugin in failures:
                _warn(f"Failed to install plugin: {plugin}")
            else:
                _ok(f"Plugin {plugin} installed")

    print("\n╭─────────────────────────────────────╮")
    print("│  SDLC-MCP bootstrap complete!       │")
    print("│                                     │")
    print("│  Run:  opencode                     │")
    print("│  Then: /sdlc                        │")
    print("╰─────────────────────────────────────╯")
    return 0
