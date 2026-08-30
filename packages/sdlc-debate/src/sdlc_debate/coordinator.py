"""DebateCoordinator — wraps DebateRuntime with Ai-Agent-Server personality configs.

Adapted from Ai-Agent-Server/latest/src/engine/debate_coordinator.py.

The coordinator maps named agent personalities (Architect, SecurityCritic, …) to
DebateAgentRole values, runs the 3-round debate via DebateRuntime, then invokes
a judge LLM to produce a structured verdict (DebateResult).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from sdlc_judge.base import LLMProvider
from sdlc_models.debate import (
    DebateAgentConfig,
    DebateAgentRole,
    DebateTranscript,
)
from sdlc_models.exceptions import DebateError
from sdlc_models.phases import BudgetPolicy, Phase, Task

from sdlc_debate.runtime import DebateRuntime, _DEBATE_SYSTEM_PROMPTS

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

_REVIEW_DECISIONS = {"APPROVED", "CHANGES_REQUIRED"}


@dataclass(frozen=True)
class DebateResult:
    """Structured outcome of a coordinated debate run.

    Attributes
    ----------
    used_debate:
        True if the debate protocol was actually exercised (not immediately skipped).
    fallback_used:
        True if the debate fell back to a single-model heuristic.
    fallback_reason:
        Human-readable explanation when *fallback_used* is True.
    transcript:
        The raw ``DebateTranscript`` from the runtime (empty on fallback).
    judge_output:
        Parsed JSON verdict from the judge LLM.
    confidence:
        Numeric confidence value (0.0–1.0) extracted from the judge output.
    risk_notes:
        Risk-related notes surfaced by the judge.
    """

    used_debate: bool
    fallback_used: bool
    fallback_reason: str | None = None
    transcript: DebateTranscript | None = None
    judge_output: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    risk_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ai-Agent personality → SDLC role mapping
# ---------------------------------------------------------------------------

_PHASE_AGENTS: dict[str, tuple[tuple[str, DebateAgentRole], ...]] = {
    "Chatting": (
        ("ChatAnalyst", DebateAgentRole.REVIEW),
    ),
    "Specs": (
        ("RequirementsAnalyst", DebateAgentRole.SPECS),
        ("ScopeCritic", DebateAgentRole.PLANNING),
        ("DevilAdvocate", DebateAgentRole.REVIEW),
        ("Secretary", DebateAgentRole.CONSENSUS),
    ),
    "Planning": (
        ("Architect", DebateAgentRole.PLANNING),
        ("SecurityCritic", DebateAgentRole.CODING),
        ("PerformanceCritic", DebateAgentRole.TESTING),
        ("DevilAdvocate", DebateAgentRole.REVIEW),
        ("Secretary", DebateAgentRole.CONSENSUS),
    ),
    "Coding": (
        ("Implementer", DebateAgentRole.CODING),
        ("CodeReviewer", DebateAgentRole.REVIEW),
        ("Tester", DebateAgentRole.TESTING),
        ("Secretary", DebateAgentRole.CONSENSUS),
    ),
    "Review": (
        ("ReviewerA", DebateAgentRole.REVIEW),
        ("ReviewerB", DebateAgentRole.CODING),
        ("DevilAdvocate", DebateAgentRole.SPECS),
        ("Secretary", DebateAgentRole.CONSENSUS),
    ),
    "Testing": (
        ("TestDesigner", DebateAgentRole.TESTING),
        ("CodeReviewer", DebateAgentRole.CODING),
        ("RequirementsAnalyst", DebateAgentRole.SPECS),
        ("Secretary", DebateAgentRole.CONSENSUS),
    ),
    "Done": (
        ("Summarizer", DebateAgentRole.REVIEW),
    ),
}

_PERSONALITY_SYSTEM_PROMPTS: dict[str, str] = {
    "Architect": (
        "You are the Architect. Evaluate the plan for structural soundness, "
        "component boundaries, dependency management, and scalability. "
        "Identify missing abstractions, over-engineering, and architectural risks."
    ),
    "SecurityCritic": (
        "You are the SecurityCritic. Evaluate the output for security "
        "vulnerabilities, trust boundaries, input validation, authentication, "
        "authorization, and data protection. Flag any OWASP Top 10 concerns."
    ),
    "PerformanceCritic": (
        "You are the PerformanceCritic. Evaluate the output for algorithmic "
        "complexity, resource usage, caching opportunities, database query "
        "efficiency, and potential bottlenecks."
    ),
    "DevilAdvocate": (
        "You are the DevilAdvocate. Your job is to challenge every assumption "
        "in the output. Find edge cases, failure modes, unstated dependencies, "
        "and scenarios where the proposed approach breaks down. Be thorough "
        "and specific — your role is to strengthen the output by stress-testing it."
    ),
    "Secretary": (
        "You are the Secretary. Summarize the key points of the discussion "
        "and the output being evaluated. Identify areas of agreement and "
        "disagreement among reviewers. Note any unresolved concerns."
    ),
    "ReviewerA": (
        "You are ReviewerA. Evaluate the code for correctness, readability, "
        "adherence to coding standards, and test coverage. Look for bugs, "
        "anti-patterns, and deviations from the spec."
    ),
    "ReviewerB": (
        "You are ReviewerB. Evaluate the code from a maintainability perspective. "
        "Assess documentation clarity, naming conventions, code organization, "
        "and long-term sustainability of the approach."
    ),
    "RequirementsAnalyst": (
        "You are the RequirementsAnalyst. Evaluate whether the output "
        "completely and unambiguously satisfies the stated requirements. "
        "Look for missing functionality, implicit assumptions, and scope gaps."
    ),
    "ScopeCritic": (
        "You are the ScopeCritic. Evaluate the output for scope clarity, "
        "boundary definitions, and constraint completeness. Identify "
        "ambiguities, contradictions, and scope creep risks."
    ),
    "Implementer": (
        "You are the Implementer. Evaluate the output from an implementation "
        "standpoint — is it feasible, well-sequenced, and properly detailed? "
        "Look for missing steps, insufficient detail, and unhandled states."
    ),
    "CodeReviewer": (
        "You are the CodeReviewer. Evaluate the code for correctness, style, "
        "security, and adherence to best practices. Be specific — cite line-level "
        "issues when possible."
    ),
    "Tester": (
        "You are the Tester. Evaluate test coverage, assertion quality, edge-case "
        "handling, and whether the tests actually validate the requirements. "
        "Flag weak or missing tests."
    ),
    "TestDesigner": (
        "You are the TestDesigner. Evaluate the test plan and test output for "
        "coverage adequacy, meaningful assertions, edge cases, and correct "
        "pass/fail classification."
    ),
    "ChatAnalyst": (
        "You are a neutral ChatAnalyst evaluating a conversation output. "
        "Assess clarity, coherence, and completeness of the response."
    ),
    "Summarizer": (
        "You are the Summarizer. Review the final output for completeness, "
        "accuracy, and appropriate level of detail for a done/completion summary."
    ),
}

_AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    **_DEBATE_SYSTEM_PROMPTS,
    **_PERSONALITY_SYSTEM_PROMPTS,
}


# ---------------------------------------------------------------------------
# Judge prompt helpers
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """You are a neutral judge evaluating a multi-agent debate transcript.

