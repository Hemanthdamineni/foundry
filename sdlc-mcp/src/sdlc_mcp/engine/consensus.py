"""ConsensusEngine — pure logic for multi-agent consensus, minority reports, collapse detection."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sdlc_mcp.adapters.llm import LLMProvider
from sdlc_mcp.exceptions import DebateError
from sdlc_mcp.models import CollapseSignal, ConsensusResult, MinorityReport

if TYPE_CHECKING:
    from sdlc_mcp.models import Task

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
        "disagreement_areas": {"type": "array", "items": {"type": "string"}},
        "agent_verdicts": {
            "type": "object",
            "additionalProperties": {"type": "boolean"},
        },
        "minority_positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "position": {"type": "string"},
                    "severity": {"type": "string"},
                },
            },
        },
        "sycophancy_risk": {"type": "string"},
    },
    "required": ["passed", "reason"],
}

_MAX_RESPONSE_PREVIEW_CHARS = 500
_MINORITY_PREVIEW_CHARS = 300
_MIN_ROUNDS_FOR_COMPARISON = 2
_COLLAPSE_KEYWORDS = [
    "i agree", "i concur", "same here", "as previously stated",
    "ditto", "echo", "second that", "nothing to add",
    "no further comments", "i have no objections",
]
_COLLAPSE_THRESHOLD = 0.6
_RESIDUAL_CONCERN_WORDS = frozenset(["issue", "problem", "concern", "bug", "fail"])
_RESIDUAL_PERSIST_WORDS = frozenset(["still", "remains", "not addressed", "persists"])
_CONSENSUS_SYSTEM_PROMPT = """You are a neutral consensus judge evaluating a multi-agent debate.

Each agent independently reviewed the '{phase}' phase output.
Analyze their responses for:

1. GENUINE CONSENSUS — agents independently reached the same conclusion with distinct reasoning
2. SYCOPHANTIC COLLAPSE — agents are agreeing without substance
   (e.g. "I agree", "same here", no new reasoning)
3. MINORITY POSITIONS — dissenting views with valid reasoning that should be preserved
4. RESIDUAL OBJECTIONS — concerns raised but not fully addressed

