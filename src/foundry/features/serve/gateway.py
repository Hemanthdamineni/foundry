"""Model gateway — Ollama/OpenAI HTTP client for the serve server.

Provides the full ModelGateway implementation with all protocol helpers
inlined.  Imports Settings / BackendProtocol / resolve_backend_model from
features.serve.config (NOT api_server.config).  The ``message_content_to_text``
helper from ``sdlc_models.schemas`` is inlined here because that package
is not available at runtime in the serve environment.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from collections.abc import Sequence
from typing import Any

import httpx

from foundry.features.serve.config import BackendProtocol
from foundry.features.serve.config import resolve_backend_model
from foundry.features.serve.config import Settings


# ---------------------------------------------------------------------------
# Inlined from sdlc_models.schemas (package not available at serve runtime)
# ---------------------------------------------------------------------------

def message_content_to_text(
    content: str | list[dict[str, object]] | None,
) -> str:
    """Convert OpenAI-style message content (string or list of parts) to plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
            continue
        input_text = item.get("input_text")
        if isinstance(input_text, str):
            parts.append(input_text)
            continue
        nested = item.get("content")
        if isinstance(nested, str):
            parts.append(nested)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# SSE protocol (originally foundry.features.api_server.api.sse)
# ---------------------------------------------------------------------------

class SseProtocolError(ValueError):
    """Raised when an SSE payload is malformed."""


def parse_sse_line(line: str) -> tuple[bool, dict[str, Any] | None]:
    if line.startswith("data:[DONE]") or line.startswith("data: [DONE]"):
        return True, None

    if line.startswith(": ping"):
        return False, None

    if not line.startswith("data:"):
        return False, None

    payload = line[len("data:") :].strip()
    if not payload:
        return False, None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SseProtocolError(f"Malformed JSON in SSE line: {payload}") from exc

    if isinstance(data, dict) and "error" in data:
        error_data = data.get("error")
        if isinstance(error_data, dict):
            message = error_data.get("message")
            if isinstance(message, str) and message:
                raise SseProtocolError(message)
        raise SseProtocolError("Upstream returned streaming error payload")

    if not isinstance(data, dict):
        raise SseProtocolError("SSE data must be a JSON object")

    return False, data


def normalize_chat_chunk(
    payload: dict[str, Any],
    *,
    completion_id: str,
    model: str,
    created: int,
) -> dict[str, Any]:
    chunk = dict(payload)
    chunk.setdefault("id", completion_id)
    chunk.setdefault("object", "chat.completion.chunk")
    chunk.setdefault("created", created)
    chunk.setdefault("model", model)
    return chunk


# ---------------------------------------------------------------------------
# OpenAI-compatible protocol helpers (originally foundry.features.api_server.api.protocol)
# ---------------------------------------------------------------------------

