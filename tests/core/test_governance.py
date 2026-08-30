"""Tests for GovernanceGate — pre-execution governance checks."""

from __future__ import annotations

import pytest

from foundry.core.capability_router import CapabilityRouter, RigorLevel
from foundry.core.governance import GovernanceDecision, GovernanceGate
from foundry.core.workspace.manager import WorkspaceBoundaries


class TestGovernanceGate:
    def test_no_boundaries_allows_all(self) -> None:
        gate = GovernanceGate()
        decision = gate.check("Implement REST API")
        assert decision.allowed is True
        assert decision.max_repairs > 0

    def test_tool_denylist_blocks(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(denied_tools=("code_generation",))
        decision = gate.check(
            "Implement a feature",
            boundaries=boundaries,
        )
        assert decision.allowed is False
        assert decision.deny_reason is not None
        assert "denied" in decision.deny_reason.lower() or "not allowed" in decision.deny_reason.lower()

    def test_budget_ceiling_blocks(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(max_budget=10.0)
        decision = gate.check(
            "Implement something",
            boundaries=boundaries,
            current_budget_spent=10.0,
        )
        assert decision.allowed is False
        assert "Budget exhausted" in decision.deny_reason

    def test_budget_under_limit_allows(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(max_budget=10.0)
        decision = gate.check(
            "Implement something",
            boundaries=boundaries,
            current_budget_spent=5.0,
        )
        assert decision.allowed is True

    def test_concurrency_limit_blocks(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(max_concurrent_tasks=2)
        decision = gate.check(
            "Implement something",
            boundaries=boundaries,
            current_concurrent_tasks=2,
        )
        assert decision.allowed is False
        assert "Concurrency limit" in decision.deny_reason

    def test_restricted_autonomy(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(autonomy_level="restricted")
        decision = gate.check(
            "Refactor the auth system",
            boundaries=boundaries,
        )
        assert decision.allowed is True
        assert decision.use_debate is False
        assert decision.max_repairs <= 1

    def test_retry_limit_capped(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(max_retry_per_task=1)
        decision = gate.check(
            "Refactor the auth system",  # Thorough rigor → 3 repairs
            boundaries=boundaries,
        )
        assert decision.allowed is True
        assert decision.max_repairs == 1  # Capped by workspace limit

    def test_governance_decision_properties(self) -> None:
        from foundry.core.capability_router import RoutingDecision, Capability
        routing = RoutingDecision(
            capabilities=(Capability.CODE_GENERATION,),
            rigor=RigorLevel.THOROUGH,
            max_repairs=3,
            use_debate=True,
            matched_rule=r"\b(implement)\b",
            confidence=0.8,
        )
        decision = GovernanceDecision(
            allowed=True,
            routing=routing,
            max_repairs=3,
            use_debate=True,
        )
        assert decision.rigor == RigorLevel.THOROUGH
        assert decision.allowed is True