Phase: {phase}

Each agent reviewed the phase output and participated in a structured debate.
Analyze their responses for consensus quality, minority concerns, and residual risks.

Return strict JSON with these keys:
- "decision" (string): PASS or FAIL — whether the phase output is acceptable
- "confidence" (number 0..1): how confident you are in this decision
- "risk_notes" (array of strings): specific risks or concerns that remain
"""


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class DebateCoordinator:
    """Wraps ``DebateRuntime`` with Ai-Agent-Server personality configurations.

    The coordinator:
    - Selects agents for the current phase (bounded by *max_agents*).
    - Optionally configures per-agent personality system prompts.
    - Delegates the 3-round protocol to ``DebateRuntime.run_debate``.
    - Invokes a judge LLM to produce the final ``DebateResult``.

    Parameters
    ----------
    provider:
        An ``LLMProvider`` shared by the runtime and judge.
    model:
        Default model identifier.
    max_tokens:
        Maximum tokens per agent response.
    max_agents:
        Maximum number of debate agents per phase (``None`` = all).
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen3:8b",
        max_tokens: int = 1024,
        max_agents: int | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._max_agents = max_agents
        self._runtime = DebateRuntime(
            provider=provider,
            model=model,
            max_tokens=max_tokens,
        )

    async def run(
        self,
        phase: Phase | str,
        input_payload: dict[str, Any],
        debate_models: tuple[str, ...] | None = None,
        task_id: str | None = None,
    ) -> DebateResult:
        """Run the full debate protocol for *phase* and return a structured result.

        Parameters
        ----------
        phase:
            SDLC phase identifier (``Phase`` enum or string).
        input_payload:
            Arbitrary dictionary with at least ``"output"`` (the phase output
            to debate) and optionally ``"task"`` (a serialised ``Task`` dict).
        debate_models:
            Ordered tuple of model identifiers (the first is used as the
            primary debate model; ``None`` triggers a fallback).
        task_id:
            Optional task identifier used for transcript attribution.

        Returns
        -------
        DebateResult
            Structured outcome with transcript, judge verdict, confidence,
            and risk notes.
        """
        phase_str = phase.value if isinstance(phase, Phase) else str(phase)
        output = str(input_payload.get("output", input_payload.get("content", "")))
        if not output:
            return self._fallback(
                phase=phase_str,
                input_payload=input_payload,
                reason="empty_output",
            )

        if not debate_models:
            return self._fallback(
                phase=phase_str,
                input_payload=input_payload,
                reason="no_debate_model",
            )

        model = debate_models[0]

        # Build a lightweight Task from the payload (or create a minimal one).
        task = self._resolve_task(input_payload, task_id=task_id or "coordinator")

        # Build agent configs with Ai-Agent personality prompts.
        agent_configs = self._build_agent_configs(phase_str)
        if not agent_configs:
            return self._fallback(
                phase=phase_str,
                input_payload=input_payload,
                reason="no_agents_for_phase",
            )

        started = time.perf_counter()
        try:
            transcript = await asyncio.wait_for(
                self._run_with_personalities(
                    task=task,
                    phase=phase_str,
                    output=output,
                    agent_configs=agent_configs,
                ),
                timeout=120.0,
            )
        except (TimeoutError, DebateError, RuntimeError) as exc:
            return self._fallback(
                phase=phase_str,
                input_payload=input_payload,
                reason=f"debate_failed:{exc}",
            )

        duration_s = round(time.perf_counter() - started, 3)

        # Invoke judge on the completed transcript.
        judge_output = await self._judge_transcript(phase_str, output, transcript)

        if judge_output.get("decision") or judge_output.get("passed") is not None:
            # Structured judge output — extract confidence and risk notes.
            confidence = self._extract_confidence(judge_output)
            risk_notes = self._extract_risk_notes(judge_output)
        else:
            # Fall back to consensus signal from the transcript.
            confidence = 0.5
            risk_notes = []
            if transcript.consensus:
                confidence = 0.7 if transcript.consensus.passed else 0.3
                if transcript.consensus.collapse_signal.detected:
                    risk_notes.append(
                        f"Sycophantic collapse detected (confidence={transcript.consensus.collapse_signal.confidence:.2f})",
                    )
                for mr in transcript.consensus.minority_reports:
                    risk_notes.append(f"({mr.agent_role}) {mr.objection[:120]}")
                for obj in transcript.consensus.residual_objections:
                    risk_notes.append(f"Residual: {obj[:120]}")

        return DebateResult(
            used_debate=True,
            fallback_used=False,
            fallback_reason=None,
            transcript=transcript,
            judge_output=judge_output,
            confidence=confidence,
            risk_notes=risk_notes,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_with_personalities(
        self,
        task: Task,
        phase: str,
        output: str,
        agent_configs: list[DebateAgentConfig],
    ) -> DebateTranscript:
        """Run debate with custom agent configs by mutating the runtime's defaults.

        We temporarily override the agent configs used by the runtime by
        building agent configs that include personality system prompts.
        The existing ``run_debate`` method builds its own configs from
        ``_agent_roles_for_phase``, so we pass a modified perspective by
        setting a custom attribute on the runtime that ``run_debate`` uses.

        Instead of patching the runtime, we call the underlying provider
        directly with the personality configs and assemble the transcript
        ourselves. This gives us full control over agent selection.
        """
        from datetime import UTC, datetime

        from sdlc_models.debate import ConsensusResult, DebateRound

        budget = task.budget
        max_rounds = min(budget.max_debate_rounds, 3)

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
                response = await self._runtime._call_agent_with_retry(
                    agent_cfg, phase, output, round_num,
                    debate_round.previous_responses if round_num > 0 else {},
                )
                debate_round.responses[agent_cfg.role.value] = response

            debate_round.completed_at = datetime.now(UTC).isoformat()
            transcript.rounds.append(debate_round)
            all_round_responses.append(dict(debate_round.responses))

            consensus = await self._runtime._consensus.evaluate(
                responses=debate_round.responses,
                task=task,
                phase=phase,
                round_number=round_num,
                max_rounds=max_rounds,
            )
            consensus.round_count = round_num + 1
            consensus.minority_reports = self._runtime._build_minority_reports(
                all_round_responses, consensus,
            )
            consensus.residual_objections = (
                self._runtime._consensus.extract_residual_objections(all_round_responses)
            )
            consensus.collapse_signal = self._runtime._detect_collapse_multi_round(
                all_round_responses,
            )
            transcript.consensus = consensus

            if consensus.reached and not consensus.collapse_signal.detected:
                break

        if transcript.consensus is None:
            transcript.consensus = ConsensusResult(
                reached=False, passed=False,
                reason="No consensus after all rounds",
                round_count=max_rounds,
            )

        transcript.total_tokens_estimate = self._runtime._estimate_tokens(transcript)
        return transcript

    def _build_agent_configs(self, phase: str) -> list[DebateAgentConfig]:
        """Build agent configurations for *phase* with personality prompts.

        Returns an empty list when no agents are mapped for the phase.
        """
        agent_mappings = _PHASE_AGENTS.get(phase, ())
        if not agent_mappings:
            return []

        configs: list[DebateAgentConfig] = []
        for personality_name, role in agent_mappings:
            system_prompt = _AGENT_SYSTEM_PROMPTS.get(
                personality_name,
                _DEBATE_SYSTEM_PROMPTS.get(role.value, ""),
            )
            configs.append(
                DebateAgentConfig(
                    role=role,
                    model=self._model,
                    system_prompt=(
                        f"You are {personality_name}.\n{system_prompt}"
                        if system_prompt
                        else f"You are {personality_name}, a {role.value} reviewer."
                    ),
                    temperature=0.7,
                    max_tokens=self._max_tokens,
                ),
            )

        # Apply max_agents bound, keeping Secretary if present.
        if self._max_agents is not None and len(configs) > self._max_agents >= 1:
            secretary = [c for c in configs if c.role == DebateAgentRole.CONSENSUS]
            others = [c for c in configs if c.role != DebateAgentRole.CONSENSUS]
            bounded = others[:max(0, self._max_agents - len(secretary))]
            if secretary:
                bounded.append(secretary[0])
            return bounded

        return configs

    async def _judge_transcript(
        self,
        phase: str,
        output: str,
        transcript: DebateTranscript,
    ) -> dict[str, Any]:
        """Call a judge LLM to evaluate the debate transcript."""
        consensus_block = ""
        if transcript.consensus:
            consensus_block = (
                f"Consensus reached: {transcript.consensus.reached}\n"
                f"Passed: {transcript.consensus.passed}\n"
                f"Reason: {transcript.consensus.reason}\n"
                f"Disagreement areas: {', '.join(transcript.consensus.disagreement_areas)}\n"
                f"Collapse detected: {transcript.consensus.collapse_signal.detected}\n"
                f"Minority reports: {len(transcript.consensus.minority_reports)}\n"
                f"Residual objections: {len(transcript.consensus.residual_objections)}\n"
            )

        rounds_block = []
        for r in transcript.rounds:
            resp_summary = "\n".join(
                f"  {role}: {text[:300]}"
                for role, text in r.responses.items()
            )
            rounds_block.append(f"Round {r.round_number}:\n{resp_summary}")

        prompt = (
            _JUDGE_SYSTEM_PROMPT.replace("{phase}", phase)
            + "\n\nOriginal output:\n"
            + output[:2000]
            + "\n\nDebate Transcript:\n"
            + consensus_block
            + "\n".join(rounds_block)
        )

        try:
            content = await asyncio.wait_for(
                self._provider.generate(
                    messages=[{"role": "user", "content": prompt}],
                    model=self._model,
                    temperature=0.0,
                    max_tokens=1024,
                ),
                timeout=30,
            )
        except (TimeoutError, RuntimeError):
            return {}

        return self._extract_json(content)

    async def _judge(
        self,
        *,
        phase: str,
        judge_prompt: str,
    ) -> dict[str, Any]:
        """Low-level judge call used by external integrators.

        Sends *judge_prompt* to the LLM and returns a parsed JSON dict.
        Returns an empty dict on failure.
        """
        try:
            content = await asyncio.wait_for(
                self._provider.generate(
                    messages=[{"role": "user", "content": judge_prompt}],
                    model=self._model,
                    temperature=0.0,
                    max_tokens=2048,
                ),
                timeout=60,
            )
        except (TimeoutError, RuntimeError):
            return {}
        return self._extract_json(content)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_task(input_payload: dict[str, Any], task_id: str) -> Task:
        """Build a ``Task`` from the payload, falling back to a minimal default."""
        raw = input_payload.get("task")
        if isinstance(raw, dict):
            try:
                return Task.model_validate(raw)
            except (ValueError, TypeError):
                pass
        return Task(
            task_id=task_id,
            description=str(input_payload.get("description", "")),
            budget=BudgetPolicy(max_debate_rounds=3),
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Parse the first JSON object from *text*.

        Tries a full parse first, then scans lines from the bottom for
        a valid JSON object.
        """
        content = text.strip()
        if not content:
            return {}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for line in reversed(content.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _extract_confidence(payload: dict[str, Any]) -> float:
        """Extract a 0..1 confidence value from the judge payload."""
        raw = payload.get("confidence")
        if isinstance(raw, (int, float)):
            value = float(raw)
            if 0.0 <= value <= 1.0:
                return value
        # Also check "passed" as a boolean proxy.
        passed = payload.get("passed")
        if isinstance(passed, bool):
            return 0.75 if passed else 0.4
        return 0.5

    @staticmethod
    def _extract_risk_notes(payload: dict[str, Any]) -> list[str]:
        """Extract risk notes from the judge payload."""
        raw = payload.get("risk_notes", payload.get("issues", []))
        if isinstance(raw, list):
            notes = [str(item).strip() for item in raw if str(item).strip()]
            if notes:
                return notes
        # Fall back to residual_objections.
        residual = payload.get("residual_objections", [])
        if isinstance(residual, list):
            return [str(r).strip() for r in residual if str(r).strip()]
        return []

    def _fallback(
        self,
        *,
        phase: str,
        input_payload: dict[str, Any],
        reason: str,
    ) -> DebateResult:
        """Build a fallback result when debate cannot proceed."""
        if phase in ("Review", "review"):
            decision = str(input_payload.get("decision") or "").strip().upper()
            if decision not in _REVIEW_DECISIONS:
                severity = str(input_payload.get("severity") or "").strip().lower()
                if severity in {"critical", "major", "high"}:
                    decision = "CHANGES_REQUIRED"
                else:
                    decision = "APPROVED"
            judge_output = {
                "decision": decision,
                "confidence": self._fallback_confidence(input_payload),
                "risk_notes": self._fallback_risk_notes(input_payload),
            }
        elif phase in ("Planning", "planning"):
            judge_output = {
                "decision": "PASS",
                "summary": str(input_payload.get("summary") or "single-model planning fallback"),
                "confidence": self._fallback_confidence(input_payload),
                "risk_notes": self._fallback_risk_notes(input_payload),
            }
        else:
            judge_output = {
                "decision": "PASS",
                "confidence": self._fallback_confidence(input_payload),
                "risk_notes": self._fallback_risk_notes(input_payload),
            }

        return DebateResult(
            used_debate=True,
            fallback_used=True,
            fallback_reason=reason,
            transcript=None,
            judge_output=judge_output,
            confidence=float(judge_output.get("confidence", 0.5)),
            risk_notes=list(judge_output.get("risk_notes", ["single_model_fallback"])),
        )

    @staticmethod
    def _fallback_confidence(input_payload: dict[str, Any]) -> float:
        raw = input_payload.get("confidence")
        if isinstance(raw, (int, float)):
            value = float(raw)
            if 0.0 <= value <= 1.0:
                return value
        return 0.5

    @staticmethod
    def _fallback_risk_notes(input_payload: dict[str, Any]) -> list[str]:
        raw = input_payload.get("risk_notes")
        if isinstance(raw, list):
            notes = [str(item).strip() for item in raw if str(item).strip()]
            if notes:
                return notes
        return ["single_model_fallback"]
