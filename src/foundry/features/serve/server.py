"""Serve — FastAPI server using TurnEngine + auto_run.

This is the HTTP entrypoint for Helix.  It provides an OpenAI-compatible
chat-completion API with auto-orchestration, task CRUD, agent-loop execution
(via ``auto_run``), model warm-up, and Continue bridge integration.

Key architectural differences from the predecessor ``api_server``:
- Uses ``TurnEngine`` + ``auto_run`` in place of ``PhaseEngine`` /
  ``Orchestrator``.
- Imports all shared primitives from ``foundry.core.*``.
- Task execution goes through a ``RoleGraph`` (planner/executor/verifier/
  repairer loop) rather than a hard-coded phase machine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# ── Core primitives ───────────────────────────────────────────────────────
from foundry.core.config.settings import BackendProtocol
from foundry.core.logging import get_logger
from foundry.core.store import SqliteStore
from foundry.core.turn_engine import AgentLoopGraph, DebateGraph, RoleGraph, Terminal, auto_run

# ── Serve-layer components ────────────────────────────────────────────────
from foundry.features.serve.config import Settings, resolve_backend_model
from foundry.features.serve.gateway import (
    ModelGateway,
    UpstreamError,
    build_chat_completion,
    new_completion_id,
    openai_error,
    sse_done,
    sse_event,
    unix_seconds,
)

# ── Serve-local utilities (relocated from api_server) ─────────────────────
from foundry.features.serve.chat_intent import is_small_talk
from foundry.features.serve.bridge.continue_bridge import ContinueBridgeWorker
from foundry.core.logging import StructuredLogger
from foundry.core.event_bus import Event, EventBus, EventType

logger = logging.getLogger("foundry.serve")

# ═══════════════════════════════════════════════════════════════════════════ #
#  Global state (initialized during lifespan)
# ═══════════════════════════════════════════════════════════════════════════ #

settings = Settings.from_yaml_first()
store = SqliteStore(settings.db_path)
gateway = ModelGateway(settings)

event_bus = EventBus()
structured_log = StructuredLogger(
    event_bus,
    log_path=str(settings.resolve_runtime_path(settings.structured_log_path)),
)

# ═══════════════════════════════════════════════════════════════════════════ #
#  Agent-loop RoleGraph — using canonical AgentLoopGraph from core
# ═══════════════════════════════════════════════════════════════════════════ #

# ═══════════════════════════════════════════════════════════════════════════ #
#  Pydantic request/response models
# ═══════════════════════════════════════════════════════════════════════════ #


class ChatMessage(BaseModel):
    role: str = "user"
    content: str | list[dict[str, Any]] = ""
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


class LegacyCompletionRequest(BaseModel):
    model: str = ""
    prompt: str | list[str] = ""
    stream: bool = False
    max_tokens: int | None = None


class TaskCreateRequest(BaseModel):
    prompt: str = ""
    repo_path: str = "."
    priority: str = "normal"
    mode: str = "auto"


class TaskRunRequest(BaseModel):
    max_repairs: int = 3
    model: str | None = None


class ToolRequestClaimRequest(BaseModel):
    worker_id: str = ""
    max_items: int = 1
    wait_seconds: float = 0.0


class ToolRequestResultRequest(BaseModel):
    worker_id: str = ""
    claim_token: str = ""
    resume_token: str = ""
    version: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    logs: str = ""
    exit_code: int | None = None
    error_message: str | None = None
    failure_class: str | None = None


class ToolRequestFailRequest(BaseModel):
    worker_id: str = ""
    claim_token: str = ""
    resume_token: str = ""


class BridgeHeartbeatRequest(BaseModel):
    worker_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════ #
#  Utility helpers
# ═══════════════════════════════════════════════════════════════════════════ #


def _error_json(
    status_code: int,
    message: str,
    *,
    error_type: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=openai_error(message, error_type=error_type, param=param, code=code),
    )


def _public_model(requested: str | None) -> str:
    """Resolve the public-facing model name."""  # noqa: D202
    if requested is None:
        return settings.default_model
    normalized = requested.strip()
    return normalized or settings.default_model


def _stream_headers() -> dict[str, str]:
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


# ── Coding-intent detection (ported from api_server) ──────────────────────

_WORKSPACE_HINT_KEYS = (
    "workspacePath",
    "workspace_path",
    "workspaceDir",
    "workspace_dir",
    "workspaceDirectory",
    "workspace_directory",
    "cwd",
    "workingDirectory",
    "working_directory",
    "repoPath",
    "repo_path",
)

_CODE_VERBS = (
    "implement",
    "create",
    "build",
    "make",
    "write",
    "generate",
    "develop",
    "code",
    "fix",
    "debug",
    "refactor",
    "optimize",
    "add",
    "update",
    "modify",
)

_CODE_OBJECT_HINTS = (
    "game",
    "app",
    "application",
    "script",
    "code",
    "function",
    "class",
    "module",
    "api",
    "service",
    "endpoint",
    "feature",
    "bug",
    "tests",
    "pytest",
    "ui",
    "frontend",
    "backend",
    "pygame",
    "python",
    "javascript",
    "typescript",
    "react",
    "vue",
    "django",
    "flask",
    "fastapi",
)

_SPECIFICITY_HINTS = (
    "in this project",
    "in this repo",
    "codebase",
    "existing",
    "module",
    "file",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    "endpoint",
    "api",
    "database",
    "migration",
    "unit test",
    "integration test",
    "acceptance criteria",
    "requirements",
)

_AMBIGUOUS_SCOPE_HINTS = (
    "game",
    "app",
    "application",
    "website",
    "web app",
    "service",
    "api",
    "platform",
    "system",
    "agent",
    "bot",
)

_AMBIGUOUS_ALWAYS = ("game", "website")


def _is_coding_intent_prompt(prompt: str) -> bool:
    text = prompt.strip()
    if not text:
        return False
    if is_small_talk(text):
        return False

    lowered = text.lower()
    if "```" in text:
        return True

    verb_hit = any(re.search(rf"\b{re.escape(token)}\b", lowered) for token in _CODE_VERBS)
    if not verb_hit:
        return False

    object_hit = any(token in lowered for token in _CODE_OBJECT_HINTS)
    return object_hit


def _is_vague_coding_prompt(prompt: str) -> bool:
    text = prompt.strip()
    if not text:
        return False
    if is_small_talk(text):
        return False

    lowered = text.lower()
    words = re.findall(r"\w+", lowered)
    word_count = len(words)
    has_specificity = any(token in lowered for token in _SPECIFICITY_HINTS)
    has_ambiguous_scope = any(token in lowered for token in _AMBIGUOUS_SCOPE_HINTS)
    has_always_ambiguous = any(token in lowered for token in _AMBIGUOUS_ALWAYS)
    has_code_verb = any(re.search(rf"\b{re.escape(token)}\b", lowered) for token in _CODE_VERBS)
    has_code_object = any(token in lowered for token in _CODE_OBJECT_HINTS)

    if has_code_verb and not has_code_object and not has_specificity:
        return True
    if has_always_ambiguous and not has_specificity:
        return True
    if has_ambiguous_scope and not has_specificity and word_count <= 24:
        return True
    return False


def _is_orchestration_candidate_prompt(prompt: str) -> bool:
    return _is_coding_intent_prompt(prompt) or _is_vague_coding_prompt(prompt)


def _extract_workspace_hint(body: dict[str, Any]) -> str | None:
    for key in _WORKSPACE_HINT_KEYS:
        value = body.pop(key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        for key in _WORKSPACE_HINT_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_repo_path(repo_path: str) -> str:
    raw = repo_path.strip() or "."
    normalized = Path(raw).expanduser()
    if not normalized.is_absolute():
        normalized = Path.cwd() / normalized
    resolved = normalized.resolve()
    if not resolved.exists():
        raise ValueError(f"repo_path does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"repo_path is not a directory: {resolved}")
    return str(resolved)


def _latest_user_prompt_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        role = str(message.role).strip().lower()
        if role != "user":
            continue
        content = message.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            text = " ".join(parts)
        else:
            text = ""
        if text.strip():
            return text.strip()
    return ""


# ── Model helpers ─────────────────────────────────────────────────────────

def _backend_fallback_models(current_model: str) -> tuple[str, ...]:
    """Build an ordered list of fallback models for retry-on-not-found."""
    fallback_models: list[str] = []
    seen: set[str] = {current_model}

    # Collect all configured models
    for model_id in (*settings.public_models, *settings.model_aliases):
        if model_id not in seen:
            seen.add(model_id)
            fallback_models.append(model_id)

    return tuple(fallback_models)


def _is_model_not_found_error(exc: UpstreamError) -> bool:
    message = str(exc).lower()
    return "model" in message and "not found" in message


def _fallback_backend_model(current_model: str, *, available_models: set[str] | None = None) -> str | None:
    for model_id in _backend_fallback_models(current_model):
        if available_models is not None and model_id not in available_models:
            continue
        return model_id
    return None


def _retry_backend_model(
    exc: UpstreamError,
    current_model: str,
    *,
    available_models: set[str] | None = None,
) -> str | None:
    if not _is_model_not_found_error(exc):
        return None
    return _fallback_backend_model(current_model, available_models=available_models)


def _configured_model_ids() -> list[str]:
    """Return a deduplicated list of all configured model IDs."""
    seen: set[str] = set()
    ids: list[str] = []
    for model_id in (*settings.public_models, *settings.model_aliases, settings.default_model):
        if model_id not in seen:
            seen.add(model_id)
            ids.append(model_id)
    return ids


# ── Bridge auth ───────────────────────────────────────────────────────────

def _require_bridge_auth(x_bridge_key: str | None) -> JSONResponse | None:
    expected = settings.bridge_shared_key
    if not expected:
        return None
    if x_bridge_key == expected:
        return None
    return _error_json(401, "invalid bridge key", code="bridge_auth_failed")


# ── Request tracking helpers ──────────────────────────────────────────────

def _request_start_event(
    *,
    request_id: str,
    endpoint: str,
    stream: bool,
    public_model: str,
    backend_model: str,
    has_tools: bool,
) -> float:
    started = time.perf_counter()
    event_bus.publish(
        Event(
            EventType.REQUEST_START,
            {
                "endpoint": endpoint,
                "stream": stream,
                "model": public_model,
                "backend_model": backend_model,
                "tools": has_tools,
            },
            request_id=request_id,
            model=public_model,
        )
    )
    return started


def _request_end_event(
    *,
    request_id: str,
    endpoint: str,
    stream: bool,
    public_model: str,
    status: str,
    started: float,
    retries: int = 0,
    chunks: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "endpoint": endpoint,
        "stream": stream,
        "model": public_model,
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "retries": retries,
    }
    if chunks is not None:
        payload["chunks"] = chunks
    event_bus.publish(
        Event(
            EventType.REQUEST_END,
            payload,
            request_id=request_id,
            model=public_model,
        )
    )


# ═══════════════════════════════════════════════════════════════════════════ #
#  Idle chat warmer
# ═══════════════════════════════════════════════════════════════════════════ #


class _IdleChatWarmer:
    """Periodically warms the chat model when the server is idle."""

    def __init__(self, settings: Settings, gateway: ModelGateway) -> None:
        self._settings = settings
        self._gateway = gateway
        self._active_requests = 0
        self._active_lock = asyncio.Lock()
        self._running = False
        self._monitor_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="idle-chat-warmer")

    async def stop(self) -> None:
        self._running = False
        if self._monitor_task is None:
            return
        self._monitor_task.cancel()
        try:
            await self._monitor_task
        except asyncio.CancelledError:
            pass
        self._monitor_task = None

    async def mark_request_started(self) -> None:
        async with self._active_lock:
            self._active_requests += 1

    async def mark_request_finished(self) -> None:
        async with self._active_lock:
            if self._active_requests > 0:
                self._active_requests -= 1

    async def _monitor_loop(self) -> None:
        idle_warmup = float(self._settings.idle_warmup_seconds)
        idle_monitor = float(self._settings.idle_monitor_seconds)

        while self._running:
            await asyncio.sleep(idle_monitor)
            async with self._active_lock:
                is_idle = self._active_requests == 0
            if not is_idle:
                continue
            if self._settings.backend_protocol == BackendProtocol.OLLAMA:
                await self._warm()

    async def _warm(self) -> None:
        model = settings.default_model
        try:
            resolved = await self._gateway.resolve_ollama_backend_model(model)
            await self._gateway.warmup_model(backend_model=resolved)
        except Exception:
            pass  # warming is best-effort


# ═══════════════════════════════════════════════════════════════════════════ #
#  Embedded bridge runtime
# ═══════════════════════════════════════════════════════════════════════════ #


class _EmbeddedBridgeRuntime:
    """Manages the Continue bridge worker lifecycle."""

    def __init__(self, worker: ContinueBridgeWorker | None) -> None:
        self._worker = worker
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is None or self._task is not None:
            return
        self._task = asyncio.create_task(self._worker.run(), name="embedded-continue-bridge")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None


# ═══════════════════════════════════════════════════════════════════════════ #
#  Lifespan
# ═══════════════════════════════════════════════════════════════════════════ #

idle_warmer = _IdleChatWarmer(settings, gateway)

embedded_bridge_worker = (
    ContinueBridgeWorker(
        server_base_url=f"http://127.0.0.1:{settings.server_port}",
        shared_key=settings.bridge_shared_key,
        worker_id=settings.embedded_bridge_worker_id,
        continue_command=settings.continue_command,
        poll_interval_seconds=settings.embedded_bridge_poll_interval_seconds,
        heartbeat_interval_seconds=settings.bridge_heartbeat_interval_seconds,
        claim_wait_seconds=settings.bridge_claim_wait_seconds,
    )
    if settings.embedded_bridge_enabled
    else None
)
embedded_bridge = _EmbeddedBridgeRuntime(embedded_bridge_worker)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    await store.initialize()
    settings.ensure_dirs()
    await embedded_bridge.start()
    await idle_warmer.start()
    logger.info("serve server started: host=%s port=%s protocol=%s", settings.server_host, settings.server_port, settings.backend_protocol.value)
    try:
        yield
    finally:
        await idle_warmer.stop()
        await embedded_bridge.stop()
        await gateway.aclose()
        await store.close()
        logger.info("serve server stopped")


# ═══════════════════════════════════════════════════════════════════════════ #
#  FastAPI app
# ═══════════════════════════════════════════════════════════════════════════ #

app = FastAPI(
    title="Helix Serve",
    version="0.1.0",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════════ #
#  Health & models
# ═══════════════════════════════════════════════════════════════════════════ #


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "backend_protocol": settings.backend_protocol.value,
        "default_model": settings.default_model,
        "model_aliases": list(settings.model_aliases),
        "task_api_enabled": settings.task_api_enabled,
    }


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    created = unix_seconds()
    model_ids = _configured_model_ids()

    if settings.backend_protocol == BackendProtocol.OLLAMA:
        installed = set(await gateway.list_ollama_model_names())
        if installed:
            filtered = [m for m in model_ids if m in installed]
            model_ids = filtered or sorted(installed)

    return {
        "object": "list",
        "data": [
            {
                "id": mid,
                "object": "model",
                "created": created,
                "owned_by": "helix-serve",
            }
            for mid in model_ids
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════ #
#  /v1/chat/completions
# ═══════════════════════════════════════════════════════════════════════════ #


async def _resolve_request_backend_model(requested_model: str | None) -> str:
    backend_model = resolve_backend_model(settings, requested_model)
    if settings.backend_protocol != BackendProtocol.OLLAMA:
        return backend_model
    return await gateway.resolve_ollama_backend_model(
        backend_model,
        fallback_models=_backend_fallback_models(backend_model),
    )


async def _run_agent_loop_for_chat(
    prompt: str,
    workspace_hint: str | None,
    request_id: str,
    model: str,
) -> tuple[str, str]:
    """Create a task and run the agent loop, returning (status_text, result_text)."""
    repo_path = "."
    if workspace_hint:
        try:
            repo_path = _normalize_repo_path(workspace_hint)
        except ValueError:
            logger.warning("ignoring invalid workspace hint: %s", workspace_hint)

    task_dict = {
        "task_id": f"task_{uuid.uuid4().hex}",
        "prompt": prompt,
        "repo_path": repo_path,
        "priority": "normal",
        "mode": "auto",
        "status": "QUEUED",
        "current_phase": "planner",
        "context": {"prompt": prompt, "task": prompt},
    }
    task = await store.create_task(task_dict)
    task_id = task["task_id"]

    event_bus.publish(
        Event(
            EventType.DECISION,
            {
                "from_phase": "chat_api",
                "to_phase": "task_api",
                "reason": "auto_orchestrate_coding_prompt",
                "task_id": task_id,
            },
            request_id=request_id,
            task_id=task_id,
            model=model,
        )
    )

    try:
        graph = AgentLoopGraph(max_repairs=2)
        result = await auto_run(
            store=store,
            task_id=task_id,
            graph=graph,
            generate_fn=lambda p: gateway.generate_text(
                p,
                model=model,
                system_prompt=None,
            ),
            max_turns=20,
        )
        status = "ok"
        result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        # ── Post-loop debate review ────────────────────────────────────────
        try:
            debate_graph = DebateGraph(
                store=store,
                task_id=task_id,
                artefact=str(result),
            )
            debate_result = await auto_run(
                store=store,
                task_id=task_id,
                graph=debate_graph,
                generate_fn=lambda p: gateway.generate_text(
                    p,
                    model=model,
                    system_prompt=None,
                ),
                max_turns=10,
            )
            debate_verdict = str(debate_result) if debate_result else ""
            if ":x:" in debate_verdict.lower() or "fail" in debate_verdict.lower():
                logger.info("debate flagged issues in task %s, but loop completed", task_id)
                result_text += f"\n\n---\n*Debate review flagged concerns:* {debate_verdict}"
        except Exception as debate_exc:
            logger.warning("debate round failed for task %s: %s", task_id, debate_exc)
    except Exception as exc:
        logger.warning("agent loop failed for chat task %s: %s", task_id, exc)
        status = "failed"
        result_text = f"Task {task_id} encountered an error: {exc}"

    return status, result_text


@app.post("/chat/completions", include_in_schema=False, response_model=None)
@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
) -> JSONResponse | dict[str, Any] | StreamingResponse:
    if not request.messages:
        return _error_json(400, "missing messages", param="messages")

    public_model = _public_model(request.model)
    backend_model = await _resolve_request_backend_model(request.model)
    body = request.to_openai_body() if hasattr(request, "to_openai_body") else request.model_dump()
    if not isinstance(body, dict):
        body = request.model_dump()
    workspace_hint = _extract_workspace_hint(body)
    request_id = new_completion_id()
    request_started = _request_start_event(
        request_id=request_id,
        endpoint="/v1/chat/completions",
        stream=request.stream,
        public_model=public_model,
        backend_model=backend_model,
        has_tools=False,
    )

    user_prompt = _latest_user_prompt_text(request.messages)

    # ── Auto-orchestration: detect coding intent and run agent loop ─────
    if (
        settings.task_api_enabled
        and settings.chat_auto_orchestrate
        and not request.stream
        and _is_orchestration_candidate_prompt(user_prompt)
    ):
        try:
            await idle_warmer.mark_request_started()
            status, result_text = await _run_agent_loop_for_chat(
                prompt=user_prompt,
                workspace_hint=workspace_hint,
                request_id=request_id,
                model=public_model,
            )
        finally:
            await idle_warmer.mark_request_finished()

        response = build_chat_completion(
            completion_id=request_id,
            model=public_model,
            created=unix_seconds(),
            content=result_text,
            finish_reason="stop",
        )
        _request_end_event(
            request_id=request_id,
            endpoint="/v1/chat/completions",
            stream=False,
            public_model=public_model,
            status=status,
            started=request_started,
        )
        return response

    # ── Standard passthrough to upstream ────────────────────────────────
    if request.stream:
        event_bus.publish(
            Event(
                EventType.STREAM_START,
                {"endpoint": "/v1/chat/completions", "model": public_model},
                request_id=request_id,
                model=public_model,
            )
        )
        await idle_warmer.mark_request_started()

        async def _stream() -> AsyncGenerator[str, None]:
            attempt_model = backend_model
            retried = False
            retry_count = 0
            chunk_count = 0
            status = "ok"
            try:
                while True:
                    emitted_any = False
                    try:
                        async for chunk in gateway.chat_completions_stream(
                            body,
                            public_model=public_model,
                            backend_model=attempt_model,
                        ):
                            emitted_any = True
                            chunk["model"] = public_model
                            chunk_count += 1
                            yield sse_event(chunk)
                        break
                    except UpstreamError as exc:
                        retry_model = None
                        if not retried and not emitted_any:
                            if settings.backend_protocol == BackendProtocol.OLLAMA:
                                installed = set(await gateway.list_ollama_model_names(refresh=True))
                                available = installed if installed else None
                            else:
                                available = None
                            retry_model = _retry_backend_model(exc, attempt_model, available_models=available)
                        if retry_model is not None:
                            logger.warning(
                                "retrying streaming request with fallback model '%s' after error for '%s': %s",
                                retry_model, attempt_model, exc,
                            )
                            attempt_model = retry_model
                            retried = True
                            retry_count += 1
                            continue
                        logger.error("streaming upstream error: %s", exc)
                        status = "upstream_error"
                        yield sse_event(openai_error(str(exc), error_type="api_error", code="upstream_error"))
                        break
            finally:
                _request_end_event(
                    request_id=request_id,
                    endpoint="/v1/chat/completions",
                    stream=True,
                    public_model=public_model,
                    status=status,
                    started=request_started,
                    retries=retry_count,
                    chunks=chunk_count,
                )
                event_bus.publish(
                    Event(
                        EventType.STREAM_END,
                        {"endpoint": "/v1/chat/completions", "model": public_model},
                        request_id=request_id,
                        model=public_model,
                    )
                )
                await idle_warmer.mark_request_finished()
            yield sse_done()

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers=_stream_headers(),
        )

    # ── Non-streaming passthrough ───────────────────────────────────────
    await idle_warmer.mark_request_started()
    try:
        response = await gateway.chat_completions_non_stream(
            body,
            public_model=public_model,
            backend_model=backend_model,
        )
    except UpstreamError as exc:
        available = None
        if settings.backend_protocol == BackendProtocol.OLLAMA:
            installed = set(await gateway.list_ollama_model_names(refresh=True))
            if installed:
                available = installed
        retry_model = _retry_backend_model(exc, backend_model, available_models=available)
        if retry_model is not None:
            logger.warning("retrying non-stream request with '%s' after error for '%s'", retry_model, backend_model)
            try:
                response = await gateway.chat_completions_non_stream(
                    body,
                    public_model=public_model,
                    backend_model=retry_model,
                )
            except UpstreamError as retry_exc:
                _request_end_event(
                    request_id=request_id,
                    endpoint="/v1/chat/completions",
                    stream=False,
                    public_model=public_model,
                    status="upstream_error",
                    started=request_started,
                    retries=1,
                )
                return _error_json(retry_exc.status_code, str(retry_exc), error_type="api_error", code="upstream_error")
        else:
            _request_end_event(
                request_id=request_id,
                endpoint="/v1/chat/completions",
                stream=False,
                public_model=public_model,
                status="upstream_error",
                started=request_started,
            )
            return _error_json(exc.status_code, str(exc), error_type="api_error", code="upstream_error")
    finally:
        await idle_warmer.mark_request_finished()

    response["model"] = public_model
    _request_end_event(
        request_id=request_id,
        endpoint="/v1/chat/completions",
        stream=False,
        public_model=public_model,
        status="ok",
        started=request_started,
    )
    return response


# ═══════════════════════════════════════════════════════════════════════════ #
#  /v1/completions (legacy)
# ═══════════════════════════════════════════════════════════════════════════ #


@app.post("/v1/completions", include_in_schema=False, response_model=None)
async def legacy_completions(
    request: LegacyCompletionRequest,
) -> dict[str, Any] | StreamingResponse | JSONResponse:
    prompt_text: str
    if isinstance(request.prompt, list):
        prompt_text = "\n".join(str(p) for p in request.prompt if p)
    else:
        prompt_text = str(request.prompt or "")

    chat_request = ChatCompletionRequest(
        model=request.model,
        messages=[ChatMessage(role="user", content=prompt_text)],
        stream=request.stream,
    )
    public_model = _public_model(chat_request.model)
    backend_model = await _resolve_request_backend_model(chat_request.model)
    body = chat_request.model_dump()
    request_id = new_completion_id()
    request_started = _request_start_event(
        request_id=request_id,
        endpoint="/v1/completions",
        stream=request.stream,
        public_model=public_model,
        backend_model=backend_model,
        has_tools=False,
    )

    if request.stream:
        completion_id = request_id
        created = unix_seconds()
        event_bus.publish(
            Event(
                EventType.STREAM_START,
                {"endpoint": "/v1/completions", "model": public_model},
                request_id=completion_id,
                model=public_model,
            )
        )
        await idle_warmer.mark_request_started()

        async def _legacy_stream() -> AsyncGenerator[str, None]:
            attempt_model = backend_model
            retried = False
            retry_count = 0
            chunk_count = 0
            status = "ok"
            try:
                while True:
                    emitted_any = False
                    try:
                        async for chunk in gateway.chat_completions_stream(
                            body,
                            public_model=public_model,
                            backend_model=attempt_model,
                        ):
                            emitted_any = True
                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                continue
                            choice = choices[0] if isinstance(choices[0], dict) else {}
                            delta = choice.get("delta") if isinstance(choice, dict) else {}
                            if not isinstance(delta, dict):
                                delta = {}
                            token = delta.get("content")
                            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
                            payload = {
                                "id": completion_id,
                                "object": "text_completion",
                                "created": created,
                                "model": public_model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "text": token if isinstance(token, str) else "",
                                        "logprobs": None,
                                        "finish_reason": finish_reason,
                                    }
                                ],
                            }
                            chunk_count += 1
                            yield sse_event(payload)
                        break
                    except UpstreamError as exc:
                        if not retried and not emitted_any:
                            available = None
                            if settings.backend_protocol == BackendProtocol.OLLAMA:
                                installed = set(await gateway.list_ollama_model_names(refresh=True))
                                if installed:
                                    available = installed
                            retry_model = _retry_backend_model(exc, attempt_model, available_models=available)
                            if retry_model is not None:
                                attempt_model = retry_model
                                retried = True
                                retry_count += 1
                                continue
                        logger.error("legacy streaming upstream error: %s", exc)
                        status = "upstream_error"
                        yield sse_event(openai_error(str(exc), error_type="api_error", code="upstream_error"))
                        break
            finally:
                _request_end_event(
                    request_id=request_id,
                    endpoint="/v1/completions",
                    stream=True,
                    public_model=public_model,
                    status=status,
                    started=request_started,
                    retries=retry_count,
                    chunks=chunk_count,
                )
                event_bus.publish(
                    Event(
                        EventType.STREAM_END,
                        {"endpoint": "/v1/completions", "model": public_model},
                        request_id=completion_id,
                        model=public_model,
                    )
                )
                await idle_warmer.mark_request_finished()
            yield sse_done()

        return StreamingResponse(
            _legacy_stream(),
            media_type="text/event-stream",
            headers=_stream_headers(),
        )

    await idle_warmer.mark_request_started()
    try:
        response = await gateway.chat_completions_non_stream(
            body,
            public_model=public_model,
            backend_model=backend_model,
        )
    except UpstreamError as exc:
        available = None
        if settings.backend_protocol == BackendProtocol.OLLAMA:
            installed = set(await gateway.list_ollama_model_names(refresh=True))
            if installed:
                available = installed
        retry_model = _retry_backend_model(exc, backend_model, available_models=available)
        if retry_model is not None:
            try:
                response = await gateway.chat_completions_non_stream(
                    body,
                    public_model=public_model,
                    backend_model=retry_model,
                )
            except UpstreamError as retry_exc:
                _request_end_event(
                    request_id=request_id,
                    endpoint="/v1/completions",
                    stream=False,
                    public_model=public_model,
                    status="upstream_error",
                    started=request_started,
                    retries=1,
                )
                return _error_json(retry_exc.status_code, str(retry_exc), error_type="api_error", code="upstream_error")
        else:
            _request_end_event(
                request_id=request_id,
                endpoint="/v1/completions",
                stream=False,
                public_model=public_model,
                status="upstream_error",
                started=request_started,
            )
            return _error_json(exc.status_code, str(exc), error_type="api_error", code="upstream_error")
    finally:
        await idle_warmer.mark_request_finished()

    choices = response.get("choices")
    message: dict[str, Any] = {}
    finish_reason = "stop"
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        c = choices[0]
        maybe_msg = c.get("message")
        if isinstance(maybe_msg, dict):
            message = maybe_msg
        maybe_fr = c.get("finish_reason")
        if isinstance(maybe_fr, str):
            finish_reason = maybe_fr

    content = message.get("content") if isinstance(message, dict) else ""
    _request_end_event(
        request_id=request_id,
        endpoint="/v1/completions",
        stream=False,
        public_model=public_model,
        status="ok",
        started=request_started,
    )
    return {
        "id": request_id,
        "object": "text_completion",
        "created": unix_seconds(),
        "model": public_model,
        "choices": [
            {
                "index": 0,
                "text": str(content or ""),
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
        "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }


# ═══════════════════════════════════════════════════════════════════════════ #
#  /v1/tasks  —  CRUD
# ═══════════════════════════════════════════════════════════════════════════ #


def _require_task_api() -> JSONResponse | None:
    if settings.task_api_enabled:
        return None
    return _error_json(404, "task api disabled", code="task_api_disabled")


def _serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id", ""),
        "prompt": task.get("prompt", ""),
        "repo_path": task.get("repo_path", "."),
        "priority": task.get("priority", "normal"),
        "mode": task.get("mode", "auto"),
        "status": task.get("status", "UNKNOWN"),
        "current_phase": task.get("current_phase", ""),
        "branch_name": task.get("branch_name"),
        "created_at": task.get("created_at", ""),
        "updated_at": task.get("updated_at", ""),
    }


@app.post("/v1/tasks", response_model=None)
async def create_task(request: TaskCreateRequest) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard

    prompt = request.prompt.strip()
    mode = request.mode.strip().lower() or "auto"

    try:
        repo_path = _normalize_repo_path(request.repo_path)
    except ValueError as exc:
        return _error_json(400, str(exc), param="repo_path", code="invalid_repo_path")

    task_dict = {
        "task_id": f"task_{uuid.uuid4().hex}",
        "prompt": prompt,
        "repo_path": repo_path,
        "priority": request.priority.strip() or "normal",
        "mode": mode,
        "status": "QUEUED",
        "current_phase": "planner",
        "context": {"prompt": prompt, "task": prompt},
    }

    try:
        task = await store.create_task(task_dict)
    except Exception as exc:
        logger.error("task creation failed: %s", exc)
        return _error_json(500, "task creation failed", code="task_create_failed")

    return {"task": _serialize_task(task)}


@app.get("/v1/tasks", response_model=None)
async def list_tasks() -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard
    tasks = await store.list_tasks()
    return {"tasks": [_serialize_task(t) for t in tasks]}


@app.get("/v1/tasks/{task_id}", response_model=None)
async def get_task(task_id: str) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard
    task = await store.get_task(task_id)
    if task is None:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")
    return {"task": _serialize_task(task)}


@app.get("/v1/tasks/{task_id}/state", response_model=None)
async def get_task_state(task_id: str) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard
    try:
        snapshot = await store.task_state_snapshot(task_id)
    except KeyError:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")
    return {"state": snapshot}


@app.get("/v1/tasks/{task_id}/events", response_model=None)
async def get_task_events(
    task_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard
    task = await store.get_task(task_id)
    if task is None:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")
    events = await store.task_events(task_id, limit=limit)
    return {"task_id": task_id, "events": events}


# ═══════════════════════════════════════════════════════════════════════════ #
#  /v1/tasks/{id}/run  —  Execute agent loop via auto_run
# ═══════════════════════════════════════════════════════════════════════════ #


@app.post("/v1/tasks/{task_id}/run", response_model=None)
async def run_task(task_id: str, request: TaskRunRequest) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard

    task = await store.get_task(task_id)
    if task is None:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")

    prompt = task.get("prompt", task.get("context", {}).get("prompt", ""))
    if not prompt:
        return _error_json(400, "task has no prompt", code="task_no_prompt")

    model = request.model or settings.default_model

    # Mark task as running
    await store.update_task(task_id, {"status": "RUNNING"})

    graph = AgentLoopGraph(max_repairs=request.max_repairs)

    async def _generate(p: str) -> str:
        return await gateway.generate_text(p, model=model)

    try:
        result = await auto_run(
            store=store,
            task_id=task_id,
            graph=graph,
            generate_fn=_generate,
            max_turns=50,
        )

        # ── Post-loop debate review ────────────────────────────────────────
        try:
            debate_graph = DebateGraph(
                store=store,
                task_id=task_id,
                artefact=str(result),
            )
            debate_result = await auto_run(
                store=store,
                task_id=task_id,
                graph=debate_graph,
                generate_fn=_generate,
                max_turns=10,
            )
            debate_verdict = str(debate_result) if debate_result else ""
        except Exception as debate_exc:
            logger.warning("debate round failed for task %s: %s", task_id, debate_exc)
            debate_verdict = ""

        await store.update_task(task_id, {"status": "DONE", "result": result})
        result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        payload = {"task_id": task_id, "status": "DONE", "result": result_text}
        if debate_verdict:
            payload["debate_verdict"] = debate_verdict
        return payload
    except Exception as exc:
        logger.error("agent loop failed for task %s: %s", task_id, exc)
        await store.update_task(task_id, {"status": "FAILED", "error": str(exc)})
        return _error_json(500, f"agent loop failed: {exc}", code="agent_loop_failed")


# ═══════════════════════════════════════════════════════════════════════════ #
#  Task lifecycle endpoints
# ═══════════════════════════════════════════════════════════════════════════ #


@app.post("/v1/tasks/{task_id}/cancel", response_model=None)
async def cancel_task(task_id: str) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard

    try:
        await store.update_task(task_id, {"status": "CANCELED"})
        return {"task_id": task_id, "status": "CANCELED"}
    except ValueError:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")


@app.post("/v1/tasks/{task_id}/resume", response_model=None)
async def resume_task(task_id: str) -> dict[str, Any] | JSONResponse:
    guard = _require_task_api()
    if guard is not None:
        return guard

    try:
        await store.update_task(task_id, {"status": "QUEUED"})
        return {"task_id": task_id, "status": "QUEUED"}
    except ValueError:
        return _error_json(404, f"task not found: {task_id}", code="task_not_found")


# ═══════════════════════════════════════════════════════════════════════════ #
#  Bridge internal endpoints
# ═══════════════════════════════════════════════════════════════════════════ #


@app.post("/internal/tool-requests/claim", response_model=None)
async def claim_tool_requests(
    request: ToolRequestClaimRequest,
    x_bridge_key: str | None = Header(default=None, alias="X-Bridge-Key"),
) -> dict[str, Any] | JSONResponse:
    auth_error = _require_bridge_auth(x_bridge_key)
    if auth_error is not None:
        return auth_error

    wait_seconds = max(0.0, min(30.0, request.wait_seconds))
    deadline = time.monotonic() + wait_seconds
    records: list[dict[str, Any]] = []
    requeue_stale = True

    while True:
        records = await store.claim_tool_requests(
            worker_id=request.worker_id,
            max_items=request.max_items,
            lease_seconds=settings.bridge_lease_seconds,
            heartbeat_timeout_seconds=settings.bridge_heartbeat_timeout_seconds,
            requeue_stale=requeue_stale,
        )
        requeue_stale = False
        if records or wait_seconds <= 0:
            break
        if time.monotonic() >= deadline:
            break
        remaining = max(0.0, deadline - time.monotonic())
        await asyncio.sleep(min(0.5, max(0.05, remaining)))

    return {"requests": records}


@app.post("/internal/tool-requests/{request_id}/result", response_model=None)
async def submit_tool_result(
    request_id: str,
    request: ToolRequestResultRequest,
    x_bridge_key: str | None = Header(default=None, alias="X-Bridge-Key"),
) -> dict[str, Any] | JSONResponse:
    auth_error = _require_bridge_auth(x_bridge_key)
    if auth_error is not None:
        return auth_error

    try:
        result_id, idempotent = await store.store_tool_result(
            request_id=request_id,
            status="ok",
            claim_token=request.claim_token,
            resume_token=request.resume_token,
            version=request.version,
            output_payload=request.output,
            logs=request.logs,
            exit_code=request.exit_code,
            error_message=request.error_message,
            failure_class=request.failure_class,
        )
    except (KeyError, ValueError) as exc:
        return _error_json(409, str(exc), code="tool_request_state_conflict")

    return {"ok": True, "result_id": result_id, "idempotent": idempotent}


@app.post("/internal/tool-requests/{request_id}/fail", response_model=None)
async def fail_tool_request(
    request_id: str,
    request: ToolRequestFailRequest,
    x_bridge_key: str | None = Header(default=None, alias="X-Bridge-Key"),
) -> dict[str, Any] | JSONResponse:
    auth_error = _require_bridge_auth(x_bridge_key)
    if auth_error is not None:
        return auth_error

    try:
        result_id, idempotent = await store.store_tool_result(
            request_id=request_id,
            status="failed",
            claim_token=request.claim_token,
            resume_token=request.resume_token,
            version=request.version,
            output_payload={},
            logs="",
            exit_code=None,
            error_message="tool request failed via /fail endpoint",
            failure_class="execution_error",
        )
    except (KeyError, ValueError) as exc:
        return _error_json(409, str(exc), code="tool_request_state_conflict")

    return {"ok": True, "result_id": result_id, "idempotent": idempotent}


@app.post("/internal/heartbeats", response_model=None)
async def bridge_heartbeat(
    request: BridgeHeartbeatRequest,
    x_bridge_key: str | None = Header(default=None, alias="X-Bridge-Key"),
) -> dict[str, Any] | JSONResponse:
    auth_error = _require_bridge_auth(x_bridge_key)
    if auth_error is not None:
        return auth_error

    await store.update_worker_heartbeat(worker_id=request.worker_id, metadata=request.metadata)
    requeued = await store.requeue_stale_claims(
        heartbeat_timeout_seconds=settings.bridge_heartbeat_timeout_seconds,
    )
    return {"ok": True, "requeued": requeued}


# ═══════════════════════════════════════════════════════════════════════════ #
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════════ #


def main() -> None:
    """Run the serve server via uvicorn."""
    import uvicorn

    uvicorn.run(
        "foundry.features.serve.server:app",
        host=settings.server_host,
        port=settings.server_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
