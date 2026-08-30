"""Abstract base class for LLM providers used by the JudgeEngine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Pluggable LLM provider interface for judge, debate, and consensus calls.

    Implementations: OllamaProvider, OpenAIProvider, AnthropicProvider, etc.

    Every provider must implement ``generate`` for chat completions and
    ``healthcheck`` for connectivity verification.
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
        """Send a chat completion request and return the response content string.

        Args:
            messages: Chat messages in OpenAI-compatible format
                (``[{"role": "user", "content": "..."}]``).
            model: Model identifier to use.  ``None`` means use the provider's
                default.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.
            response_format: Optional JSON schema to enforce structured output.

        Returns:
            The response content as a plain string.

        Raises:
            RuntimeError: If the underlying API call fails.
        """
        ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Return ``True`` if the provider is reachable and usable."""
        ...
