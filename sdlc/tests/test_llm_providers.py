"""Tests for LLM provider abstraction, providers, and routing."""

from __future__ import annotations

import pytest

from sdlc.adapters.llm import FakeProvider, ModelRouter, OllamaProvider, OpenAIProvider


class TestFakeProvider:
    @pytest.mark.asyncio
    async def test_returns_canned_response(self) -> None:
        p = FakeProvider(response='{"passed": true}')
        result = await p.generate([{"role": "user", "content": "hi"}])
        assert result == '{"passed": true}'

    @pytest.mark.asyncio
    async def test_tracks_call_count(self) -> None:
        p = FakeProvider()
        assert p.call_count == 0
        await p.generate([{"role": "user", "content": "a"}])
        await p.generate([{"role": "user", "content": "b"}])
        assert p.call_count == 2

    @pytest.mark.asyncio
    async def test_tracks_last_messages(self) -> None:
        p = FakeProvider()
        msgs = [{"role": "user", "content": "test"}]
        await p.generate(msgs, model="m1", temperature=0.5)
        assert p.last_messages == msgs
        assert p.last_model == "m1"

    @pytest.mark.asyncio
    async def test_healthcheck(self) -> None:
        p = FakeProvider()
        assert await p.healthcheck() is True


class TestModelRouter:
    def test_default_route(self) -> None:
        p = FakeProvider()
        router = ModelRouter(default_provider=p, default_model="m1")
        provider, model = router.route("judge")
        assert provider is p
        assert model == "m1"

    def test_override_route(self) -> None:
        default = FakeProvider()
        override = FakeProvider()
        router = ModelRouter(default_provider=default, default_model="m1")
        router.add_override("judge", override, "m2")
        provider, model = router.route("judge")
        assert provider is override
        assert model == "m2"

    def test_unknown_role_falls_to_default(self) -> None:
        p = FakeProvider()
        router = ModelRouter(default_provider=p, default_model="m1")
        provider, model = router.route("nonexistent")
        assert provider is p
        assert model == "m1"

    def test_from_config_empty(self) -> None:
        p = FakeProvider()
        router = ModelRouter.from_config(
            default_provider=p,
            default_model="m1",
            routing_config=None,
            provider_pool=None,
        )
        provider, model = router.route("judge")
        assert provider is p

    def test_from_config_with_overrides(self) -> None:
        default = FakeProvider()
        custom = FakeProvider()
        pool = {"custom": custom}
        config = {"judge": {"provider": "custom", "model": "m2"}}
        router = ModelRouter.from_config(
            default_provider=default,
            default_model="m1",
            routing_config=config,
            provider_pool=pool,
        )
        provider, model = router.route("judge")
        assert provider is custom
        assert model == "m2"


class TestOllamaProvider:
    def test_init_defaults(self) -> None:
        p = OllamaProvider()
        assert p._base_url == "http://localhost:11434"
        assert p._default_model == "qwen3:8b"
        assert p._max_retries == 1

    def test_init_custom(self) -> None:
        p = OllamaProvider(
            base_url="http://10.0.0.1:11434",
            timeout_s=60,
            default_model="llama3",
            max_retries=3,
        )
        assert p._base_url == "http://10.0.0.1:11434"
        assert p._timeout_s == 60
        assert p._default_model == "llama3"
        assert p._max_retries == 3

    @pytest.mark.asyncio
    async def test_generate_raises_runtime_error_when_ollama_down(self) -> None:
        p = OllamaProvider(
            base_url="http://127.0.0.1:19999",
            timeout_s=1,
            max_retries=0,
        )
        with pytest.raises(RuntimeError, match="Ollama provider failed"):
            await p.generate([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false_when_down(self) -> None:
        p = OllamaProvider(
            base_url="http://127.0.0.1:19999",
            timeout_s=1,
        )
        assert await p.healthcheck() is False


class TestOpenAIProvider:
    def test_init_defaults(self) -> None:
        p = OpenAIProvider()
        assert "openai.com" in p._base_url
        assert p._default_model == "gpt-4o"
        assert p._max_retries == 2

    def test_init_custom(self) -> None:
        p = OpenAIProvider(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            default_model="deepseek/deepseek-r1",
            max_retries=0,
        )
        assert "openrouter.ai" in p._base_url
        assert p._default_model == "deepseek/deepseek-r1"

    @pytest.mark.asyncio
    async def test_generate_raises_runtime_error_no_key(self) -> None:
        p = OpenAIProvider(
            api_key="",
            base_url="https://api.openai.com/v1",
            timeout_s=1,
            max_retries=0,
        )
        with pytest.raises(RuntimeError, match="OpenAI provider failed"):
            await p.generate([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_generate_raises_runtime_error_bad_key(self) -> None:
        p = OpenAIProvider(
            api_key="sk-bad-key",
            base_url="https://api.openai.com/v1",
            timeout_s=3,
            max_retries=0,
        )
        with pytest.raises(RuntimeError, match="OpenAI provider failed"):
            await p.generate([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false_no_key(self) -> None:
        p = OpenAIProvider(api_key="")
        assert await p.healthcheck() is False

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false_bad_key(self) -> None:
        p = OpenAIProvider(api_key="sk-bad", timeout_s=2)
        assert await p.healthcheck() is False
