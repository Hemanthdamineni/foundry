"""ModelRouter — per-role/per-phase model and provider selection."""

from __future__ import annotations

from typing import Any

from sdlc.adapters.llm.base import LLMProvider


class ModelRouter:
    """Resolves which provider + model to use for a given role or phase.

    Allows per-role overrides while falling back to defaults.
    """

    def __init__(
        self,
        default_provider: LLMProvider,
        default_model: str,
        overrides: dict[str, tuple[LLMProvider, str]] | None = None,
    ) -> None:
        self._default_provider = default_provider
        self._default_model = default_model
        self._overrides: dict[str, tuple[LLMProvider, str]] = overrides or {}

    def add_override(self, role: str, provider: LLMProvider, model: str) -> None:
        self._overrides[role] = (provider, model)

    def route(self, role: str) -> tuple[LLMProvider, str]:
        """Return (provider, model) for the given role/phase name."""
        if role in self._overrides:
            return self._overrides[role]
        return self._default_provider, self._default_model

    @classmethod
    def from_config(
        cls,
        default_provider: LLMProvider,
        default_model: str,
        routing_config: dict[str, Any] | None = None,
        provider_pool: dict[str, LLMProvider] | None = None,
    ) -> ModelRouter:
        """Build a router from a config dict.

        routing_config format:
            {"judge": {"provider": "openai", "model": "gpt-4o"},
             "debate_agent": {"provider": "ollama", "model": "qwen3:8b"}}
        """
        router = cls(default_provider=default_provider, default_model=default_model)
        if not routing_config or not provider_pool:
            return router

        for role, cfg in routing_config.items():
            if isinstance(cfg, dict):
                prov_name = cfg.get("provider", "")
                model = cfg.get("model", default_model)
                provider = provider_pool.get(prov_name)
                if provider is not None:
                    router.add_override(role, provider, model)
        return router
