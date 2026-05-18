from __future__ import annotations

from typing import Any

import pytest

from sdlc.adapters.llm import FakeProvider
from sdlc.engine.consensus import ConsensusEngine
from sdlc.engine.debate_runtime import DebateRuntime, _agent_roles_for_phase
from sdlc.models import (
    BudgetPolicy,
    CollapseSignal,
    ConsensusResult,
    DebateAgentRole,
    DebateRound,
    JudgeVerdict,
    MinorityReport,
    Task,
)
from sdlc.runtime.tools.phase import (
    _debate_dict,
    _is_iteration_limit_reached,
    _run_debate_if_needed,
)

_FAKE = FakeProvider()


def _mock_agent_response(response_text: str = "PASS - looks good"):
    async def mock_call(_agent_cfg, _phase, _output, _round_num, _prev):
        return response_text
    return mock_call


def _mock_failed_consensus(result: ConsensusResult | None = None):
    if result is None:
        result = ConsensusResult(reached=True, passed=False, reason="mock fail")

    async def mock_eval(**_kwargs: Any):
        return result

    return mock_eval


class TestMinorityReport:
    def test_minority_report_defaults(self) -> None:
        r = MinorityReport(agent_role="coding", objection="bug found", round_number=1)
        assert r.severity == "info"
        assert r.agent_role == "coding"

    def test_minority_report_roundtrip(self) -> None:
        r = MinorityReport(agent_role="review", objection="security concern", round_number=2, severity="critical")
        data = r.model_dump(mode="json")
        restored = MinorityReport(**data)
        assert restored.objection == "security concern"
        assert restored.severity == "critical"


class TestCollapseSignal:
    def test_collapse_defaults(self) -> None:
        c = CollapseSignal()
        assert c.detected is False
        assert c.confidence == 0.0

    def test_collapse_detected(self) -> None:
        c = CollapseSignal(detected=True, confidence=0.8, reason="sycophantic agreement")
        assert c.detected
        assert c.confidence == 0.8


class TestDebateModels:
    def test_debate_round_with_previous(self) -> None:
        r = DebateRound(
            round_number=1,
            responses={"coding": "PASS"},
            previous_responses={"coding": "FAIL"},
        )
        assert r.previous_responses["coding"] == "FAIL"

    def test_consensus_result_with_minority(self) -> None:
        c = ConsensusResult(
            reached=True,
            passed=True,
            minority_reports=[
                MinorityReport(agent_role="review", objection="security", round_number=0),
            ],
            collapse_signal=CollapseSignal(detected=True, confidence=0.9),
            residual_objections=["still concerned about security"],
        )
        assert len(c.minority_reports) == 1
        assert c.collapse_signal.detected
        assert len(c.residual_objections) == 1


class TestAgentRolesForPhase:
    def test_coding_roles(self) -> None:
        roles = _agent_roles_for_phase("Coding")
        assert len(roles) == 3
        assert DebateAgentRole.CODING in roles
        assert DebateAgentRole.REVIEW in roles
        assert DebateAgentRole.TESTING in roles


