"""Application-layer LLM wiring for the MCP server.

``server.py`` deliberately keeps LLM providers out of its module imports.
This plugin module is the "optional dependency that the lifespan context
may wire up" (see server.py module docstring): it builds a provider pool
from ``Settings.llm``, health-checks it, and constructs the optional

- ``JudgeEngine``   — LLM verdicts on phase transitions
- ``DebateRuntime`` — 3-round multi-agent debate on Review transitions

Everything degrades gracefully: any construction or health-check failure
returns ``None`` and the server keeps running in deterministic-only mode.
Set ``FOUNDRY_MCP_DISABLE_LLM=1`` to force deterministic-only mode, or
``FOUNDRY_MCP_FAKE_LLM=1`` to wire a canned-response provider (testing).
"""

from __future__ import annotations

import os
from typing import Any

from foundry.core.config.settings import Settings
from foundry.core.logging import get_logger

log = get_logger("mcp.plugins")


async def build_llm_stack(settings: Settings) -> dict[str, Any]:
    """Build the optional judge/debate stack from settings.

    Returns a dict with keys ``judge_engine`` and ``debate_runtime``, each
    set to a wired instance or ``None`` when unavailable.
    """
    stack: dict[str, Any] = {"judge_engine": None, "debate_runtime": None}

    if os.getenv("FOUNDRY_MCP_DISABLE_LLM") and not os.getenv("FOUNDRY_MCP_FAKE_LLM"):
        log.info("LLM wiring disabled via FOUNDRY_MCP_DISABLE_LLM")
        return stack

    try:
        # Lazy, function-level imports — never at server-module import time.
        from foundry.features.sdlc_runtime.adapters.llm._testing import (
            FakeProvider,
        )
        from foundry.features.sdlc_runtime.adapters.llm.providers import (
            OllamaProvider,
            OpenAIProvider,
        )
        from foundry.features.sdlc_runtime.engine.debate_runtime import (
            DebateRuntime,
        )
        from foundry.features.sdlc_runtime.engine.judge import JudgeEngine
    except ImportError as exc:
        log.warning("LLM adapter modules unavailable: %s", exc)
        return stack

    if os.getenv("FOUNDRY_MCP_FAKE_LLM"):
        import json as _json

        verdict_json = _json.dumps(
            {"passed": True, "reason": "fake judge pass", "issues": [], "severity": "info"}
        )
        fake = FakeProvider(response=verdict_json)
        stack["judge_engine"] = JudgeEngine(provider=fake, model="fake")
        stack["debate_runtime"] = DebateRuntime(provider=fake, model="fake")
        log.info("LLM stack wired with FakeProvider (FOUNDRY_MCP_FAKE_LLM)")
        return stack

    llm = settings.llm
    pool: dict[str, Any] = {}
    default_provider: Any = None

    for name, cfg in llm.providers.items():
        api_key = cfg.api_key or os.getenv("OPENAI_API_KEY", "")
        if cfg.type == "ollama":
            provider: Any = OllamaProvider(
                base_url=cfg.base_url,
                default_model=cfg.default_model,
            )
        elif cfg.type == "openai":
            provider = OpenAIProvider(
                base_url=cfg.base_url,
                api_key=api_key,
                default_model=cfg.default_model,
            )
        else:
            log.warning("Unknown provider type for %s: %s", name, cfg.type)
            continue
        pool[name] = provider
        if name == llm.default_provider:
            default_provider = provider

    if default_provider is None and pool:
        default_provider = next(iter(pool.values()))

    if default_provider is None:
        log.info("No LLM providers configured — judge/debate stay disabled")
        return stack

    try:
        healthy = await default_provider.healthcheck()
    except Exception as exc:  # noqa: BLE001 — degrade, never crash lifespan
        log.warning("LLM health check failed (%s) — judge/debate disabled", exc)
        return stack

    if not healthy:
        log.info(
            "Default LLM provider '%s' unreachable — judge/debate disabled",
            llm.default_provider,
        )
        return stack

    # Verify the configured models actually exist; fall back to whatever
    # the provider has available (e.g. a single locally-pulled model).
    available: list[str] = []
    if hasattr(default_provider, "list_models"):
        try:
            available = await default_provider.list_models()
        except Exception as exc:  # noqa: BLE001
            log.warning("Model listing failed (%s)", exc)

    def _resolve_model(requested: str) -> str | None:
        if not requested:
            requested = llm.default_model
        if not available:
            return requested  # server didn't tell us; let the call fail loudly
        for name in available:
            if name == requested or name.split(":")[0] == requested.split(":")[0]:
                return name
        fallback = available[0]
        log.warning(
            "Model '%s' not available — falling back to '%s'",
            requested,
            fallback,
        )
        return fallback

    routing = llm.routing
    judge_model = _resolve_model(routing.judge_model)
    debate_model = _resolve_model(routing.debate_agent_model)
    consensus_model = routing.debate_consensus_model or debate_model

    if judge_model is None or debate_model is None:
        log.info("No usable LLM model available — judge/debate disabled")
        return stack

    stack["judge_engine"] = JudgeEngine(
        provider=default_provider,
        model=judge_model,
    )
    stack["debate_runtime"] = DebateRuntime(
        provider=default_provider,
        model=debate_model,
    )
    log.info(
        "LLM stack wired (provider=%s, judge=%s, debate=%s)",
        llm.default_provider,
        judge_model,
        consensus_model,
    )
    return stack
