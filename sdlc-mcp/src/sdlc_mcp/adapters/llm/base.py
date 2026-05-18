"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Pluggable LLM provider for judge, debate, and consensus calls.

    Implementations: OllamaProvider, OpenAIProvider, etc.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat completion request and return the response content string."""

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Return True if the provider is reachable and usable."""
