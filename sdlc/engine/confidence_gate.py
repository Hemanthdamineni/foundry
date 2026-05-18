"""Confidence gating engine — runtime confidence enforcement for approvals.

TODO #6: Prevents decorative reviewers and meaningless approvals via
confidence normalization, threshold enforcement, and drift detection.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.confidence_gate")


class ConfidenceVote(BaseModel):
    """A single confidence vote from a reviewer or judge."""

    voter_id: str
    role: str  # reviewer, architect, security, tool
    approved: bool
    confidence: float  # 0.0 – 1.0
    reasoning: str = ""
    risks: list[str] = Field(default_factory=list)


class GateDecision(BaseModel):
    """The result of confidence gating."""

    approved: bool
    reason: str
    avg_confidence: float = 0.0
    min_confidence: float = 0.0
    unanimous: bool = False
    votes: list[ConfidenceVote] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    action: str = "approve"  # approve, continue_debate, synthesize, reject


# ── Role-based Confidence Bounds ─────────────────────────────────

DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "reviewer": (0.0, 1.0),
    "architect": (0.0, 1.0),
    "security": (0.0, 1.0),
    "tool": (0.0, 1.0),  # Tools should always be 0.0 or 1.0
}


class ConfidenceGate:
    """Runtime confidence gating for approval decisions.

    Rules:
    - Unanimous approval required
    - Average confidence must meet threshold
    - Low confidence triggers continued debate
    - Role-based confidence bounds enforced
    - Confidence drift detected across iterations
    """

    def __init__(
        self,
        threshold: float = 0.7,
        role_bounds: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._threshold = threshold
        self._role_bounds = role_bounds or dict(DEFAULT_BOUNDS)
        self._history: list[GateDecision] = []

    def evaluate(self, votes: list[ConfidenceVote]) -> GateDecision:
        """Evaluate a set of confidence votes and produce a gate decision."""
        if not votes:
            decision = GateDecision(
                approved=False,
                reason="No votes provided",
                action="reject",
            )
            self._history.append(decision)
            return decision

        # Normalize confidence to role bounds
        normalized = [self._normalize_vote(v) for v in votes]

        # Calculate metrics
        confidences = [v.confidence for v in normalized]
        avg_conf = sum(confidences) / len(confidences)
        min_conf = min(confidences)
        unanimous = all(v.approved for v in normalized)

        # Collect risks
        all_risks: list[str] = []
        for v in normalized:
            all_risks.extend(v.risks)

        # Gate logic
        if unanimous and avg_conf >= self._threshold:
            action = "approve"
            approved = True
            reason = f"Unanimous approval, avg confidence {avg_conf:.2f} >= {self._threshold}"
        elif not unanimous:
            # Check if it's a minor disagreement
            disapprovers = [v for v in normalized if not v.approved]
            if all(v.confidence < 0.3 for v in disapprovers):
                action = "synthesize"
                approved = False
                reason = f"Low-confidence disagreement from {len(disapprovers)} voters — synthesize"
            else:
                action = "continue_debate"
                approved = False
                reason = f"Non-unanimous: {len(disapprovers)} disapprovals"
        elif avg_conf < self._threshold:
            action = "continue_debate"
            approved = False
            reason = f"Avg confidence {avg_conf:.2f} below threshold {self._threshold}"
        else:
            action = "approve"
            approved = True
            reason = "Approved"

        decision = GateDecision(
            approved=approved,
            reason=reason,
            avg_confidence=round(avg_conf, 3),
            min_confidence=round(min_conf, 3),
            unanimous=unanimous,
            votes=normalized,
            unresolved_risks=list(set(all_risks)),
            action=action,
        )
        self._history.append(decision)
        return decision

    def detect_drift(self, window: int = 5) -> dict[str, Any]:
        """Detect confidence drift across recent decisions."""
        if len(self._history) < window:
            return {"drift_detected": False, "reason": "Insufficient history"}

        recent = self._history[-window:]
        older = self._history[-(window * 2):-window] if len(self._history) >= window * 2 else []

        recent_avg = sum(d.avg_confidence for d in recent) / len(recent)

        if older:
            older_avg = sum(d.avg_confidence for d in older) / len(older)
            drift = recent_avg - older_avg
            return {
                "drift_detected": abs(drift) > 0.15,
                "direction": "improving" if drift > 0 else "degrading",
                "drift_magnitude": round(abs(drift), 3),
                "recent_avg": round(recent_avg, 3),
                "older_avg": round(older_avg, 3),
            }

        return {
            "drift_detected": False,
            "recent_avg": round(recent_avg, 3),
        }

    def _normalize_vote(self, vote: ConfidenceVote) -> ConfidenceVote:
        """Normalize a vote's confidence to its role bounds."""
        bounds = self._role_bounds.get(vote.role, (0.0, 1.0))
        lo, hi = bounds
        clamped = max(lo, min(hi, vote.confidence))
        return ConfidenceVote(
            voter_id=vote.voter_id,
            role=vote.role,
            approved=vote.approved,
            confidence=clamped,
            reasoning=vote.reasoning,
            risks=vote.risks,
        )

    @property
    def history(self) -> list[GateDecision]:
        return list(self._history)
