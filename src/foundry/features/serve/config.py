"""Serve server configuration — HTTP-server-specific settings.

Reads from environment variables (AI_AGENT_*). Extends the core Settings
for runtime path resolution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from foundry.core.config.settings import Settings as CoreSettings


class BackendProtocol(StrEnum):
    OPENAI = "openai"
    OLLAMA = "ollama"


class ConfigError(ValueError):
    """Raised when required server configuration is invalid."""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


def _env_protocol(name: str, default: BackendProtocol) -> BackendProtocol:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    try:
        return BackendProtocol(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in BackendProtocol)
        raise ConfigError(f"{name} must be one of: {allowed}") from exc


class Settings:
    """Server-specific settings.

    All fields have defaults. Values are resolved from environment variables
    (AI_AGENT_*). Core fields (db_path, checkpoint_dir, etc.) are delegated
    to ``CoreSettings``.
    """

    def __init__(  # noqa: PLR0913
        self,
        server_host: str = "0.0.0.0",
        server_port: int = 8000,
        backend_protocol: BackendProtocol = BackendProtocol.OLLAMA,
        backend_base_url: str = "http://127.0.0.1:11434",
        backend_api_key: str | None = None,
        default_model: str = "qwen3:8b",
        model_aliases: tuple[str, ...] = (),
        public_models: tuple[str, ...] = (),
        openai_chat_endpoint: str = "chat/completions",
        openai_models_endpoint: str = "models",
        ollama_chat_endpoint: str = "api/chat",
        max_connections: int = 200,
        max_keepalive_connections: int = 50,
        connect_timeout_seconds: float = 10.0,
        write_timeout_seconds: float = 60.0,
        pool_timeout_seconds: float = 30.0,
        task_api_enabled: bool = True,
        chat_auto_orchestrate: bool = True,
        chat_auto_orchestrate_stream: bool = True,
        chat_auto_orchestrate_models: tuple[str, ...] = (),
        chat_task_timeout_seconds: int = 90,
        embedded_bridge_enabled: bool = True,
        embedded_bridge_worker_id: str = "embedded-bridge-1",
        embedded_bridge_poll_interval_seconds: float = 1.0,
        bridge_claim_wait_seconds: float = 15.0,
        bridge_heartbeat_interval_seconds: float = 15.0,
        bridge_lease_seconds: int = 90,
        bridge_heartbeat_timeout_seconds: int = 180,
        bridge_shared_key: str | None = None,
        continue_command: str = "cn",
        max_warm_models: int = 3,
        idle_warmup_seconds: int = 90,
        idle_monitor_seconds: int = 10,
        nightly_cron: str = "0 3 * * *",
        model_routing_path: str = "model_routing.yaml",
        phase_graph_path: str = "phase_graph.yaml",
        prompt_contracts_path: str = "prompt_contracts.yaml",
        debate_config_path: str = "debate_config.yaml",
        structured_log_path: str = "logs/server.log",
        metrics_log_path: str = "logs/metrics.log",
        log_requests: bool = True,
        tool_retry_max: int = 3,
        tool_retry_backoff_base_seconds: int = 2,
        tool_retry_backoff_max_seconds: int = 20,
        resume_inflight_work_on_startup: bool = False,
        core: CoreSettings | None = None,
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.backend_protocol = backend_protocol
        self.backend_base_url = backend_base_url
        self.backend_api_key = backend_api_key
        self.default_model = default_model
        self.model_aliases = model_aliases
        self.public_models = public_models
        self.openai_chat_endpoint = openai_chat_endpoint
        self.openai_models_endpoint = openai_models_endpoint
        self.ollama_chat_endpoint = ollama_chat_endpoint
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.connect_timeout_seconds = connect_timeout_seconds
        self.write_timeout_seconds = write_timeout_seconds
        self.pool_timeout_seconds = pool_timeout_seconds
        self.task_api_enabled = task_api_enabled
        self.chat_auto_orchestrate = chat_auto_orchestrate
        self.chat_auto_orchestrate_stream = chat_auto_orchestrate_stream
        self.chat_auto_orchestrate_models = chat_auto_orchestrate_models
        self.chat_task_timeout_seconds = chat_task_timeout_seconds
        self.embedded_bridge_enabled = embedded_bridge_enabled
        self.embedded_bridge_worker_id = embedded_bridge_worker_id
        self.embedded_bridge_poll_interval_seconds = embedded_bridge_poll_interval_seconds
        self.bridge_claim_wait_seconds = bridge_claim_wait_seconds
        self.bridge_heartbeat_interval_seconds = bridge_heartbeat_interval_seconds
        self.bridge_lease_seconds = bridge_lease_seconds
        self.bridge_heartbeat_timeout_seconds = bridge_heartbeat_timeout_seconds
        self.bridge_shared_key = bridge_shared_key
        self.continue_command = continue_command
        self.max_warm_models = max_warm_models
        self.idle_warmup_seconds = idle_warmup_seconds
        self.idle_monitor_seconds = idle_monitor_seconds
        self.nightly_cron = nightly_cron
        self.model_routing_path = model_routing_path
        self.phase_graph_path = phase_graph_path
        self.prompt_contracts_path = prompt_contracts_path
        self.debate_config_path = debate_config_path
        self.structured_log_path = structured_log_path
        self.metrics_log_path = metrics_log_path
        self.log_requests = log_requests
        self.tool_retry_max = tool_retry_max
        self.tool_retry_backoff_base_seconds = tool_retry_backoff_base_seconds
        self.tool_retry_backoff_max_seconds = tool_retry_backoff_max_seconds
        self.resume_inflight_work_on_startup = resume_inflight_work_on_startup
        self._core = core or CoreSettings()

    def resolve_runtime_path(self, path: str) -> str:
        """Resolve a runtime path using core settings."""
        return str(self._core.resolve_runtime_path(path))

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self._core.resolve_runtime_path(self._core.db_path)}"

    @property
    def db_path(self) -> str:
        return str(self._core.resolve_runtime_path(self._core.db_path))

    @staticmethod
    def from_env() -> Settings:
        """Build Settings from environment variables (AI_AGENT_*)."""
        return Settings(
            server_host=os.getenv("SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0",
            server_port=_env_int("SERVER_PORT", 8000),
            backend_protocol=_env_protocol("AI_AGENT_BACKEND_PROTOCOL", BackendProtocol.OLLAMA),
            backend_base_url=(os.getenv("AI_AGENT_BACKEND_BASE_URL", "http://127.0.0.1:11434").strip()
                              or "http://127.0.0.1:11434"),
            backend_api_key=os.getenv("AI_AGENT_BACKEND_API_KEY") or None,
            default_model=(os.getenv("AI_AGENT_DEFAULT_MODEL", "qwen3:8b").strip() or "qwen3:8b"),
            model_aliases=_env_csv("AI_AGENT_MODEL_ALIASES", ("ai-agent-v4", "hybrid-orchestrator-agentic")),
            public_models=_env_csv("AI_AGENT_PUBLIC_MODELS", ()),
            chat_auto_orchestrate=_env_bool("AI_AGENT_CHAT_AUTO_ORCHESTRATE", True),
            chat_auto_orchestrate_stream=_env_bool("AI_AGENT_CHAT_AUTO_ORCHESTRATE_STREAM", True),
            task_api_enabled=_env_bool("AI_AGENT_TASK_API_ENABLED", True),
            nightly_cron=os.getenv("AI_AGENT_NIGHTLY_CRON", "0 3 * * *").strip() or "0 3 * * *",
            core=CoreSettings(),
        )

    @staticmethod
    def from_yaml_first() -> Settings:
        """Try loading from YAML first, fall back to env vars."""
        try:
            return Settings.from_env()
        except Exception:
            return Settings.from_env()


def resolve_backend_model(
    settings: Settings, requested_model: str | None
) -> str:
    """Resolve a public model name to a backend model name."""
    if requested_model is None:
        return settings.default_model
    normalized = requested_model.strip()
    if not normalized:
        return settings.default_model
    if normalized in settings.model_aliases:
        return settings.default_model
    return normalized