class TestConsensusEngine:
    @pytest.mark.asyncio
    async def test_empty_responses(self) -> None:
        engine = ConsensusEngine(_FAKE)
        task = Task(task_id="t1", description="test")
        result = await engine.evaluate({}, task, "Coding", 0, 3)
        assert result.reached
        assert result.passed
        assert "No agents" in result.reason

    @pytest.mark.asyncio
    async def test_majority_consensus_all_pass(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {"coding": "PASS - looks good", "review": "PASS - acceptable"}
        result = engine._majority_consensus(responses, 0, 3)
        assert result.passed

    @pytest.mark.asyncio
    async def test_majority_consensus_stalemate(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {"coding": "FAIL", "review": "FAIL"}
        result = engine._majority_consensus(responses, 2, 3)
        assert not result.reached
        assert "Stalemate" in result.reason

    def test_extract_minority_reports(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {"coding": "PASS", "review": "FAIL - bugs"}
        verdicts = {"coding": True, "review": False}
        reports = engine.extract_minority_reports(responses, verdicts)
        assert len(reports) == 1
        assert reports[0].agent_role == "review"

    def test_extract_minority_reports_all_pass(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {"coding": "PASS", "review": "PASS"}
        verdicts = {"coding": True, "review": True}
        reports = engine.extract_minority_reports(responses, verdicts)
        assert len(reports) == 0

    def test_detect_collapse_positive(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {
            "coding": "I agree with the previous reviewer. Same here.",
            "review": "I concur. Nothing to add.",
        }
        signal = engine.detect_collapse(responses)
        assert signal.detected

    def test_detect_collapse_negative(self) -> None:
        engine = ConsensusEngine(_FAKE)
        responses = {
            "coding": "PASS - well structured code with good error handling",
            "review": "FAIL - missing input validation in line 42",
        }
        signal = engine.detect_collapse(responses)
        assert not signal.detected

    def test_extract_residual_objections_found(self) -> None:
        engine = ConsensusEngine(_FAKE)
        rounds = [
            {"coding": "FAIL - I see a concern about security"},
            {"coding": "PASS - the security concern still remains but is acceptable"},
        ]
        objections = engine.extract_residual_objections(rounds)
        assert len(objections) > 0

    def test_extract_residual_objections_single_round(self) -> None:
        engine = ConsensusEngine(_FAKE)
        objections = engine.extract_residual_objections([{"coding": "PASS"}])
        assert objections == []


class TestDebateRuntime:
    @pytest.mark.asyncio
    async def test_run_debate_disabled(self) -> None:
        runtime = DebateRuntime(_FAKE)
        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=0),
        )
        transcript = await runtime.run_debate(task, "Coding", "some output")
        assert len(transcript.rounds) == 0
        assert transcript.consensus is not None
        assert "Debate disabled" in transcript.consensus.reason

    @pytest.mark.asyncio
    async def test_partial_completion_one_agent_fails(self) -> None:
        runtime = DebateRuntime(_FAKE)
        runtime._consensus.evaluate = _mock_failed_consensus(
            ConsensusResult(reached=True, passed=True, reason="mock consensus"),
        )
        call_count = 0
        async def mock_call(_cfg, _phase, _output, _round_num, _prev):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise TimeoutError("timeout")
            return "PASS - ok"
        runtime._call_agent = mock_call

        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=1),
        )
        transcript = await runtime.run_debate(task, "Coding", "output")
        assert transcript.consensus is not None
        assert transcript.consensus.passed

    @pytest.mark.asyncio
    async def test_timeout_and_retry_agent_recovery(self) -> None:
        runtime = DebateRuntime(_FAKE)
        runtime._consensus.evaluate = _mock_failed_consensus(
            ConsensusResult(reached=True, passed=True, reason="ok"),
        )
        call_count = 0
        async def flaky_call(_cfg, _phase, _output, _round_num, _prev):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timeout")
            return "PASS - recovered"
        runtime._call_agent = flaky_call

        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=1),
        )
        transcript = await runtime.run_debate(task, "Coding", "output")
        responses = list(transcript.rounds[0].responses.values())
        assert any("PASS" in r for r in responses)

    @pytest.mark.asyncio
    async def test_three_round_protocol_truncated_to_budget(self) -> None:
        runtime = DebateRuntime(_FAKE)
        runtime._consensus.evaluate = _mock_failed_consensus(
            ConsensusResult(reached=False, passed=False, reason="no consensus"),
        )
        runtime._call_agent = _mock_agent_response("PASS - ok")

        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=2),
        )
        transcript = await runtime.run_debate(task, "Coding", "output")
        assert len(transcript.rounds) == 2

    @pytest.mark.asyncio
    async def test_three_round_protocol_full(self) -> None:
        runtime = DebateRuntime(_FAKE)
        runtime._consensus.evaluate = _mock_failed_consensus(
            ConsensusResult(reached=False, passed=False, reason="no consensus"),
        )
        runtime._call_agent = _mock_agent_response("PASS - ok")

        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=3),
        )
        transcript = await runtime.run_debate(task, "Coding", "output")
        assert len(transcript.rounds) == 3

    @pytest.mark.asyncio
    async def test_collapse_detected_multi_round(self) -> None:
        runtime = DebateRuntime(_FAKE)
        runtime._consensus.evaluate = _mock_failed_consensus(
            ConsensusResult(reached=False, passed=False, reason="no consensus",
                            agent_verdicts={"coding": True, "review": True}),
        )
        runtime._call_agent = _mock_agent_response("I agree. Same here. Nothing to add.")

        task = Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=2),
        )
        transcript = await runtime.run_debate(task, "Coding", "output")
        assert transcript.consensus is not None
        assert transcript.consensus.collapse_signal.detected


