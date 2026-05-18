"""DebateRuntime — orchestrates multi-agent debate with 3-round protocol.

Round 1 — Independent: agents respond without seeing each other.
Round 2 — Deliberation: agents see all Round 1 responses, may revise.
Round 3 — Final: agents give final positions after full deliberation.

If max_rounds < 3, the protocol truncates gracefully.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sdlc.adapters.llm import LLMProvider
from sdlc.engine.consensus import ConsensusEngine
from sdlc.exceptions import DebateError
from sdlc.log import get_logger
from sdlc.models import (
    CollapseSignal,
    ConsensusResult,
    DebateAgentConfig,
    DebateAgentRole,
    DebateRound,
    DebateTranscript,
    MinorityReport,
)

if TYPE_CHECKING:
    from sdlc.models import BudgetPolicy, Task
    from sdlc.runtime.tracing import Tracer

log = get_logger("debate_runtime")

_DEBATE_SYSTEM_PROMPTS: dict[str, str] = {
    "specs": (
        "You are a Specs Reviewer. Evaluate the output for completeness of requirements, "
        "clear scope definition, and unambiguous constraints. Look for missing edge cases, "
        "vague requirements, and scope creep."
    ),
    "planning": (
        "You are a Planning Reviewer. Evaluate the implementation plan for technical soundness, "
        "feasibility, risk assessment, and proper sequencing. Look for missing dependencies, "
        "underestimated complexity, and architectural gaps."
    ),
    "coding": (
        "You are a Code Reviewer. Evaluate the code for correctness, style, security, "
        "and adherence to the plan. Look for bugs, anti-patterns, security vulnerabilities, "
        "and deviation from requirements."
    ),
    "review": (
        "You are a Meta-Reviewer. Evaluate the review output for thoroughness, accuracy of "
        "issues found, appropriate severity classification, and actionable feedback."
    ),
    "testing": (
        "You are a Testing Reviewer. Evaluate the test output for coverage adequacy, "
        "meaningful assertions, edge case coverage, and correct pass/fail classification."
    ),
}

_ROUND_PROMPTS = {
    0: (
        "Review the output below. Provide your INDEPENDENT assessment — do not speculate "
        "about what other reviewers might say. Be specific and cite concrete issues.\n\n"
        "Output:\n{output}\n\n"
        "Respond with PASS or FAIL followed by your detailed reasoning. "
        "List specific strengths and weaknesses."
    ),
    1: (
        "You previously reviewed this output. Below are the other reviewers' assessments.\n\n"
        "Other reviewers:\n{other_responses}\n\n"
        "You MAY revise your assessment based on new information, or you MAY maintain your "
        "original position. If you disagree with another reviewer, explain why.\n\n"
        "Original output:\n{output}\n\n"
        "Respond with PASS or FAIL followed by your reasoning. "
        "If changing your verdict, explain what changed your mind."
    ),
    2: (
        "This is your FINAL assessment. You have seen all other perspectives.\n\n"
        "Previous round responses:\n{other_responses}\n\n"
        "Output:\n{output}\n\n"
        "Provide your definitive PASS or FAIL verdict. This is final — "
        "no further deliberation will occur."
    ),
}

_AGENT_TIMEOUT_S = 30
_MAX_RETRIES_PER_AGENT = 2
_RETRY_BACKOFF_BASE_S = 1.0
_MIN_ROUNDS_FOR_COLLAPSE = 2


def _agent_roles_for_phase(phase: str) -> list[DebateAgentRole]:
    mapping: dict[str, list[DebateAgentRole]] = {
        "Specs": [DebateAgentRole.SPECS, DebateAgentRole.PLANNING],
        "Planning": [DebateAgentRole.PLANNING, DebateAgentRole.CODING, DebateAgentRole.SPECS],
        "Coding": [DebateAgentRole.CODING, DebateAgentRole.REVIEW, DebateAgentRole.TESTING],
        "Review": [DebateAgentRole.REVIEW, DebateAgentRole.CODING, DebateAgentRole.TESTING],
        "Testing": [DebateAgentRole.TESTING, DebateAgentRole.CODING, DebateAgentRole.REVIEW],
    }
    return mapping.get(phase, [DebateAgentRole.REVIEW])


class DebateRuntime:
    """Orchestration-only. Manages 3-round debate protocol, agent calls, partial completion.

    Does NOT contain consensus logic (delegates to ConsensusEngine).
    Does NOT access filesystem or external state (except LLM via httpx).
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen3:8b",
        max_tokens: int = 1024,
        tracer: Tracer | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._consensus = ConsensusEngine(provider=provider, model=model)
        self._tracer = tracer

    async def run_debate(
        self,
        task: Task,
        phase: str,
        output: str,
        budget: BudgetPolicy | None = None,
    ) -> DebateTranscript:
        b = budget or task.budget
        max_rounds = min(b.max_debate_rounds, 3)
        if max_rounds <= 0:
            return self._skip_transcript(task, phase, output, "Debate disabled by budget policy")

        agent_roles = _agent_roles_for_phase(phase)
        if not agent_roles:
            return self._skip_transcript(
                task, phase, output, "No debate agents configured for this phase",
            )

        agent_configs = [
            DebateAgentConfig(
                role=role,
                model=self._model,
                system_prompt=_DEBATE_SYSTEM_PROMPTS.get(role.value, ""),
                temperature=0.7,
                max_tokens=self._max_tokens,
            )
            for role in agent_roles
        ]

        transcript = DebateTranscript(
            task_id=task.task_id,
            phase=phase,
            output_preview=output[:200],
        )

        all_round_responses: list[dict[str, str]] = []

        for round_num in range(max_rounds):
            debate_round = DebateRound(
                round_number=round_num,
                started_at=datetime.now(UTC).isoformat(),
            )

            if round_num > 0 and all_round_responses:
                debate_round.previous_responses = dict(all_round_responses[-1])

            for agent_cfg in agent_configs:
                response = await self._call_agent_with_retry(
                    agent_cfg, phase, output, round_num,
                    debate_round.previous_responses if round_num > 0 else {},
                )
                debate_round.responses[agent_cfg.role.value] = response

            debate_round.completed_at = datetime.now(UTC).isoformat()
            transcript.rounds.append(debate_round)
            all_round_responses.append(dict(debate_round.responses))

            consensus = await self._consensus.evaluate(
                responses=debate_round.responses,
                task=task,
                phase=phase,
                round_number=round_num,
                max_rounds=max_rounds,
            )
            consensus.round_count = round_num + 1
            consensus.minority_reports = self._build_minority_reports(
                all_round_responses,
                consensus,
            )
            consensus.residual_objections = self._consensus.extract_residual_objections(
                all_round_responses,
            )
            consensus.collapse_signal = self._detect_collapse_multi_round(all_round_responses)
            transcript.consensus = consensus

            if consensus.reached and not consensus.collapse_signal.detected:
                log.info(
                    "Consensus reached round %d (passed=%s, collapse=%s)",
                    round_num, consensus.passed, consensus.collapse_signal.detected,
                )
                break

            if consensus.collapse_signal.detected and round_num == max_rounds - 1:
                log.warning("Sycophantic collapse detected — forcing consensus with warning")

        if transcript.consensus is None:
            transcript.consensus = ConsensusResult(
                reached=False, passed=False,
                reason="No consensus after all rounds",
                round_count=max_rounds,
            )

        transcript.total_tokens_estimate = self._estimate_tokens(transcript)

        if self._tracer:
            trace_id = self._tracer.create_trace_id()
            await self._tracer.record_span(
                trace_id,
                phase=phase,
                tool="sdlc_debate_output",
                task_id=task.task_id,
                metadata={
                    "rounds": len(transcript.rounds),
                    "consensus_reached": transcript.consensus.reached,
                    "consensus_passed": transcript.consensus.passed,
                    "collapse_detected": transcript.consensus.collapse_signal.detected,
                    "minority_reports": len(transcript.consensus.minority_reports),
                    "residual_objections": len(transcript.consensus.residual_objections),
                },
            )

        return transcript

    async def _call_agent_with_retry(
        self,
        agent_cfg: DebateAgentConfig,
        phase: str,
        output: str,
        round_num: int,
        previous_responses: dict[str, str],
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES_PER_AGENT + 1):
            try:
                return await asyncio.wait_for(
                    self._call_agent(agent_cfg, phase, output, round_num, previous_responses),
                    timeout=_AGENT_TIMEOUT_S,
                )
            except (TimeoutError, OSError, DebateError, RuntimeError) as e:
                last_error = e
                log.warning(
                    "Agent %s attempt %d failed: %s",
                    agent_cfg.role.value, attempt + 1, e,
                )
                if attempt < _MAX_RETRIES_PER_AGENT:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE_S * (2 ** attempt))
        return f"ERROR after {_MAX_RETRIES_PER_AGENT + 1} attempts: {last_error}"

    async def _call_agent(
        self,
        agent_cfg: DebateAgentConfig,
        _phase: str,
        output: str,
        round_num: int,
        previous_responses: dict[str, str],
    ) -> str:
        round_num = min(round_num, 2)
        round_prompt = _ROUND_PROMPTS[round_num]

        if round_num == 0:
            user_content = round_prompt.format(output=output)
        else:
            other_lines = [
                f"--- {role} ---\n{resp[:500]}"
                for role, resp in previous_responses.items()
                if role != agent_cfg.role.value
            ]
            other_text = "\n\n".join(other_lines) if other_lines else "No other responses."

            user_content = round_prompt.format(
                other_responses=other_text,
                output=output,
            )

        messages = [
            {
                "role": "system",
                "content": (
                    agent_cfg.system_prompt
                    or f"You are a {agent_cfg.role.value} reviewer."
                ),
            },
            {"role": "user", "content": user_content},
        ]

        return await self._provider.generate(
            messages=messages,
            model=agent_cfg.model,
            temperature=agent_cfg.temperature,
            max_tokens=agent_cfg.max_tokens,
        )

    def _build_minority_reports(
        self,
        all_rounds: list[dict[str, str]],
        consensus: ConsensusResult,
    ) -> list[MinorityReport]:
        if consensus.minority_reports:
            return consensus.minority_reports
        if not all_rounds:
            return []
        latest = all_rounds[-1]
        return self._consensus.extract_minority_reports(latest, consensus.agent_verdicts)

    def _detect_collapse_multi_round(
        self,
        all_rounds: list[dict[str, str]],
    ) -> CollapseSignal:
        if len(all_rounds) < _MIN_ROUNDS_FOR_COLLAPSE:
            return CollapseSignal()

        signals = [self._consensus.detect_collapse(r) for r in all_rounds]
        detected = [s for s in signals if s.detected]
        if detected:
            worst = max(detected, key=lambda s: s.confidence)
            return CollapseSignal(
                detected=True,
                confidence=worst.confidence,
                reason=(
                    f"Collapse detected in {len(detected)}/{len(signals)} rounds: "
                    f"{worst.reason}"
                ),
            )
        return CollapseSignal()

    @staticmethod
    def _skip_transcript(
        task: Task,
        phase: str,
        output: str,
        reason: str,
    ) -> DebateTranscript:
        return DebateTranscript(
            task_id=task.task_id,
            phase=phase,
            output_preview=output[:100],
            consensus=ConsensusResult(reached=True, passed=True, reason=reason),
        )

    def _estimate_tokens(self, transcript: DebateTranscript) -> int:
        total = 0
        for r in transcript.rounds:
            for resp in r.responses.values():
                total += len(resp.split())
        return total * 2
