"""Fake LLM provider for testing — returns canned responses."""

from __future__ import annotations

from typing import Any

from sdlc_mcp.adapters.llm.base import LLMProvider


class FakeProvider(LLMProvider):
    """Returns pre-configured responses. Never makes real HTTP calls."""

    def __init__(self, response: str = "PASS", model: str = "test-model") -> None:
        self._response = response
        self._model = model
        self.call_count = 0
        self.last_messages: list[dict[str, str]] | None = None
        self.last_model: str | None = None

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.call_count += 1
        self.last_messages = messages
        self.last_model = model
        return self._response

    async def healthcheck(self) -> bool:
        return True
