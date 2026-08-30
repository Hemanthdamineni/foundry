"""foundry doctor — validate environment, configuration, and database."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from foundry.core.store.ensure_initialized import StoreBackend, db_exists


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _info(msg: str) -> None:
    print(f"  [..] {msg}")


def _check_python() -> bool:
    if sys.version_info < (3, 12):
        _fail(f"Python >= 3.12 required (have {sys.version_info.major}.{sys.version_info.minor})")
        return False
    _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def _check_env_var(name: str) -> None:
    if os.environ.get(name):
        _ok(f"${name} set")
    else:
        _info(f"${name} not set (optional)")


def _check_opencode_json(root: Path) -> bool:
    target = root / "opencode.json"
    if not target.exists():
        _warn("opencode.json not found — run `foundry init` first")
        return False
    try:
        config = json.loads(target.read_text())
        agents = config.get("agents", {})
        if "foundry" in agents:
            _ok("Primary agent foundry registered in opencode.json")
        else:
            _info("No 'foundry' agent in opencode.json (add via `foundry init`)")
        return True
    except json.JSONDecodeError:
        _fail("opencode.json is not valid JSON")
        return False


def _check_mcp_server(root: Path) -> bool:
    opencode_json = root / "opencode.json"
    if not opencode_json.exists():
        return False
    try:
        config = json.loads(opencode_json.read_text())
        servers = config.get("mcpServers", {})
        foundry_server = servers.get("foundry-server")
        if foundry_server:
            cmd = foundry_server.get("command", "")
            _ok(f"MCP server registered: {cmd}")
            if shutil.which(cmd):
                _ok(f"MCP binary found in PATH: {cmd}")
            else:
                _warn(f"MCP binary not in PATH: {cmd}")
            return True
        _warn("No foundry-server MCP server in opencode.json")
        return False
    except json.JSONDecodeError:
        return False


def _check_db(db_path: Path) -> bool:
    if not db_exists(db_path):
        _fail(f"Database not found: {db_path}")
        return False
    size = db_path.stat().st_size
    _ok(f"Database: {db_path} ({size} bytes)")

    try:
        store = StoreBackend(db_path)
        store.initialize()
        cursor = store.conn.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        mode = row[0] if row else "unknown"
        if mode == "wal":
            _ok("SQLite WAL mode enabled")
        else:
            _warn(f"SQLite journal mode: {mode} (expected wal)")

        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        tables = [r[0] for r in cursor.fetchall()]
        expected = {"tasks", "phase_history", "checkpoints", "traces", "engrams", "debate_logs"}
        missing = expected - set(tables)
        if missing:
            _warn(f"Missing tables: {missing}")
        else:
            _ok(f"Tables: {tables}")
        store.close()
        return not bool(missing)
    except Exception as exc:
        _fail(f"Database check failed: {exc}")
        return False


def _check_llm_providers(root: Path) -> bool:
    config_yaml = root / "config" / "llm_config.yaml"
    if config_yaml.exists():
        try:
            import yaml

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

    env_providers = {"OL": False, "OP": False}
    for key in os.environ:
        if "FOUNDRY_LLM__PROVIDERS__OLLAMA" in key:
            env_providers["OL"] = True
        if "FOUNDRY_LLM__PROVIDERS__OPENAI" in key:
            env_providers["OP"] = True

    if not config_yaml.exists() and not any(env_providers.values()):
        _warn("No LLM providers configured — add config/llm_config.yaml or set env vars")
        return False
    return True


def _check_ollama() -> None:
    if not shutil.which("ollama"):
        _info("Ollama not found (optional)")
        return
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip() or "unknown"
        _ok(f"Ollama {version}")
    except (subprocess.TimeoutExpired, OSError):
        _warn("Ollama not responding")


def run_doctor() -> int:
    """Run all diagnostic checks. Returns 0 if all pass, 1 otherwise."""
    root = Path.cwd()
    print("Foundry Doctor")
    print("=" * 60)

    issues = 0

    # Python
    if not _check_python():
        issues += 1

    # Project structure
    print("\nProject structure:")
    for p in [
        root / "config",
        root / "data",
    ]:
        if p.exists():
            _ok(f"{p.relative_to(root)}/")
        else:
            _warn(f"{p.relative_to(root)}/ not found")

    # opencode.json
    _check_opencode_json(root)

    # MCP server
    print("\nMCP server:")
    _check_mcp_server(root)

    # Database
    print("\nDatabase:")
    db_path = root / ".foundry" / "workspace.db"
    if not _check_db(db_path):
        issues += 1

    # LLM providers
    print("\nLLM providers:")
    if not _check_llm_providers(root):
        issues += 1

    # Ollama
    print("\nDependencies:")
    _check_ollama()
    for cmd in ("opencode", "node", "git"):
        if shutil.which(cmd):
            _ok(f"{cmd} available")
        else:
            _warn(f"{cmd} not found (optional)")

    # Environment
    print("\nEnvironment:")
    for var in ("FOUNDRY_HOME", "FOUNDRY_LOG_LEVEL", "OPENAI_API_KEY"):
        _check_env_var(var)

    print()
    if issues == 0:
        _ok("All checks passed!")
        return 0
    _fail(f"{issues} issue(s) found")
    return 1


def main() -> None:
    sys.exit(run_doctor())