def openai_error(
    message: str,
    *,
    error_type: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def new_chat_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def new_completion_id() -> str:
    return f"cmpl-{uuid.uuid4().hex}"


def unix_seconds() -> int:
    return int(time.time())


def build_chat_chunk(
    *,
    completion_id: str,
    model: str,
    created: int,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
    }


def build_usage_chunk(
    *,
    completion_id: str,
    model: str,
    created: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def build_chat_completion(
    *,
    completion_id: str,
    model: str,
    created: int,
    content: str | None,
    finish_reason: str,
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def map_done_reason_to_finish_reason(done_reason: str | None) -> str:
    normalized = (done_reason or "").strip().lower()
    if normalized in {"length", "max_tokens", "max_output_tokens"}:
        return "length"
    if normalized == "content_filter":
        return "content_filter"
    return "stop"


def normalize_ollama_tool_calls(
    raw_tool_calls: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not raw_tool_calls:
        return []

    normalized: list[dict[str, Any]] = []
    for index, call in enumerate(raw_tool_calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue

        name = str(function.get("name") or "")
        if not name:
            continue

        arguments = function.get("arguments")
        if isinstance(arguments, str):
            arguments_text = arguments
        elif isinstance(arguments, dict):
            arguments_text = json.dumps(arguments, ensure_ascii=False)
        else:
            arguments_text = "{}"

        tool_id = call.get("id")
        if not isinstance(tool_id, str) or not tool_id.strip():
            tool_id = f"call_{uuid.uuid4().hex[:12]}"

        normalized.append(
            {
                "index": index,
                "id": tool_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments_text,
                },
            }
        )

    return normalized


def strip_tool_call_index(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for call in tool_calls:
        copied = dict(call)
        copied.pop("index", None)
        serialized.append(copied)
    return serialized


# ---------------------------------------------------------------------------
# UpstreamError
# ---------------------------------------------------------------------------

class UpstreamError(RuntimeError):
    """Raised when the model backend request fails."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# ModelGateway — full implementation
# ---------------------------------------------------------------------------

class ModelGateway:
    """HTTP client that proxies chat-completion requests to an Ollama or
    OpenAI-compatible backend."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ollama_model_names_cache: tuple[str, ...] = ()
        self._ollama_model_names_cache_at: float = 0.0
        self._ollama_model_names_lock = asyncio.Lock()
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=None,
            write=settings.write_timeout_seconds,
            pool=settings.pool_timeout_seconds,
        )
        limits = httpx.Limits(
            max_connections=settings.max_connections,
            max_keepalive_connections=settings.max_keepalive_connections,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- URL helpers -------------------------------------------------------

    def _join_url(self, endpoint: str) -> str:
        base = self.settings.backend_base_url.rstrip("/")
        suffix = endpoint.lstrip("/")
        return f"{base}/{suffix}"

    def _ollama_generate_url(self) -> str:
        return self._join_url("api/generate")

    def _ollama_tags_url(self) -> str:
        return self._join_url("api/tags")

    def _ollama_chat_url(self) -> str:
        return self._join_url(self.settings.ollama_chat_endpoint)

    def _openai_chat_url(self) -> str:
        return self._join_url(self.settings.openai_chat_endpoint)

    def _openai_models_url(self) -> str:
        return self._join_url(self.settings.openai_models_endpoint)

    # -- Headers -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.settings.backend_api_key:
            headers["Authorization"] = f"Bearer {self.settings.backend_api_key}"
            headers["x-api-key"] = self.settings.backend_api_key
        return headers

    # -- Error helpers -----------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = response.text.strip()
        message = body or f"upstream returned HTTP {response.status_code}"
        raise UpstreamError(message, status_code=502)

    @staticmethod
    async def _raise_for_status_stream(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body_bytes = await response.aread()
        try:
            body = body_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        message = body or f"upstream returned HTTP {response.status_code}"
        raise UpstreamError(message, status_code=502)

    # -- Ollama model management -------------------------------------------

    async def warmup_model(
        self, *, backend_model: str, keep_alive: str = "30m"
    ) -> bool:
        if self.settings.backend_protocol != BackendProtocol.OLLAMA:
            return False
        payload = {
            "model": backend_model,
            "prompt": "",
            "stream": False,
            "keep_alive": keep_alive,
        }
        response = await self._client.post(
            self._ollama_generate_url(),
            json=payload,
            headers=self._headers(),
        )
        self._raise_for_status(response)
        return True

    async def list_ollama_model_names(
        self, *, refresh: bool = False
    ) -> tuple[str, ...]:
        if self.settings.backend_protocol != BackendProtocol.OLLAMA:
            return ()

        cache_ttl_seconds = 30.0
        if (
            not refresh
            and self._ollama_model_names_cache
            and (time.monotonic() - self._ollama_model_names_cache_at)
            < cache_ttl_seconds
        ):
            return self._ollama_model_names_cache

        async with self._ollama_model_names_lock:
            if (
                not refresh
                and self._ollama_model_names_cache
                and (time.monotonic() - self._ollama_model_names_cache_at)
                < cache_ttl_seconds
            ):
                return self._ollama_model_names_cache

            try:
                response = await self._client.get(
                    self._ollama_tags_url(),
                    headers=self._headers(),
                )
            except httpx.HTTPError:
                self._ollama_model_names_cache = ()
                self._ollama_model_names_cache_at = time.monotonic()
                return ()

            if response.status_code >= 400:
                self._ollama_model_names_cache = ()
                self._ollama_model_names_cache_at = time.monotonic()
                return ()

            try:
                payload = response.json()
            except json.JSONDecodeError:
                self._ollama_model_names_cache = ()
                self._ollama_model_names_cache_at = time.monotonic()
                return ()

            if not isinstance(payload, dict):
                self._ollama_model_names_cache = ()
                self._ollama_model_names_cache_at = time.monotonic()
                return ()

            models = payload.get("models")
            if not isinstance(models, list):
                self._ollama_model_names_cache = ()
                self._ollama_model_names_cache_at = time.monotonic()
                return ()

            seen: set[str] = set()
            names: list[str] = []
            for item in models:
                if not isinstance(item, dict):
                    continue
                for key in ("name", "model"):
                    value = item.get(key)
                    if not isinstance(value, str):
                        continue
                    normalized = value.strip()
                    if not normalized or normalized in seen:
                        continue
                    seen.add(normalized)
                    names.append(normalized)

            self._ollama_model_names_cache = tuple(names)
            self._ollama_model_names_cache_at = time.monotonic()
            return self._ollama_model_names_cache

    async def resolve_ollama_backend_model(
        self,
        requested_model: str | None,
        *,
        fallback_models: Sequence[str] = (),
    ) -> str:
        backend_model = resolve_backend_model(self.settings, requested_model)
        if self.settings.backend_protocol != BackendProtocol.OLLAMA:
            return backend_model

        available_models = await self.list_ollama_model_names()
        if not available_models:
            return backend_model

        if backend_model in available_models:
            return backend_model

        for candidate in fallback_models:
            normalized = candidate.strip()
            if normalized and normalized in available_models:
                return normalized

        return available_models[0]

    async def unload_model(self, *, backend_model: str) -> bool:
        if self.settings.backend_protocol != BackendProtocol.OLLAMA:
            return False
        payload = {
            "model": backend_model,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }
        response = await self._client.post(
            self._ollama_generate_url(),
            json=payload,
            headers=self._headers(),
        )
        self._raise_for_status(response)
        return True

    async def list_openai_models(self) -> list[dict[str, Any]]:
        if self.settings.backend_protocol != BackendProtocol.OPENAI:
            return []

        response = await self._client.get(
            self._openai_models_url(),
            headers=self._headers(),
        )
        if response.status_code >= 400:
            return []

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []

        models: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                models.append(item)
        return models

    # -- Chat completions (non-stream) -------------------------------------

    async def chat_completions_non_stream(
        self,
        request_body: dict[str, Any],
        *,
        public_model: str,
        backend_model: str,
    ) -> dict[str, Any]:
        if self.settings.backend_protocol == BackendProtocol.OPENAI:
            return await self._openai_non_stream(
                request_body, backend_model=backend_model
            )
        return await self._ollama_non_stream(
            request_body,
            public_model=public_model,
            backend_model=backend_model,
        )

    async def _openai_non_stream(
        self,
        request_body: dict[str, Any],
        *,
        backend_model: str,
    ) -> dict[str, Any]:
        payload = dict(request_body)
        payload["model"] = backend_model
        payload["stream"] = False

        response = await self._client.post(
            self._openai_chat_url(),
            json=payload,
            headers=self._headers(),
        )
        self._raise_for_status(response)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise UpstreamError(
                "upstream returned malformed JSON", status_code=502
            ) from exc

        if not isinstance(data, dict):
            raise UpstreamError(
                "upstream response must be a JSON object", status_code=502
            )
        return data

    async def _ollama_non_stream(
        self,
        request_body: dict[str, Any],
        *,
        public_model: str,
        backend_model: str,
    ) -> dict[str, Any]:
        payload = self._to_ollama_payload(
            request_body,
            backend_model=backend_model,
            stream=False,
        )
        response = await self._client.post(
            self._ollama_chat_url(),
            json=payload,
            headers=self._headers(),
        )
        self._raise_for_status(response)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise UpstreamError(
                "ollama returned malformed JSON", status_code=502
            ) from exc

        if not isinstance(data, dict):
            raise UpstreamError(
                "ollama response must be a JSON object", status_code=502
            )

        message = data.get("message")
        if not isinstance(message, dict):
            raise UpstreamError(
                "ollama response missing message object", status_code=502
            )

        content = message.get("content")
        if not isinstance(content, str):
            content = ""

        tool_calls = normalize_ollama_tool_calls(
            message.get("tool_calls")
            if isinstance(message.get("tool_calls"), list)
            else None
        )
        finish_reason = (
            "tool_calls"
            if tool_calls
            else map_done_reason_to_finish_reason(
                str(data.get("done_reason") or "")
            )
        )

        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)

        return build_chat_completion(
            completion_id=new_chat_id(),
            model=public_model,
            created=unix_seconds(),
            content=content,
            finish_reason=finish_reason,
            tool_calls=strip_tool_call_index(tool_calls) if tool_calls else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    # -- Chat completions (stream) -----------------------------------------

    async def chat_completions_stream(
        self,
        request_body: dict[str, Any],
        *,
        public_model: str,
        backend_model: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self.settings.backend_protocol == BackendProtocol.OPENAI:
            async for chunk in self._openai_stream(
                request_body,
                public_model=public_model,
                backend_model=backend_model,
            ):
                yield chunk
            return

        async for chunk in self._ollama_stream(
            request_body,
            public_model=public_model,
            backend_model=backend_model,
        ):
            yield chunk

    async def _openai_stream(
        self,
        request_body: dict[str, Any],
        *,
        public_model: str,
        backend_model: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload = dict(request_body)
        payload["model"] = backend_model
        payload["stream"] = True
        payload.setdefault("stream_options", {"include_usage": True})

        completion_id = new_chat_id()
        created = unix_seconds()

        async with self._client.stream(
            "POST",
            self._openai_chat_url(),
            json=payload,
            headers=self._headers(),
        ) as response:
            await self._raise_for_status_stream(response)
            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped:
                    continue
                done, data = parse_sse_line(stripped)
                if done:
                    break
                if data is None:
                    continue
                yield normalize_chat_chunk(
                    data,
                    completion_id=completion_id,
                    model=public_model,
                    created=created,
                )

    async def _ollama_stream(
        self,
        request_body: dict[str, Any],
        *,
        public_model: str,
        backend_model: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload = self._to_ollama_payload(
            request_body,
            backend_model=backend_model,
            stream=True,
        )

        completion_id = new_chat_id()
        created = unix_seconds()
        saw_tool_calls = False
        emitted_tool_keys: set[str] = set()

        # Start with assistant role chunk to match OpenAI-compatible streams.
        yield build_chat_chunk(
            completion_id=completion_id,
            model=public_model,
            created=created,
            delta={"role": "assistant"},
            finish_reason=None,
        )

        async with self._client.stream(
            "POST",
            self._ollama_chat_url(),
            json=payload,
            headers=self._headers(),
        ) as response:
            await self._raise_for_status_stream(response)

            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise UpstreamError(
                        "ollama stream produced malformed JSON",
                        status_code=502,
                    ) from exc

                if not isinstance(data, dict):
                    raise UpstreamError(
                        "ollama stream event must be an object",
                        status_code=502,
                    )

                message = data.get("message")
                if isinstance(message, dict):
                    token = message.get("content")
                    if isinstance(token, str) and token:
                        yield build_chat_chunk(
                            completion_id=completion_id,
                            model=public_model,
                            created=created,
                            delta={"content": token},
                            finish_reason=None,
                        )

                    raw_calls = message.get("tool_calls")
                    if isinstance(raw_calls, list) and raw_calls:
                        tool_calls = normalize_ollama_tool_calls(raw_calls)
                        for call in tool_calls:
                            call_key = (
                                f"{call.get('id')}|"
                                f"{call.get('function', {}).get('name')}|"
                                f"{call.get('function', {}).get('arguments')}"
                            )
                            if call_key in emitted_tool_keys:
                                continue
                            emitted_tool_keys.add(call_key)
                            saw_tool_calls = True
                            yield build_chat_chunk(
                                completion_id=completion_id,
                                model=public_model,
                                created=created,
                                delta={"tool_calls": [call]},
                                finish_reason=None,
                            )

                if bool(data.get("done")):
                    finish_reason = (
                        "tool_calls"
                        if saw_tool_calls
                        else map_done_reason_to_finish_reason(
                            str(data.get("done_reason") or "")
                        )
                    )
                    yield build_chat_chunk(
                        completion_id=completion_id,
                        model=public_model,
                        created=created,
                        delta={},
                        finish_reason=finish_reason,
                    )

                    prompt_tokens = int(data.get("prompt_eval_count") or 0)
                    completion_tokens = int(data.get("eval_count") or 0)
                    if prompt_tokens or completion_tokens:
                        yield build_usage_chunk(
                            completion_id=completion_id,
                            model=public_model,
                            created=created,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                        )
                    break

    # -- Ollama payload builder --------------------------------------------

    def _to_ollama_payload(
        self,
        request_body: dict[str, Any],
        *,
        backend_model: str,
        stream: bool,
    ) -> dict[str, Any]:
        messages = request_body.get("messages")
        if not isinstance(messages, list):
            raise UpstreamError("messages must be an array", status_code=400)

        ollama_messages: list[dict[str, Any]] = []
        for raw_message in messages:
            if not isinstance(raw_message, dict):
                continue
            role = str(raw_message.get("role") or "").strip().lower()
            if not role:
                continue
            if role == "developer":
                role = "system"

            content = message_content_to_text(raw_message.get("content"))
            item: dict[str, Any] = {
                "role": role,
                "content": content,
            }

            name = raw_message.get("name")
            if isinstance(name, str) and name:
                item["name"] = name

            tool_call_id = raw_message.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                item["tool_call_id"] = tool_call_id

            tool_calls = raw_message.get("tool_calls")
            if isinstance(tool_calls, list):
                item["tool_calls"] = tool_calls

            ollama_messages.append(item)

        payload: dict[str, Any] = {
            "model": backend_model,
            "messages": ollama_messages,
            "stream": stream,
        }

        tools = request_body.get("tools")
        if isinstance(tools, list):
            payload["tools"] = tools

        options: dict[str, Any] = {}
        temperature = request_body.get("temperature")
        if isinstance(temperature, (int, float)):
            options["temperature"] = float(temperature)

        top_p = request_body.get("top_p")
        if isinstance(top_p, (int, float)):
            options["top_p"] = float(top_p)

        stop = request_body.get("stop")
        if isinstance(stop, str):
            options["stop"] = [stop]
        elif isinstance(stop, list):
            options["stop"] = [str(item) for item in stop]

        max_completion_tokens = request_body.get("max_completion_tokens")
        max_tokens = request_body.get("max_tokens")
        token_budget = None
        if isinstance(max_completion_tokens, int):
            token_budget = max_completion_tokens
        elif isinstance(max_tokens, int):
            token_budget = max_tokens
        if token_budget is not None:
            options["num_predict"] = token_budget

        if options:
            payload["options"] = options

        return payload


__all__ = [
    "ModelGateway",
    "UpstreamError",
    "SseProtocolError",
    "build_chat_completion",
    "build_chat_chunk",
    "build_usage_chunk",
    "map_done_reason_to_finish_reason",
    "new_chat_id",
    "new_completion_id",
    "normalize_chat_chunk",
    "normalize_ollama_tool_calls",
    "openai_error",
    "parse_sse_line",
    "sse_done",
    "sse_event",
    "strip_tool_call_index",
    "unix_seconds",
]