Return JSON:
- "passed" (bool): output passes collective review
- "reason" (str): detailed analysis
- "disagreement_areas" (array): specific issues agents disagree on
- "agent_verdicts" (dict): mapping of agent_role -> passed bool
- "minority_positions" (array): {{agent, position, severity}} for each dissenter
- "sycophancy_risk" (str): "none" | "low" | "medium" | "high"
"""


class ConsensusEngine:
    """Pure consensus logic. No orchestration, no I/O except LLM calls.

    Responsibilities:
    - Determine if consensus is reached
    - Extract minority reports
    - Detect sycophantic collapse
    - Track residual objections
    - Fall back to majority vote when LLM unavailable
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen3:8b",
    ) -> None:
        self._provider = provider
        self._model = model

    async def evaluate(
        self,
        responses: dict[str, str],
        task: Task,  # noqa: ARG002 - reserved for task-aware consensus prompts.
        phase: str,
        round_number: int,
        max_rounds: int,
    ) -> ConsensusResult:
        if not responses:
            return ConsensusResult(
                reached=True,
                passed=True,
                reason="No agents participated — defaulting to pass",
                round_count=round_number,
            )
        try:
            return await self._llm_consensus(responses, phase)
        except (DebateError, json.JSONDecodeError, OSError, RuntimeError):
            return self._majority_consensus(responses, round_number, max_rounds)

    def extract_minority_reports(
        self,
        responses: dict[str, str],
        agent_verdicts: dict[str, bool],
    ) -> list[MinorityReport]:
        reports: list[MinorityReport] = []
        for role, response in responses.items():
            if not agent_verdicts.get(role, True):
                preview = (
                    response[:_MINORITY_PREVIEW_CHARS]
                    if len(response) > _MINORITY_PREVIEW_CHARS
                    else response
                )
                reports.append(
                    MinorityReport(
                        agent_role=role,
                        objection=preview,
                        round_number=0,
                        severity="warning",
                    ),
                )
        return reports

    def detect_collapse(self, responses: dict[str, str]) -> CollapseSignal:
        if len(responses) < _MIN_ROUNDS_FOR_COMPARISON:
            return CollapseSignal()

        match_count = 0
        for response in responses.values():
            lower = response.lower()
            for kw in _COLLAPSE_KEYWORDS:
                if kw in lower:
                    match_count += 1
                    break

        ratio = match_count / max(len(responses), 1)
        if ratio >= _COLLAPSE_THRESHOLD:
            return CollapseSignal(
                detected=True,
                confidence=ratio,
                reason=f"{match_count}/{len(responses)} agents show sycophantic patterns",
            )
        return CollapseSignal()

    def extract_residual_objections(
        self,
        all_rounds: list[dict[str, str]],
    ) -> list[str]:
        if len(all_rounds) < _MIN_ROUNDS_FOR_COMPARISON:
            return []
        first = all_rounds[0]
        last = all_rounds[-1]

        objections: list[str] = []
        for role in first:
            first_lower = first.get(role, "").lower()
            last_lower = last.get(role, "").lower()
            has_issue_first = any(w in first_lower for w in _RESIDUAL_CONCERN_WORDS)
            still_present = any(w in last_lower for w in _RESIDUAL_PERSIST_WORDS)
            if has_issue_first and still_present:
                preview = last.get(role, "")[:200]
                objections.append(f"({role}) {preview}")
        return objections

    @staticmethod
    def _preview(text: str, max_chars: int = _MAX_RESPONSE_PREVIEW_CHARS) -> str:
        return text[:max_chars] if len(text) > max_chars else text

    async def _llm_consensus(
        self,
        responses: dict[str, str],
        phase: str,
    ) -> ConsensusResult:
        agent_lines = [
            f"--- {role} ---\n{self._preview(response)}\n"
            for role, response in responses.items()
        ]

        prompt = (
            _CONSENSUS_SYSTEM_PROMPT.replace("{phase}", phase)
            + "\n\nAgent Responses:\n"
            + "".join(agent_lines)
        )

        content = await self._provider.generate(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            temperature=0.0,
            response_format=_VERDICT_SCHEMA,
        )

        if not content.strip():
            return ConsensusResult(
                reached=False, passed=False,
                reason="Consensus judge returned empty response",
            )

        data = json.loads(content)
        minority_reports = [
            MinorityReport(
                agent_role=str(m.get("agent", "")),
                objection=str(m.get("position", "")),
                round_number=0,
                severity=str(m.get("severity", "info")),
            )
            for m in data.get("minority_positions", []) if isinstance(m, dict)
        ]

        sycophancy_raw = str(data.get("sycophancy_risk", "none"))
        confidence_map = {"high": 0.8, "medium": 0.4}
        collapse = CollapseSignal(
            detected=sycophancy_raw in ("medium", "high"),
            confidence=confidence_map.get(sycophancy_raw, 0.0),
            reason=f"Sycophancy risk: {sycophancy_raw}",
        )

        return ConsensusResult(
            reached=True,
            passed=bool(data.get("passed", False)),
            reason=str(data.get("reason", "")),
            disagreement_areas=[str(a) for a in data.get("disagreement_areas", [])],
            agent_verdicts={
                str(k): bool(v) for k, v in data.get("agent_verdicts", {}).items()
            },
            minority_reports=minority_reports,
            collapse_signal=collapse,
        )

    @staticmethod
    def _extract_verdict_from_text(text: str) -> bool | None:
        tokens = {
            token.strip(".,:;!?()[]{}'\"-").lower()
            for token in text.split()
        }
        has_pass = "pass" in tokens
        has_fail = "fail" in tokens
        if has_pass and not has_fail:
            return True
        if has_fail and not has_pass:
            return False
        return None

    def _majority_consensus(
        self,
        responses: dict[str, str],
        round_number: int,
        max_rounds: int,
    ) -> ConsensusResult:
        agent_verdicts: dict[str, bool] = {}
        for role, response in responses.items():
            verdict = self._extract_verdict_from_text(response)
            agent_verdicts[role] = True if verdict is None else verdict

        passed_votes = sum(1 for v in agent_verdicts.values() if v)
        total = len(agent_verdicts) or 1
        majority_passed = passed_votes > total / 2
        stalemate = round_number >= max_rounds - 1 and not majority_passed

        minority_reports = self.extract_minority_reports(responses, agent_verdicts)
        collapse = self.detect_collapse(responses)

        return ConsensusResult(
            reached=not stalemate,
            passed=majority_passed,
            reason=(
                f"Majority vote: {passed_votes}/{total} passed"
                if not stalemate
                else "Stalemate — no consensus after maximum rounds"
            ),
            round_count=round_number,
            agent_verdicts=agent_verdicts,
            minority_reports=minority_reports,
            collapse_signal=collapse,
        )
