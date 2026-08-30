"""Governance — wires CapabilityRouter + WorkspaceBoundaries into execution.

This module provides the integration layer between the governance system
(CapabilityRouter, WorkspaceBoundaries, Chronicle) and the execution
system (TurnEngine, auto_run). It determines:

1. Which capabilities a task needs (CapabilityRouter)
2. What rigor level to apply (adaptive rigor)
3. Whether the workspace allows the operation (boundaries)
4. Whether budget allows the operation (budget checks)
5. Whether concurrency limits allow the operation

Architecture reference:
    GV Governance — "Boundaries that can't be crossed"
    Adaptive Rigor — "Orchestration intensity scales with complexity"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from foundry.core.capability_router import CapabilityRouter, RigorLevel, RoutingDecision
from foundry.core.logging import get_logger
from foundry.core.workspace.manager import WorkspaceBoundaries

log = get_logger("foundry.governance")


# --------------------------------------------------------------------------- #
#  Governance decision
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of governance checks before executing a task."""

    allowed: bool  # Whether the task can proceed
    routing: RoutingDecision  # Capability routing result
    max_repairs: int  # From routing, capped by workspace limits
    use_debate: bool  # Whether to run debate review
    deny_reason: str | None = None  # If not allowed, why

    @property
    def rigor(self) -> RigorLevel:
        return self.routing.rigor


# --------------------------------------------------------------------------- #
#  Governance gate
# --------------------------------------------------------------------------- #


class GovernanceGate:
    """Pre-execution governance checks.

    Usage::

        gate = GovernanceGate(router=CapabilityRouter())
        decision = gate.check(
            prompt="Implement REST API",
            boundaries=WorkspaceBoundaries(max_budget=10.0),
            current_budget_spent=5.0,
            current_concurrent_tasks=2,
        )
        if decision.allowed:
            # Proceed with task execution
            ...
    """

    def __init__(self, router: CapabilityRouter | None = None) -> None:
        self._router = router or CapabilityRouter()

    def check(
        self,
        prompt: str,
        *,
        boundaries: WorkspaceBoundaries | None = None,
        current_budget_spent: float = 0.0,
        current_concurrent_tasks: int = 0,
    ) -> GovernanceDecision:
        """Run all governance checks and return a decision.

        Checks performed:
        1. Capability routing (which caps, what rigor)
        2. Tool allowlist/denylist
        3. Budget ceiling
        4. Concurrency ceiling
        5. Autonomy level
        """
        # 1. Route the task
        routing = self._router.route(prompt, workspace_boundaries=boundaries)

        if boundaries is None:
            # No workspace boundaries — allow everything with routing results
            return GovernanceDecision(
                allowed=True,
                routing=routing,
                max_repairs=routing.max_repairs,
                use_debate=routing.use_debate,
            )

        # 2. Check tool allowlist/denylist
        for cap in routing.capabilities:
            if not boundaries.tool_allowed(cap.value):
                log.warning(
                    "governance denied: capability %s not allowed in workspace",
                    cap.value,
                )
                return GovernanceDecision(
                    allowed=False,
                    routing=routing,
                    max_repairs=0,
                    use_debate=False,
                    deny_reason=f"Capability '{cap.value}' not allowed in workspace",
                )

        # If routing produced no capabilities (all denied), block the task
        if not routing.capabilities:
            log.warning("governance denied: no capabilities available for task")
            return GovernanceDecision(
                allowed=False,
                routing=routing,
                max_repairs=0,
                use_debate=False,
                deny_reason="No capabilities available (all denied by workspace)",
            )

        # 3. Check budget ceiling
        if boundaries.max_budget > 0 and current_budget_spent >= boundaries.max_budget:
            log.warning(
                "governance denied: budget exhausted (%.1f / %.1f)",
                current_budget_spent,
                boundaries.max_budget,
            )
            return GovernanceDecision(
                allowed=False,
                routing=routing,
                max_repairs=0,
                use_debate=False,
                deny_reason=f"Budget exhausted ({current_budget_spent:.1f} / {boundaries.max_budget:.1f})",
            )

        # 4. Check concurrency ceiling
        if current_concurrent_tasks >= boundaries.max_concurrent_tasks:
            log.warning(
                "governance denied: concurrency limit reached (%d / %d)",
                current_concurrent_tasks,
                boundaries.max_concurrent_tasks,
            )
            return GovernanceDecision(
                allowed=False,
                routing=routing,
                max_repairs=0,
                use_debate=False,
                deny_reason=f"Concurrency limit reached ({current_concurrent_tasks} / {boundaries.max_concurrent_tasks})",
            )

        # 5. Check autonomy level
        if boundaries.autonomy_level == "restricted":
            # Restricted mode: no debate, minimal repairs
            return GovernanceDecision(
                allowed=True,
                routing=routing,
                max_repairs=min(routing.max_repairs, 1),
                use_debate=False,
            )

        # All checks passed — apply workspace limits to routing result
        max_repairs = min(routing.max_repairs, boundaries.max_retry_per_task)

        return GovernanceDecision(
            allowed=True,
            routing=routing,
            max_repairs=max_repairs,
            use_debate=routing.use_debate,
        )
