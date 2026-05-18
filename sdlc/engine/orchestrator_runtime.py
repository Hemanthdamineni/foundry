"""Orchestrator authority engine — centralized execution governance.

TODO #8: No component may advance phases without orchestrator approval.
Explicit authority boundaries, deterministic governance, centralized control.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.orchestrator_runtime")


class AuthorityRequest(BaseModel):
    """A request for orchestrator authority."""

    request_type: str  # phase_transition, debate_continue, retry, replan, recovery, rollback, budget
    requester: str
    phase: str = ""
    target_phase: str = ""
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorityDecision(BaseModel):
    """Orchestrator's authority decision."""

    request_type: str
    approved: bool
    reason: str
    conditions: list[str] = Field(default_factory=list)


class OrchestratorAuthority:
    """Centralized authority engine — all phase transitions must go through here.

    Prevents: rogue agents, uncontrolled loops, hidden phase transitions.
    """

    def __init__(self) -> None:
        self._rules: dict[str, Any] = {}
        self._blocked_transitions: set[tuple[str, str]] = set()
        self._max_retries: dict[str, int] = {}
        self._retry_counts: dict[str, int] = {}
        self._decision_log: list[AuthorityDecision] = []
        self._budget_exhausted: set[str] = set()

    def block_transition(self, from_phase: str, to_phase: str) -> None:
        """Explicitly block a phase transition."""
        self._blocked_transitions.add((from_phase, to_phase))

    def set_max_retries(self, phase: str, max_retries: int) -> None:
        self._max_retries[phase] = max_retries

    def mark_budget_exhausted(self, task_id: str) -> None:
        self._budget_exhausted.add(task_id)

    def request_authority(self, request: AuthorityRequest) -> AuthorityDecision:
        """Process an authority request — the single decision point."""
        handler = {
            "phase_transition": self._decide_phase_transition,
            "debate_continue": self._decide_debate_continue,
            "retry": self._decide_retry,
            "replan": self._decide_replan,
            "recovery": self._decide_recovery,
            "rollback": self._decide_rollback,
            "budget": self._decide_budget,
        }.get(request.request_type, self._decide_default)

        decision = handler(request)
        self._decision_log.append(decision)
        log_extra = {"type": request.request_type, "approved": decision.approved, "reason": decision.reason}
        if decision.approved:
            logger.info("Authority granted", extra=log_extra)
        else:
            logger.warning("Authority denied", extra=log_extra)
        return decision

    def _decide_phase_transition(self, req: AuthorityRequest) -> AuthorityDecision:
        key = (req.phase, req.target_phase)
        if key in self._blocked_transitions:
            return AuthorityDecision(
                request_type=req.request_type, approved=False,
                reason=f"Transition {req.phase} → {req.target_phase} is blocked",
            )
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason=f"Transition {req.phase} → {req.target_phase} approved",
        )

    def _decide_debate_continue(self, req: AuthorityRequest) -> AuthorityDecision:
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason="Debate continuation approved",
        )

    def _decide_retry(self, req: AuthorityRequest) -> AuthorityDecision:
        phase = req.phase
        count = self._retry_counts.get(phase, 0) + 1
        max_r = self._max_retries.get(phase, 3)
        self._retry_counts[phase] = count
        if count > max_r:
            return AuthorityDecision(
                request_type=req.request_type, approved=False,
                reason=f"Retry limit ({max_r}) exceeded for {phase}",
            )
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason=f"Retry {count}/{max_r} approved for {phase}",
        )

    def _decide_replan(self, req: AuthorityRequest) -> AuthorityDecision:
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason="Replanning approved",
            conditions=["preserve_stable_work"],
        )

    def _decide_recovery(self, req: AuthorityRequest) -> AuthorityDecision:
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason="Recovery approved",
            conditions=["restore_from_checkpoint", "validate_state"],
        )

    def _decide_rollback(self, req: AuthorityRequest) -> AuthorityDecision:
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason="Rollback approved",
            conditions=["never_corrupt_stable_phases"],
        )

    def _decide_budget(self, req: AuthorityRequest) -> AuthorityDecision:
        task_id = req.metadata.get("task_id", "")
        if task_id in self._budget_exhausted:
            return AuthorityDecision(
                request_type=req.request_type, approved=False,
                reason=f"Budget exhausted for task {task_id}",
            )
        return AuthorityDecision(
            request_type=req.request_type, approved=True,
            reason="Budget available",
        )

    def _decide_default(self, req: AuthorityRequest) -> AuthorityDecision:
        return AuthorityDecision(
            request_type=req.request_type, approved=False,
            reason=f"Unknown authority request type: {req.request_type}",
        )

    def reset_retries(self, phase: str) -> None:
        self._retry_counts.pop(phase, None)

    @property
    def decision_log(self) -> list[dict[str, Any]]:
        return [d.model_dump() for d in self._decision_log]
