"""Foundry unified configuration system.

This package provides a single ``Settings`` class that merges
:srcref:`src/foundry/features/sdlc_runtime/config.py` and
:srcref:`src/foundry/features/api_server/config.py` into one place.

Resolution order (highest priority first):
  1. YAML files in ``config_dir/*.yaml`` (or ``config_dir/*.yml``)
  2. Environment variables (``AI_AGENT_*``, ``SDLC_*``, ``FOUNDRY_*`` prefixes)
  3. Field-level pydantic defaults

Usage::

    from foundry.core.config import Settings

    # YAML-first (default: looks for configs/ directory)
    settings = Settings.from_yaml_first()

    # Env-fallback only (no YAML directory)
    settings = Settings()
"""

from .settings import (
    BackendProtocol,
    IndexConfigModel,
    LLMConfig,
    LLMProviderConfig,
    LLMRoutingConfig,
    LoggingConfig,
    SandboxConfig,
    Settings,
    StoreConfig,
    resolve_backend_model,
    settings,
)

__all__ = [
    "BackendProtocol",
    "IndexConfigModel",
    "LLMConfig",
    "LLMProviderConfig",
    "LLMRoutingConfig",
    "LoggingConfig",
    "SandboxConfig",
    "Settings",
    "StoreConfig",
    "resolve_backend_model",
    "settings",
]
