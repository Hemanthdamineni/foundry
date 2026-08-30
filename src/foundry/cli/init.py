"""foundry init — bootstrap Foundry in a project directory."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from foundry.core.store.ensure_initialized import ensure_initialized


DEFAULT_CONFIG_FILES: dict[str, str] = {
    "config/llm_config.yaml": (
        "llm:\n"
        "  default_provider: ollama\n"
        "  default_model: qwen3:8b\n"
        "  providers:\n"
        "    ollama:\n"
        "      type: ollama\n"
        "      base_url: http://localhost:11434\n"
        "      default_model: qwen3:8b\n"
        "      timeout_s: 120\n"
        "    openai:\n"
        "      type: openai\n"
        "      api_key: ${OPENAI_API_KEY}\n"
        "      base_url: https://api.openai.com/v1\n"
        "      default_model: gpt-4o\n"
        "  routing:\n"
        "    judge_provider: default\n"
        "    judge_model: ''\n"
        "    debate_agent_provider: default\n"
        "    debate_agent_model: ''\n"
        "    debate_consensus_provider: default\n"
        "    debate_consensus_model: ''\n"
    ),
    "config/model_routing.yaml": (
        "phases:\n"
        "  ContextHarvesting:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.7\n"
        "  Specs:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.3\n"
        "  Planning:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.3\n"
        "  Coding:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.2\n"
        "  Review:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.5\n"
        "  Testing:\n"
        "    model: qwen3:8b\n"
        "    temperature: 0.3\n"
    ),
    "config/sandbox.yaml": (
        "enabled: false\n"
        "network_isolation: localhost\n"
        "readonly_paths:\n"
        "  - /usr\n"
        "  - /etc\n"
        "denied_paths: []\n"
        "writable_paths: []\n"
    ),
    "config/budget_policy.yaml": (
        "max_iterations: 8\n"
        "max_debate_rounds: 3\n"
        "max_retries: 2\n"
        "max_cost: 0\n"
    ),
}

OPENCODE_FRAGMENT = {
    "agents": {
        "foundry": {
            "mode": "primary",
            "prompt": "{file:.opencode/skills/foundry/SKILL.md}",
        },
    },
    "mcpServers": {
        "foundry-server": {
            "command": "foundry",
            "args": ["mcp"],
            "enabled": True,
            "type": "local",
        },
    },
}


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _info(msg: str) -> None:
    print(f"  [..] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _info(f"Created {path}/")


def _write(path: Path, content: str, *, force: bool = False) -> None:
    if path.exists() and not force:
        _info(f"{path} exists, skipping (use --force to overwrite)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _ok(f"Wrote {path}")


def _merge_opencode_json(root: Path) -> None:
    target = root / "opencode.json"
    if target.exists():
        try:
            existing = json.loads(target.read_text())
            agents = existing.setdefault("agents", {})
            if "foundry" not in agents:
                agents["foundry"] = OPENCODE_FRAGMENT["agents"]["foundry"]
            servers = existing.setdefault("mcpServers", {})
            if "foundry-server" not in servers:
                servers["foundry-server"] = OPENCODE_FRAGMENT["mcpServers"]["foundry-server"]
            target.write_text(json.dumps(existing, indent=2) + "\n")
            _ok("Merged foundry config into opencode.json")
        except json.JSONDecodeError:
            _fail("opencode.json is not valid JSON — cannot merge")
    else:
        target.write_text(json.dumps(OPENCODE_FRAGMENT, indent=2) + "\n")
        _ok("Created opencode.json")


def _create_project_structure(root: Path, *, force: bool = False) -> None:
    print("\nCreating project structure...")
    _ensure_dir(root / "config")
    _ensure_dir(root / "data")
    _ensure_dir(root / ".opencode" / "skills" / "foundry")
    _ensure_dir(root / ".opencode" / "skills" / "foundry" / "prompts")
    _ensure_dir(root / ".opencode" / "graphs")

    for relpath, content in DEFAULT_CONFIG_FILES.items():
        _write(root / relpath, content, force=force)

    _merge_opencode_json(root)


def _create_database(root: Path, *, force: bool = False) -> None:
    db_path = root / ".foundry" / "workspace.db"
    if db_path.exists() and not force:
        _info(f"{db_path} exists, skipping (use --force to recreate)")
        return
    store = ensure_initialized(db_path)
    store.close()
    _ok(f"Database created: {db_path}")


def _check_dependencies() -> None:
    print("\nChecking dependencies...")
    for cmd in ("python3",):
        if shutil.which(cmd):
            _ok(f"{cmd} available")
        else:
            _warn(f"{cmd} not found")

    if shutil.which("ollama"):
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            version = result.stdout.strip() or "unknown"
            _ok(f"Ollama {version}")
        except (subprocess.TimeoutExpired, OSError):
            _warn("Ollama not responding")
    else:
        _info("Ollama not found (optional — install for local LLMs)")


def run_init(*, force: bool = False) -> int:
    """Bootstrap Foundry in the current project directory."""
    root = Path.cwd()
    print("Foundry Bootstrap")
    print("=" * 60)

    _check_dependencies()
    _create_project_structure(root, force=force)
    _create_database(root, force=force)

    print("\n" + "=" * 60)
    _ok("Foundry bootstrap complete!")
    _info("Run `foundry doctor` to verify the setup.")
    _info("Run `foundry serve` to start the server.")
    return 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap Foundry in a project directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    sys.exit(run_init(force=args.force))
