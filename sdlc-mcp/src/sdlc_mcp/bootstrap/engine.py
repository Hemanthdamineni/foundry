"""BootstrapEngine — idempotent workspace bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

from sdlc_mcp.bootstrap.migrations import SCHEMA_VERSION, migration_for_version
from sdlc_mcp.bootstrap.workspace import WorkspaceState, detect_workspace
from sdlc_mcp.templates import (
    GRAPH_FILES,
    LLM_CONFIG_YAML,
    OPENCODE_FRAGMENT,
    PROMPT_FILES,
    SKILL_MD,
)


class BootstrapEngine:
    """Idempotent, deterministic workspace bootstrap.

    Creates and maintains the ``.sdlc/`` directory structure.
    Safe to call multiple times — will not overwrite existing content.
    """

    REQUIRED_DIRS: tuple[str, ...] = (
        "traces",
        "checkpoints",
        "logs",
        "config",
        "index",
        "memory",
    )

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root or Path.cwd()).resolve()
        self._sdlc = self._root / ".sdlc"

    # ── public API ──────────────────────────────────────────────────────

    def ensure_workspace(self) -> bool:
        """Idempotent bootstrap. Returns True if anything was created."""
        state, _ = detect_workspace(self._root)
        if state == WorkspaceState.READY:
            return False

        changed = False

        changed |= self._ensure_directories()
        changed |= self._ensure_state_file()
        changed |= self._ensure_database()
        changed |= self._ensure_version_file()
        changed |= self._ensure_opencode_integration()

        return changed

    def ensure_database(self) -> bool:
        """Create and migrate the workspace database. Idempotent."""
        return self._ensure_database()

    def ensure_opencode_integration(self) -> bool:
        """Install .opencode/ skills, prompts, and graph config."""
        return self._ensure_opencode_integration()

    def upgrade(self) -> bool:
        """Upgrade workspace schema and config to latest version."""
        changed = self._ensure_directories()
        changed |= self._ensure_state_file()
        changed |= self._ensure_database()
        changed |= self._ensure_opencode_integration()
        changed |= self._ensure_version_file()
        return changed

    # ── internals ───────────────────────────────────────────────────────

    def _ensure_directories(self) -> bool:
        changed = False
        for name in self.REQUIRED_DIRS:
            target = self._sdlc / name
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                changed = True

        # Root .opencode/ directories
        opencode_dirs = (
            self._root / ".opencode" / "skills" / "foundry" / "prompts",
            self._root / ".opencode" / "context" / "project",
            self._root / ".opencode" / "context" / "foundry",
            self._root / ".opencode" / "graphs",
            self._root / ".opencode" / "plugins",
        )
        for target in opencode_dirs:
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                changed = True

        return changed

    def _ensure_state_file(self) -> bool:
        target = self._sdlc / "state.json"
        if target.exists():
            return False
        target.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "bootstrap_version": 1,
                    "status": "ready",
                },
                indent=2,
            )
        )
        return True

    def _ensure_database(self) -> bool:
        import sqlite3

        target = self._sdlc / "workspace.db"
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = sqlite3.connect(str(target))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            # Read current version
            cursor = conn.execute("PRAGMA user_version")
            current_version = cursor.fetchone()[0]

            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                for stmt in migration_for_version(version):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version={version}")

            conn.commit()
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def _ensure_version_file(self) -> bool:
        target = self._sdlc / ".version"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_text().strip() == str(SCHEMA_VERSION):
            return False
        target.write_text(f"{SCHEMA_VERSION}\n")
        return True

    def _ensure_opencode_integration(self) -> bool:
        from sdlc_mcp.cli.merger import merge_opencode_json

        changed = False

        # SKILL.md
        skill_target = self._root / ".opencode" / "skills" / "foundry" / "SKILL.md"
        if not skill_target.exists():
            skill_target.parent.mkdir(parents=True, exist_ok=True)
            skill_target.write_text(SKILL_MD)
            changed = True

        # Prompt files
        prompts_dir = self._root / ".opencode" / "skills" / "foundry" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in PROMPT_FILES.items():
            target = prompts_dir / filename
            if not target.exists():
                target.write_text(content)
                changed = True

        # Graph templates
        graphs_dir = self._root / ".opencode" / "graphs"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in GRAPH_FILES.items():
            target = graphs_dir / filename
            if not target.exists():
                target.write_text(content)
                changed = True

        # LLM config
        config_target = self._sdlc / "config" / "llm_config.yaml"
        config_target.parent.mkdir(parents=True, exist_ok=True)
        if not config_target.exists():
            config_target.write_text(LLM_CONFIG_YAML)
            changed = True

        # opencode.json merge
        opencode_target = self._root / "opencode.json"
        merged = merge_opencode_json(opencode_target, OPENCODE_FRAGMENT)
        changed |= merged

        return changed
