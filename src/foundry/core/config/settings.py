"""Unified Foundry configuration — YAML-first with env-var fallback.

Combines field sets from:
- :mod:`foundry.features.sdlc_runtime.config`  (SDLC runtime settings)
- :mod:`foundry.features.api_server.config`      (AI-Agent server settings)
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Package root ─────────────────────────────────────────────────────────────
# Two directories up from this file (src/foundry/core/config/settings.py)
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# YAML helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its contents as a dict."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        msg = f"Expected YAML mapping at {path}, got {type(data).__name__}"
        raise TypeError(msg)
    return cast("dict[str, Any]", data)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Recursively merge *overlay* into *base* (mutates *base* in place).

    When both ``base[key]`` and ``overlay[key]`` are dicts the merge is
    recursive; otherwise *overlay* wins (simple replacement).
    """
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _collect_yaml_configs(config_dir: Path) -> dict[str, Any]:
    """Load and merge every ``.yaml`` / ``.yml`` file in *config_dir*."""
    merged: dict[str, Any] = {}
    if not config_dir.is_dir():
        return merged
    for path in sorted(config_dir.glob("*.yaml")) + sorted(config_dir.glob("*.yml")):
        data = _load_yaml_dict(path)
        _deep_merge(merged, data)
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class BackendProtocol(StrEnum):
    """Supported LLM backend protocols (mirrors :class:`api_server.config.BackendProtocol`)."""

    OPENAI = "openai"
    OLLAMA = "ollama"


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-configuration models
# ═══════════════════════════════════════════════════════════════════════════════


