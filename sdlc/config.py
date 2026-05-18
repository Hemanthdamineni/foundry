"""Configuration loading and environment handling for the SDLC server."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        msg = f"Expected YAML mapping in {path}"
        raise TypeError(msg)
    return cast("dict[str, Any]", data)


class IndexConfigModel(BaseModel):
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
    level: str = "INFO"
    use_json: bool = True
    path: str = "data/logs/sdlc.log"


class StoreConfig(BaseModel):
    db_path: str = "data/sdlc.db"
    wal_mode: bool = True
    busy_timeout_ms: int = 5000
    checkpoint_interval: int = 100


class SandboxConfig(BaseModel):
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
    type: str = "ollama"
    api_key: str = ""
    base_url: str = "http://localhost:11434"
    default_model: str = "qwen3:8b"
    timeout_s: int = 120


class LLMRoutingConfig(BaseModel):
    judge_provider: str = "default"
    judge_model: str = ""
    debate_agent_provider: str = "default"
    debate_agent_model: str = ""
    debate_consensus_provider: str = "default"
    debate_consensus_model: str = ""


class LLMConfig(BaseModel):
    default_provider: str = "ollama"
    default_model: str = "qwen3:8b"
    providers: dict[str, LLMProviderConfig] = Field(default_factory=lambda: {
        "ollama": LLMProviderConfig(type="ollama", default_model="qwen3:8b"),
    })
    routing: LLMRoutingConfig = Field(default_factory=LLMRoutingConfig)


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
    llm: LLMConfig = Field(default_factory=LLMConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    memory_enabled: bool = False
    index_dir: str = "data/index"
    index: IndexConfigModel = Field(default_factory=IndexConfigModel)

    @field_validator("config_dir")
    @classmethod
    def resolve_config_dir(cls, v: str) -> str:
        return str(Path(v).expanduser())

    def resolve_runtime_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return PACKAGE_ROOT / candidate

    def resolve_config_path(self, filename: str) -> Path:
        config_dir = self.resolve_runtime_path(self.config_dir)
        candidates = [
            config_dir / filename,
            PACKAGE_ROOT / "config" / filename,
            PACKAGE_ROOT / "configs" / filename,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def phase_graph_path(self, name: str = "feature") -> Path:
        candidates = [
            PACKAGE_ROOT / "graphs" / f"{name}.yaml",
            self.resolve_config_path("graphs") / f"{name}.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def load_phase_graph(self, name: str = "feature") -> dict[str, Any]:
        path = self.phase_graph_path(name)
        if not path.exists():
            msg = f"Phase graph not found: {name}"
            raise FileNotFoundError(msg)
        return _load_yaml_dict(path)

    def load_model_routing(self) -> dict[str, Any]:
        path = self.resolve_config_path("model_routing.yaml")
        if not path.exists():
            msg = "model_routing.yaml not found"
            raise FileNotFoundError(msg)
        return _load_yaml_dict(path)

    def load_budget_policy(self) -> dict[str, Any]:
        path = self.resolve_config_path("budget_policy.yaml")
        if path.exists():
            return _load_yaml_dict(path)
        return {}

    def load_judge_prompt(self, name: str) -> str | None:
        """Load a judge prompt template by name (e.g. 'judge_specs_to_planning')."""
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
        """Load all judge prompt templates from the prompts directory."""
        prompts_dir = self.resolve_config_path("prompts")
        if not prompts_dir.exists():
            prompts_dir = PACKAGE_ROOT / "configs" / "prompts"
        result: dict[str, str] = {}
        if not prompts_dir.exists():
            return result
        for entry in sorted(prompts_dir.iterdir()):
            if entry.suffix == ".txt":
                name = entry.stem
                content = entry.read_text(encoding="utf-8")
                result[name] = content
        return result

    def load_llm_config(self) -> LLMConfig:
        """Load LLM config from YAML, falling back to env-based defaults."""
        path = self.resolve_config_path("llm_config.yaml")
        if path.exists():
            data = _load_yaml_dict(path)
            return LLMConfig(**data)
        return self.llm

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


settings = Settings()
