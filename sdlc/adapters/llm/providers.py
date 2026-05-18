"""Concrete LLM providers — Ollama (local) and OpenAI-compatible (remote)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from sdlc.adapters.llm.base import LLMProvider
from sdlc.log import get_logger

log = get_logger("llm_providers")


class OllamaProvider(LLMProvider):
    """Local Ollama provider via the /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout_s: int = 120,
        default_model: str = "qwen3:8b",
        max_retries: int = 1,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._default_model = default_model
        self._max_retries = max_retries

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens  # type: ignore[call-overload]
        if response_format is not None:
            body["format"] = response_format

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(f"{self._base_url}/api/chat", json=body)
                    resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                message = data.get("message", {})
                return str(message.get("content", ""))
            except (httpx.HTTPError, OSError, ValueError) as e:
                last_exc = e
                log.warning("Ollama attempt %d failed: %s", attempt + 1, e)
                if attempt < self._max_retries:
                    await asyncio.sleep(1.0)

        msg = f"Ollama provider failed after {self._max_retries + 1} attempts: {last_exc}"
        raise RuntimeError(msg)

    async def healthcheck(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
            return True
        except Exception:
            return False


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider (OpenAI, OpenRouter, DeepSeek, Together, etc.)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: int = 120,
        default_model: str = "gpt-4o",
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._default_model = default_model
        self._max_retries = max_retries

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = {"type": "json_object", "schema": response_format}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=body,
                        headers=headers,
                    )
                    resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                choices = data.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    return str(message.get("content", ""))
                msg = "OpenAI response missing choices"
                raise ValueError(msg)
            except (httpx.HTTPError, ValueError) as e:
                last_exc = e
                log.warning("OpenAI provider attempt %d failed: %s", attempt + 1, e)
                if attempt < self._max_retries:
                    await asyncio.sleep(1.0)

        msg = f"OpenAI provider failed after {self._max_retries + 1} attempts: {last_exc}"
        raise RuntimeError(msg)

    async def healthcheck(self) -> bool:
        if not self._api_key:
            return False
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                resp.raise_for_status()
            return True
        except Exception:
            return False