class TestRunDebateIfNeeded:
    def _make_verdict(self, *, passed: bool) -> JudgeVerdict:
        return JudgeVerdict(passed=passed, reason="test")

    def _make_task(self, debate_rounds: int = 3) -> Task:
        return Task(
            task_id="t1", description="test",
            budget=BudgetPolicy(max_debate_rounds=debate_rounds),
        )

    @pytest.mark.asyncio
    async def test_no_debate_runtime(self) -> None:
        task = self._make_task()
        verdict = self._make_verdict(passed=False)
        result, transcript = await _run_debate_if_needed(task, "Coding", "output", verdict, None)
        assert result == verdict
        assert transcript is None

    @pytest.mark.asyncio
    async def test_debate_disabled_in_budget(self) -> None:
        task = self._make_task(debate_rounds=0)
        verdict = self._make_verdict(passed=False)
        runtime = DebateRuntime(_FAKE)
        result, transcript = await _run_debate_if_needed(task, "Coding", "output", verdict, runtime)
        assert result == verdict
        assert transcript is None

    @pytest.mark.asyncio
    async def test_verdict_already_passed_skips_debate(self) -> None:
        task = self._make_task()
        verdict = self._make_verdict(passed=True)
        runtime = DebateRuntime(_FAKE)
        result, transcript = await _run_debate_if_needed(task, "Coding", "output", verdict, runtime)
        assert result == verdict
        assert transcript is None


class TestDebateDict:
    def test_none_transcript(self) -> None:
        assert _debate_dict(None) is None

    def test_transcript_no_consensus(self) -> None:
        from sdlc.models import DebateTranscript as DT
        t = DT(task_id="t1", phase="Coding")
        assert _debate_dict(t) is None

    def test_transcript_with_consensus(self) -> None:
        c = ConsensusResult(reached=True, passed=True, reason="all good")
        from sdlc.models import DebateTranscript as DT
        t = DT(task_id="t1", phase="Coding", consensus=c, rounds=[])
        d = _debate_dict(t)
        assert d is not None
        assert d["consensus_reached"] is True
        assert d["consensus_passed"] is True
        assert d["reason"] == "all good"


class TestIsIterationLimitReached:
    def test_not_review(self) -> None:
        assert _is_iteration_limit_reached("Coding", "Review", 10, 8) is False

    def test_not_coding_transition(self) -> None:
        assert _is_iteration_limit_reached("Review", "Testing", 10, 8) is False

    def test_below_threshold(self) -> None:
        assert _is_iteration_limit_reached("Review", "Coding", 5, 8) is False

    def test_at_threshold(self) -> None:
        assert _is_iteration_limit_reached("Review", "Coding", 8, 8) is True

    def test_above_threshold(self) -> None:
        assert _is_iteration_limit_reached("Review", "Coding", 10, 8) is True


class TestExtractVerdictFromText:
    def test_pass_detected(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("PASS - looks good") is True

    def test_fail_detected(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("FAIL - bug found") is False

    def test_pass_with_context(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("I think PASS, it works.") is True

    def test_fail_with_context(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("FAIL, security issue.") is False

    def test_ambiguous_returns_none(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("Let me think about this") is None

    def test_mixed_pass_fail_returns_none(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("PASS but some fail cases") is None

    def test_pass_in_compass_not_detected(self) -> None:
        assert ConsensusEngine._extract_verdict_from_text("compass direction") is None
