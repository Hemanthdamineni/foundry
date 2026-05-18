"""Reviewer debate runtime — structured debate rounds with convergence detection.

TODO #5: Debates exist architecturally but not operationally. This provides
the actual structured debate flow: INDEPENDENT_REVIEW → CROSS_CRITIQUE →
SECRETARY_SUMMARY → CONFIDENCE_EMISSION → ORCHESTRATOR_DECISION.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.reviewer_debate")


class ReviewerAnalysis(BaseModel):
    """Independent analysis from a single reviewer."""

    reviewer_id: str
    role: str
    approved: bool
    confidence: float = 0.0
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CrossCritique(BaseModel):
    """A critique of another reviewer's analysis."""

    critic_id: str
    target_reviewer_id: str
    agrees: bool
    confidence_delta: float = 0.0
    objections: list[str] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)


class DebateRound(BaseModel):
    """A single debate round."""

    round_number: int
    analyses: list[ReviewerAnalysis] = Field(default_factory=list)
    critiques: list[CrossCritique] = Field(default_factory=list)
    summary: str = ""
    consensus_reached: bool = False
    avg_confidence: float = 0.0
    unresolved_risks: list[str] = Field(default_factory=list)


class DebateResult(BaseModel):
    """Final result of a reviewer debate."""

    phase: str = ""
    rounds: list[DebateRound] = Field(default_factory=list)
    final_approved: bool = False
    final_confidence: float = 0.0
    total_rounds: int = 0
    converged: bool = False
    convergence_reason: str = ""
    unresolved_risks: list[str] = Field(default_factory=list)
    repetition_detected: bool = False


class ReviewerDebate:
    """Structured reviewer debate runtime.

    Flow: INDEPENDENT_REVIEW → CROSS_CRITIQUE → SECRETARY_SUMMARY →
    CONFIDENCE_EMISSION → ORCHESTRATOR_DECISION.

    Properties:
    - No premature agreement
    - No hidden disagreement
    - Explicit unresolved risks
    - Repetition detection
    """

    def __init__(
        self,
        max_rounds: int = 4,
        convergence_threshold: float = 0.75,
    ) -> None:
        self._max_rounds = max_rounds
        self._convergence_threshold = convergence_threshold
        self._current_debate: DebateResult | None = None

    def start_debate(self, phase: str) -> DebateResult:
        """Start a new debate."""
        self._current_debate = DebateResult(phase=phase)
        return self._current_debate

    def add_round(
        self,
        analyses: list[ReviewerAnalysis],
        critiques: list[CrossCritique] | None = None,
    ) -> DebateRound:
        """Add a debate round with analyses and optional cross-critiques."""
        if self._current_debate is None:
            self._current_debate = DebateResult()

        round_num = len(self._current_debate.rounds) + 1
        confidences = [a.confidence for a in analyses]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Collect unresolved risks
        all_risks: list[str] = []
        for a in analyses:
            all_risks.extend(a.risks)

        # Check consensus
        all_approve = all(a.approved for a in analyses)
        consensus = all_approve and avg_conf >= self._convergence_threshold

        # Build summary
        approvals = sum(1 for a in analyses if a.approved)
        summary = (
            f"Round {round_num}: {approvals}/{len(analyses)} approved, "
            f"avg confidence {avg_conf:.2f}"
        )

        debate_round = DebateRound(
            round_number=round_num,
            analyses=analyses,
            critiques=critiques or [],
            summary=summary,
            consensus_reached=consensus,
            avg_confidence=avg_conf,
            unresolved_risks=list(set(all_risks)),
        )
        self._current_debate.rounds.append(debate_round)
        return debate_round

    def check_convergence(self) -> dict[str, Any]:
        """Check if the debate has converged."""
        if self._current_debate is None:
            return {"converged": False, "reason": "No active debate"}

        rounds = self._current_debate.rounds
        if not rounds:
            return {"converged": False, "reason": "No rounds"}

        latest = rounds[-1]

        # Check max rounds
        if len(rounds) >= self._max_rounds:
            return {
                "converged": True,
                "reason": f"Max rounds ({self._max_rounds}) reached",
                "forced": True,
            }

        # Check consensus
        if latest.consensus_reached:
            return {
                "converged": True,
                "reason": "Consensus reached",
                "forced": False,
            }

        # Check repetition
        if len(rounds) >= 2:
            prev = rounds[-2]
            if (
                abs(latest.avg_confidence - prev.avg_confidence) < 0.05
                and latest.consensus_reached == prev.consensus_reached
            ):
                return {
                    "converged": True,
                    "reason": "Repetition detected — no progress",
                    "repetition": True,
                }

        return {"converged": False, "reason": "Debate continues"}

    def finalize(self) -> DebateResult:
        """Finalize the debate and produce the result."""
        if self._current_debate is None:
            return DebateResult()

        debate = self._current_debate
        convergence = self.check_convergence()

        debate.total_rounds = len(debate.rounds)
        debate.converged = convergence.get("converged", False)
        debate.convergence_reason = convergence.get("reason", "")
        debate.repetition_detected = convergence.get("repetition", False)

        if debate.rounds:
            latest = debate.rounds[-1]
            debate.final_confidence = latest.avg_confidence
            debate.final_approved = latest.consensus_reached
            debate.unresolved_risks = latest.unresolved_risks

        self._current_debate = None
        return debate
