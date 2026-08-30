"""Configuration models for the SDLC pipeline.

Merges from:
- Helix/foundry/sdlc/config.py  (LLMProviderConfig, LLMRoutingConfig, LLMConfig,
  StoreConfig, SandboxConfig, LoggingConfig, IndexConfigModel)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndexConfigModel(BaseModel):
    """Code index configuration."""

    enabled: bool = True
    max_files: int = 5000
    max_file_size_kb: int = 512
    include_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.py",
            "*.js",
            "*.ts",
            "*.jsx",
            "*.tsx",
            "*.rs",
            "*.go",
            "*.java",
            "*.yaml",
            "*.yml",
            "*.json",
            "*.md",
        ],
    )
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "*.pyc",
            "__pycache__/*",
            ".git/*",
            "node_modules/*",
            ".pixi/*",
            ".venv/*",
            "data/*",
            ".opencode/*",
        ],
    )
    incremental: bool = True
    chunk_size_lines: int = 50
    context_file_count: int = 10
    context_chunk_count: int = 20


class LoggingConfig(BaseModel):
    """Structured logging configuration."""

    level: str = "INFO"
    use_json: bool = True
    path: str = "data/logs/sdlc.log"


class StoreConfig(BaseModel):
    """Persistence (SQLite) configuration."""

    db_path: str = "data/sdlc.db"
    wal_mode: bool = True
    busy_timeout_ms: int = 5000
    checkpoint_interval: int = 100


class SandboxConfig(BaseModel):
    """Execution sandbox isolation configuration."""

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
    """Configuration for a single LLM provider."""

    type: str = "ollama"
    api_key: str = ""
    base_url: str = "http://localhost:11434"
    default_model: str = "qwen3:8b"
    timeout_s: int = 120


class LLMRoutingConfig(BaseModel):
    """Per-role model routing overrides."""

    judge_provider: str = "default"
    judge_model: str = ""
    debate_agent_provider: str = "default"
    debate_agent_model: str = ""
    debate_consensus_provider: str = "default"
    debate_consensus_model: str = ""


class LLMConfig(BaseModel):
    """Aggregate LLM configuration with provider map and routing."""

    default_provider: str = "ollama"
    default_model: str = "qwen3:8b"
    providers: dict[str, LLMProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": LLMProviderConfig(type="ollama", default_model="qwen3:8b"),
        },
    )
    routing: LLMRoutingConfig = Field(default_factory=LLMRoutingConfig)


class SDLCSettings(BaseSettings):
    """Top-level settings for the SDLC server.

    This is the standalone config model extracted from the Helix Settings class.
    Use it directly or subclass to add project-specific overrides.
    """

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
    llm: LLMConfig = Field(default_factory=LLMConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    memory_enabled: bool = False
    index_dir: str = "data/index"
    index: IndexConfigModel = Field(default_factory=IndexConfigModel)

    def resolve_runtime_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        base = Path(__file__).resolve().parent.parent.parent
        return base / candidate

    def ensure_dirs(self) -> None:
        paths = [
            self.resolve_runtime_path(self.db_path),
            self.resolve_runtime_path(self.plugin_state_dir),
            self.resolve_runtime_path(self.checkpoint_dir),
            self.resolve_runtime_path(self.log_path),
            self.resolve_runtime_path(self.trace_dir),
            self.resolve_runtime_path(self.index_dir),
        ]
        for d in paths:
            p = Path(d)
            if p.suffix:
                p = p.parent
            p.mkdir(parents=True, exist_ok=True)


__all__ = [
    "IndexConfigModel",
    "LoggingConfig",
    "StoreConfig",
    "SandboxConfig",
    "LLMProviderConfig",
    "LLMRoutingConfig",
    "LLMConfig",
    "SDLCSettings",
]
# Alias for backward compat
IndexConfig = IndexConfigModel