class IndexConfigModel(BaseModel):
    """Indexing strategy for code-aware search (from SDLC runtime)."""

    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
            "*.rs", "*.go", "*.java", "*.yaml", "*.yml",
            "*.json", "*.md",
        ],
    )
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.pyc", "__pycache__/*", ".git/*", "node_modules/*",
            ".pixi/*", ".venv/*", "data/*", ".opencode/*",
        ],
    )
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20


class LoggingConfig(BaseModel):
    """Logging configuration (from SDLC runtime)."""

    level: str = "INFO"
    use_json: bool = True
    path: str = ".foundry/logs/sdlc.log"


class StoreConfig(BaseModel):
    """SQLite / persistence store configuration (from SDLC runtime)."""

    db_path: str = ".foundry/sdlc.db"
    wal_mode: bool = True
    busy_timeout_ms: int = 5000
    checkpoint_interval: int = 100


class SandboxConfig(BaseModel):
    """Sandbox / container isolation configuration (from SDLC runtime)."""

    enabled: bool = False
    network_isolation: str = "localhost"
    readonly_paths: list[str] = Field(
        default_factory=lambda: ["/usr", "/etc", "/nix/store"],
    )
    writable_paths: list[str] = Field(
        default_factory=lambda: ["/workspace/src", "/workspace/tests"],
    )
    denied_paths: list[str] = Field(default_factory=list)


class LLMProviderConfig(BaseModel):
    """A single LLM provider entry (from SDLC runtime)."""

    type: str = "ollama"
    api_key: str = ""
    base_url: str = "http://localhost:11434"
    default_model: str = "qwen3:8b"
    timeout_s: int = 120


class LLMRoutingConfig(BaseModel):
    """Model routing for agent roles (from SDLC runtime)."""

    judge_provider: str = "default"
    judge_model: str = ""
    debate_agent_provider: str = "default"
    debate_agent_model: str = ""
    debate_consensus_provider: str = "default"
    debate_consensus_model: str = ""


class LLMConfig(BaseModel):
    """Top-level LLM orchestration configuration (from SDLC runtime)."""

    default_provider: str = "ollama"
    default_model: str = "qwen3:8b"
    providers: dict[str, LLMProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": LLMProviderConfig(type="ollama", default_model="qwen3:8b"),
        },
    )
    routing: LLMRoutingConfig = Field(default_factory=LLMRoutingConfig)


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Settings
# ═══════════════════════════════════════════════════════════════════════════════


class Settings(BaseSettings):
    """Unified Foundry configuration.

    Resolution order (highest priority first):

    1.  YAML files in ``config_dir/*.{yaml,yml}``
    2.  Environment variables (``AI_AGENT_*``, ``SDLC_*``, ``FOUNDRY_*`` prefixes)
    3.  Field-level pydantic defaults

    Construct via :meth:`from_yaml_first` to get YAML-first behaviour, or use
    the standard ``Settings()`` constructor for env-var-only resolution.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    # ╭────────────────────────────────────────────────────────────────────────╮
    # │  SDLC Runtime fields                                                   │
    # ╰────────────────────────────────────────────────────────────────────────╯

    debug: bool = Field(
        False,
        validation_alias=AliasChoices("SDLC_DEBUG", "AI_AGENT_DEBUG", "FOUNDRY_DEBUG"),
    )
    config_dir: str = Field(
        "configs",
        validation_alias=AliasChoices("SDLC_CONFIG_DIR", "AI_AGENT_CONFIG_DIR", "FOUNDRY_CONFIG_DIR"),
    )
    db_path: str = Field(
        ".foundry/sdlc.db",
        validation_alias=AliasChoices("SDLC_DB_PATH", "FOUNDRY_DB_PATH"),
    )
    plugin_state_dir: str = Field(
        ".foundry/plugin_state",
        validation_alias=AliasChoices("SDLC_PLUGIN_STATE_DIR", "FOUNDRY_PLUGIN_STATE_DIR"),
    )
    checkpoint_dir: str = Field(
        ".foundry/checkpoints",
        validation_alias=AliasChoices("SDLC_CHECKPOINT_DIR", "FOUNDRY_CHECKPOINT_DIR"),
    )
    log_path: str = Field(
        ".foundry/logs/sdlc.log",
        validation_alias=AliasChoices("SDLC_LOG_PATH", "FOUNDRY_LOG_PATH"),
    )
    trace_dir: str = Field(
        ".foundry/traces",
        validation_alias=AliasChoices("SDLC_TRACE_DIR", "FOUNDRY_TRACE_DIR"),
    )
    max_iterations: int = Field(
        8,
        validation_alias=AliasChoices("SDLC_MAX_ITERATIONS", "FOUNDRY_MAX_ITERATIONS"),
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    logging_cfg: LoggingConfig = Field(
        default_factory=LoggingConfig,
        alias="logging",
        validation_alias=AliasChoices("SDLC_LOGGING__LEVEL", "FOUNDRY_LOGGING__LEVEL"),
    )
    memory_enabled: bool = Field(
        True,
        validation_alias=AliasChoices("SDLC_MEMORY_ENABLED", "FOUNDRY_MEMORY_ENABLED"),
    )
    workspace_path: str = Field(
        ".",
        validation_alias=AliasChoices(
            "SDLC_WORKSPACE_PATH", "FOUNDRY_WORKSPACE_PATH"
        ),
    )
    memory_dir: str = Field(
        ".foundry/memory",
        validation_alias=AliasChoices("SDLC_MEMORY_DIR", "FOUNDRY_MEMORY_DIR"),
    )
    index_dir: str = Field(
        ".foundry/index",
        validation_alias=AliasChoices("SDLC_INDEX_DIR", "FOUNDRY_INDEX_DIR"),
    )
    index: IndexConfigModel = Field(default_factory=IndexConfigModel)

    # ╭────────────────────────────────────────────────────────────────────────╮
    # │  API Server fields                                                     │
    # ╰────────────────────────────────────────────────────────────────────────╯

    server_host: str = Field(
        "0.0.0.0",
        validation_alias=AliasChoices("AI_AGENT_SERVER_HOST", "FOUNDRY_SERVER_HOST", "SERVER_HOST"),
    )
    server_port: int = Field(
        8000,
        validation_alias=AliasChoices("AI_AGENT_SERVER_PORT", "FOUNDRY_SERVER_PORT", "SERVER_PORT"),
    )
    backend_protocol: BackendProtocol = Field(
        BackendProtocol.OLLAMA,
        validation_alias=AliasChoices("AI_AGENT_BACKEND_PROTOCOL", "FOUNDRY_BACKEND_PROTOCOL"),
    )
    backend_base_url: str = Field(
        "http://127.0.0.1:11434",
        validation_alias=AliasChoices("AI_AGENT_BACKEND_BASE_URL", "FOUNDRY_BACKEND_BASE_URL"),
    )
    backend_api_key: str | None = Field(
        None,
        validation_alias=AliasChoices("AI_AGENT_BACKEND_API_KEY", "FOUNDRY_BACKEND_API_KEY"),
    )
    default_model: str = Field(
        "ai-agent-v4",
        validation_alias=AliasChoices("AI_AGENT_DEFAULT_MODEL", "FOUNDRY_DEFAULT_MODEL"),
    )
    model_aliases: tuple[str, ...] = Field(
        ("ai-agent-v4", "hybrid-orchestrator-agentic"),
        validation_alias=AliasChoices("AI_AGENT_MODEL_ALIASES", "FOUNDRY_MODEL_ALIASES"),
    )
    public_models: tuple[str, ...] = Field(
        (),
        validation_alias=AliasChoices("AI_AGENT_PUBLIC_MODELS", "FOUNDRY_PUBLIC_MODELS"),
    )
    openai_chat_endpoint: str = "chat/completions"
    openai_models_endpoint: str = "models"
    ollama_chat_endpoint: str = "api/chat"
    max_connections: int = 200
    max_keepalive_connections: int = 50
    connect_timeout_seconds: float = 10.0
    write_timeout_seconds: float = 60.0
    pool_timeout_seconds: float = 30.0
    log_requests: bool = True
    db_url: str = Field(
        "sqlite:///./ai_agent_server_v3.db",
        validation_alias=AliasChoices("AI_AGENT_DB_URL", "FOUNDRY_DB_URL"),
    )
    task_api_enabled: bool = True
    chat_auto_orchestrate: bool = Field(
        True,
        validation_alias=AliasChoices("AI_AGENT_CHAT_AUTO_ORCHESTRATE", "FOUNDRY_CHAT_AUTO_ORCHESTRATE"),
    )
    chat_auto_orchestrate_stream: bool = Field(
        True,
        validation_alias=AliasChoices("AI_AGENT_CHAT_AUTO_ORCHESTRATE_STREAM", "FOUNDRY_CHAT_AUTO_ORCHESTRATE_STREAM"),
    )
    chat_auto_orchestrate_models: tuple[str, ...] = Field(
        (),
        validation_alias=AliasChoices("AI_AGENT_CHAT_AUTO_ORCHESTRATE_MODELS", "FOUNDRY_CHAT_AUTO_ORCHESTRATE_MODELS"),
    )
    embedded_bridge_enabled: bool = True
    embedded_bridge_worker_id: str = "embedded-bridge-1"
    embedded_bridge_poll_interval_seconds: float = 1.0
    bridge_claim_wait_seconds: float = 15.0
    bridge_heartbeat_interval_seconds: float = 15.0
    continue_command: str = "cn"
    chat_task_timeout_seconds: int = 90
    bridge_shared_key: str | None = None
    bridge_lease_seconds: int = 90
    bridge_heartbeat_timeout_seconds: int = 180
    tool_retry_max: int = 3
    tool_retry_backoff_base_seconds: int = 2
    tool_retry_backoff_max_seconds: int = 20
    resume_inflight_work_on_startup: bool = False
    max_warm_models: int = 3
    idle_warmup_seconds: int = 90
    idle_monitor_seconds: int = 10
    nightly_cron: str = Field(
        "0 3 * * *",
        validation_alias=AliasChoices("AI_AGENT_NIGHTLY_CRON", "FOUNDRY_NIGHTLY_CRON"),
    )
    model_routing_path: str = "model_routing.yaml"
    phase_graph_path: str = "phase_graph.yaml"
    prompt_contracts_path: str = "prompt_contracts.yaml"
    debate_config_path: str = "debate_config.yaml"
    structured_log_path: str = "logs/server.log"
    metrics_log_path: str = "logs/metrics.log"

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("config_dir")
    @classmethod
    def _resolve_config_dir(cls, v: str) -> str:
        return str(Path(v).expanduser())

    # ── Construction helpers ────────────────────────────────────────────────

    @classmethod
    def from_yaml_first(cls, config_dir: str | Path | None = None) -> Settings:
        """Build a ``Settings`` instance with YAML-first resolution.

        1. Start with environment-variable overrides on top of defaults.
        2. Load and merge all ``.yaml`` / ``.yml`` files from *config_dir*.
        3. YAML values take highest priority.

        Parameters
        ----------
        config_dir:
            Directory to scan for YAML files.  If *None* the value of the
            ``FOUNDRY_CONFIG_DIR`` or ``SDLC_CONFIG_DIR`` env var is used;
            falling back to the first existing directory among ``./config``,
            ``./configs`` (relative to *cwd*) and ``<PACKAGE_ROOT>/config``.
        """
        if config_dir is None:
            env_config_dir = (
                os.getenv("FOUNDRY_CONFIG_DIR")
                or os.getenv("SDLC_CONFIG_DIR")
            )
            if env_config_dir:
                config_dir = Path(env_config_dir).expanduser()
            else:
                candidates = [
                    Path("config"),
                    Path("configs"),
                    PACKAGE_ROOT / "config",
                    PACKAGE_ROOT / "configs",
                ]
                config_dir = next(
                    (c for c in candidates if c.is_dir()), candidates[0]
                )
        else:
            config_dir = Path(config_dir).expanduser()

        # 1.  Resolve environment variables + defaults.
        instance = cls()

        # 2.  Overlay YAML values on top (YAML wins).
        yaml_data = _collect_yaml_configs(config_dir)
        if yaml_data:
            current = instance.model_dump(mode="python")
            _deep_merge(current, yaml_data)
            # model_validate does NOT re-read env vars — only __init__ does.
            instance = cls.model_validate(current)

        return instance

    # ── Path resolution ─────────────────────────────────────────────────────

    def resolve_runtime_path(self, path: str | Path) -> Path:
        """Resolve a possibly-relative path against the package root.

        Absolute paths are returned as-is; relative paths are anchored to
        :data:`PACKAGE_ROOT`.
        """
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return PACKAGE_ROOT / candidate

    def resolve_config_path(self, filename: str) -> Path:
        """Locate a configuration file by name.

        Searches, in order:

        1. ``<config_dir>/<filename>``
        2. ``<PACKAGE_ROOT>/config/<filename>``
        3. ``<PACKAGE_ROOT>/configs/<filename>``

        Returns the first match or the first candidate if none exist.
        """
        cfg_dir = self.resolve_runtime_path(self.config_dir)
        candidates = [
            cfg_dir / filename,
            PACKAGE_ROOT / "config" / filename,
            PACKAGE_ROOT / "configs" / filename,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def resolve_phase_graph_path(self, name: str = "feature") -> Path:
        """Return the path to a phase-graph YAML file."""
        candidates = [
            PACKAGE_ROOT / "graphs" / f"{name}.yaml",
            self.resolve_config_path("graphs") / f"{name}.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    # ── Config-file loaders ─────────────────────────────────────────────────

    def load_phase_graph(self, name: str = "feature") -> dict[str, Any]:
        """Load a phase-graph YAML definition."""
        path = self.resolve_phase_graph_path(name)
        if not path.exists():
            msg = f"Phase graph not found: {name}"
            raise FileNotFoundError(msg)
        return _load_yaml_dict(path)

    def load_model_routing(self) -> dict[str, Any]:
        """Load the model-routing configuration."""
        path = self.resolve_config_path("model_routing.yaml")
        if not path.exists():
            msg = "model_routing.yaml not found"
            raise FileNotFoundError(msg)
        return _load_yaml_dict(path)

    def load_budget_policy(self) -> dict[str, Any]:
        """Load the budget policy, or return an empty dict if absent."""
        path = self.resolve_config_path("budget_policy.yaml")
        if path.exists():
            return _load_yaml_dict(path)
        return {}

    def load_judge_prompt(self, name: str) -> str | None:
        """Load a judge-prompt template by stem name (e.g. ``"judge_specs_to_planning"``).

        Returns *None* if not found.
        """
        prompts_dir = self.resolve_config_path("prompts")
        candidates = [
            prompts_dir / f"{name}.txt",
            Path(self.config_dir) / "prompts" / f"{name}.txt",
            PACKAGE_ROOT / "config" / "prompts" / f"{name}.txt",
            PACKAGE_ROOT / "configs" / "prompts" / f"{name}.txt",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        return None

    def load_all_judge_prompts(self) -> dict[str, str]:
        """Load every ``.txt`` prompt file from the prompts directory."""
        prompts_dir = self.resolve_config_path("prompts")
        if not prompts_dir.exists():
            prompts_dir = PACKAGE_ROOT / "configs" / "prompts"
        result: dict[str, str] = {}
        if not prompts_dir.exists():
            return result
        for entry in sorted(prompts_dir.iterdir()):
            if entry.suffix == ".txt":
                result[entry.stem] = entry.read_text(encoding="utf-8")
        return result

    def load_llm_config(self) -> LLMConfig:
        """Load LLM config from YAML, falling back to the runtime defaults."""
        path = self.resolve_config_path("llm_config.yaml")
        if path.exists():
            data = _load_yaml_dict(path)
            return LLMConfig(**data)
        return self.llm

    # ── Directory lifecycle ─────────────────────────────────────────────────

    def resolve_workspace_path(self) -> Path:
        """Resolve the user-facing workspace directory.

        Relative ``workspace_path`` values are anchored to the *current
        working directory* (the project the server operates on), unlike
        :meth:`resolve_runtime_path` which anchors to the package root.
        """
        candidate = Path(self.workspace_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (Path.cwd() / candidate).resolve()

    def ensure_dirs(self) -> None:
        """Create every directory referenced by path-configuration fields."""
        paths = [
            self.resolve_runtime_path(self.db_path),
            self.resolve_runtime_path(self.plugin_state_dir),
            self.resolve_runtime_path(self.checkpoint_dir),
            self.resolve_runtime_path(self.log_path),
            self.resolve_runtime_path(self.trace_dir),
            self.resolve_runtime_path(self.index_dir),
            self.resolve_runtime_path(self.structured_log_path),
            self.resolve_runtime_path(self.metrics_log_path),
        ]
        for d in paths:
            p = Path(d)
            if p.suffix:
                p = p.parent
            p.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level convenience instance
# ═══════════════════════════════════════════════════════════════════════════════

settings = Settings.from_yaml_first()


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone helper (ported from api_server.config)
# ═══════════════════════════════════════════════════════════════════════════════


def resolve_backend_model(settings: Settings, requested_model: str | None) -> str:
    """Resolve a requested model name against the configured model aliases.

    If *requested_model* is *None*, empty, or one of the configured
    :attr:`Settings.model_aliases`, the :attr:`Settings.default_model` is
    returned.  Otherwise the requested name passes through unchanged.
    """
    if requested_model is None:
        return settings.default_model
    normalized = requested_model.strip()
    if not normalized:
        return settings.default_model
    if normalized in settings.model_aliases:
        return settings.default_model
    return normalized
