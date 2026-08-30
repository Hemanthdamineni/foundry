"""Tests for EvalRunner — scenario evaluation orchestration."""

from __future__ import annotations

import json

import pytest

from foundry.features.eval_harness.runners.runner import EvalResult, EvalRunner
from foundry.features.eval_harness.suites.base import EvalScenario, EvalSuite


class FakeProvider:
    """Minimal fake LLM provider for testing — no real HTTP calls.

    Mirrors the ``LLMProvider`` interface without importing the real
    abstract base (avoids dependency on adapters.llm package).
    """

    def __init__(self, response: str = "PASS") -> None:
        self.response = response
        self.call_count = 0
        self.last_messages = None
        self.last_model = None

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        self.call_count += 1
        self.last_messages = messages
        self.last_model = model

        if self.response == "PASS":
            return json.dumps({"passed": True, "reason": "All good"})
        if self.response == "FAIL":
            return json.dumps({"passed": False, "reason": "Issues found", "issues": ["Bad code"]})
        return self.response

    async def healthcheck(self) -> bool:
        return True


class TestEvalRunner:
    """EvalRunner construction and run_suite behaviour."""

    @pytest.mark.asyncio
    async def test_run_suite_empty(self) -> None:
        """An empty suite produces a zeroed result."""
        provider = FakeProvider()
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(name="empty", scenarios=[])
        result = await runner.run_suite(suite)
        assert result.suite_name == "empty"
        assert result.total == 0
        assert result.passed == 0
        assert result.scenarios == []

    @pytest.mark.asyncio
    async def test_run_suite_all_pass(self) -> None:
        """Scenarios with expected_pass=True pass when judge returns PASS."""
        provider = FakeProvider(response="PASS")
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(
            name="pass-all",
            scenarios=[
                EvalScenario(name="s1", input="good output", expected_pass=True, phase="Chatting"),
                EvalScenario(name="s2", input="also good", expected_pass=True, phase="Chatting"),
            ],
        )
        result = await runner.run_suite(suite)
        assert result.total == 2
        assert result.passed == 2
        assert result.failed == 0
        for sr in result.scenarios:
            assert sr.passed is True
            assert sr.actual_pass is True

    @pytest.mark.asyncio
    async def test_run_suite_mixed(self) -> None:
        """Scenarios that should fail are flagged appropriately."""
        provider = FakeProvider(response="FAIL")
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(
            name="mixed",
            scenarios=[
                EvalScenario(name="should-pass", input="x", expected_pass=True),
                EvalScenario(name="should-fail", input="bad", expected_pass=False),
            ],
        )
        result = await runner.run_suite(suite)
        # Judge returns FAIL — so actual_pass=False for both.
        # "should-pass" expected_pass=True vs actual False => regression (not passed).
        # "should-fail" expected_pass=False vs actual False => passed.
        assert result.total == 2
        assert result.passed == 1  # only should-fail
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_run_suite_no_expectation(self) -> None:
        """When expected_pass is None, any non-error result passes."""
        provider = FakeProvider(response="PASS")
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(
            name="no-expect",
            scenarios=[
                EvalScenario(name="no-assert", input="whatever"),
            ],
        )
        result = await runner.run_suite(suite)
        assert result.total == 1
        assert result.passed == 1

    @pytest.mark.asyncio
    async def test_run_suite_with_debate(self) -> None:
        """When use_debate=True, debate results are included."""
        provider = FakeProvider(response='{"passed": true, "reason": "ok"}')
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(
            name="debate",
            scenarios=[EvalScenario(name="with-debate", input="test output", expected_pass=True)],
        )
        result = await runner.run_suite(suite, use_debate=True)
        assert result.total == 1
        assert result.scenarios[0].judge_verdict is not None
        assert result.scenarios[0].debate_transcript is not None

    @pytest.mark.asyncio
    async def test_runner_metadata(self) -> None:
        """Result metadata reflects runner configuration."""
        provider = FakeProvider()
        runner = EvalRunner(
            judge_provider=provider,
            debate_provider=provider,
            judge_model="judge-v1",
            debate_model="debate-v1",
        )
        suite = EvalSuite(name="meta", scenarios=[EvalScenario(name="t", input="x")])
        result = await runner.run_suite(suite)
        assert result.metadata["judge_model"] == "judge-v1"
        assert result.metadata["debate_model"] == "debate-v1"
        assert result.metadata["use_debate"] is False

    @pytest.mark.asyncio
    async def test_list_suites(self) -> None:
        """list_suites returns a summary dict per suite."""
        provider = FakeProvider()
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suites = {
            "a": EvalSuite(name="a", scenarios=[EvalScenario(name="s1", input="x")]),
            "b": EvalSuite(name="b", scenarios=[]),
        }
        result = runner.list_suites(suites)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"a", "b"}

    @pytest.mark.asyncio
    async def test_result_serialization(self) -> None:
        """EvalResult can be serialized and deserialized."""
        provider = FakeProvider(response="PASS")
        runner = EvalRunner(judge_provider=provider, debate_provider=provider)
        suite = EvalSuite(
            name="serialize",
            scenarios=[EvalScenario(name="s1", input="x", expected_pass=True)],
        )
        result = await runner.run_suite(suite)
        data = result.model_dump()
        restored = EvalResult.model_validate(data)
        assert restored.suite_name == "serialize"
        assert restored.total == 1
        assert restored.scenarios[0].scenario_name == "s1"
