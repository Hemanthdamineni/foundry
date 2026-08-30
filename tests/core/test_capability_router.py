"""Tests for CapabilityRouter — role-based routing and adaptive rigor."""

from __future__ import annotations

import pytest

from foundry.core.capability_router import (
    Capability,
    CapabilityRouter,
    CapabilityRule,
    RigorLevel,
    RoutingDecision,
)
from foundry.core.workspace.manager import WorkspaceBoundaries


class TestCapabilityRouterBasic:
    def test_code_generation(self) -> None:
        router = CapabilityRouter()
        d = router.route("Implement a REST API with endpoints")
        assert Capability.CODE_GENERATION in d.capabilities
        assert d.rigor in (RigorLevel.STANDARD, RigorLevel.THOROUGH)

    def test_refactoring(self) -> None:
        router = CapabilityRouter()
        d = router.route("Refactor the authentication module to use JWT")
        assert Capability.REFACTORY in d.capabilities
        assert d.rigor == RigorLevel.THOROUGH

    def test_debugging(self) -> None:
        router = CapabilityRouter()
        d = router.route("Fix the crash in the login flow")
        assert Capability.DEBUGGING in d.capabilities
        assert d.rigor == RigorLevel.THOROUGH

    def test_testing(self) -> None:
        router = CapabilityRouter()
        d = router.route("Add pytest tests for the calculator module")
        assert Capability.TESTING in d.capabilities

    def test_code_review(self) -> None:
        router = CapabilityRouter()
        d = router.route("Review the PR for security issues")
        assert Capability.CODE_REVIEW in d.capabilities

    def test_documentation(self) -> None:
        router = CapabilityRouter()
        d = router.route("Document the API endpoints in the README")
        assert Capability.DOCUMENTATION in d.capabilities
        assert d.rigor == RigorLevel.MINIMAL

    def test_debate(self) -> None:
        router = CapabilityRouter()
        d = router.route("Debate the tradeoffs of microservices vs monolith")
        assert Capability.DEBATE in d.capabilities


class TestCapabilityRouterRigor:
    def test_rigor_mapping(self) -> None:
        router = CapabilityRouter()
        # Simple task → minimal
        d_min = router.route("Add a comment to line 10")
        # Complex task → thorough/exhaustive
        d_max = router.route(
            "Refactor the entire authentication system, add tests, "
            "update documentation, and also migrate the database schema"
        )
        assert d_min.rigor.value <= d_max.rigor.value

    def test_rigor_to_params(self) -> None:
        router = CapabilityRouter()
        assert router._rigor_to_params(RigorLevel.MINIMAL) == (0, False)
        assert router._rigor_to_params(RigorLevel.STANDARD) == (2, False)
        assert router._rigor_to_params(RigorLevel.THOROUGH) == (3, True)
        assert router._rigor_to_params(RigorLevel.EXHAUSTIVE) == (5, True)


class TestCapabilityRouterCustomRules:
    def test_custom_rule_takes_precedence(self) -> None:
        custom = CapabilityRule(
            pattern=r"\bdeploy to prod\b",
            capabilities=(Capability.DEPLOYMENT,),
            rigor=RigorLevel.MINIMAL,
            priority=100,
        )
        router = CapabilityRouter(custom_rules=[custom])
        d = router.route("Deploy to prod immediately")
        assert Capability.DEPLOYMENT in d.capabilities
        assert d.rigor == RigorLevel.MINIMAL

    def test_add_rule(self) -> None:
        router = CapabilityRouter()
        router.add_rule(CapabilityRule(
            pattern=r"\bmigrate database\b",
            capabilities=(Capability.DATA_PROCESSING,),
            rigor=RigorLevel.THOROUGH,
            priority=95,
        ))
        d = router.route("Migrate database to PostgreSQL")
        assert Capability.DATA_PROCESSING in d.capabilities


class TestCapabilityRouterWorkspace:
    def test_respects_denylist(self) -> None:
        router = CapabilityRouter()
        boundaries = WorkspaceBoundaries(denied_tools=("code_generation",))
        d = router.route("Implement a feature", workspace_boundaries=boundaries)
        # code_generation should be filtered out
        assert Capability.CODE_GENERATION not in d.capabilities

    def test_empty_capabilities_fallback(self) -> None:
        router = CapabilityRouter()
        # Deny all capabilities in the default code_generation rule
        boundaries = WorkspaceBoundaries(
            denied_tools=("code_generation", "architecture"),
        )
        d = router.route("Implement something", workspace_boundaries=boundaries)
        # When all capabilities are denied, we get empty caps with minimal rigor
        assert len(d.capabilities) == 0
        assert d.rigor == RigorLevel.MINIMAL


class TestConfidence:
    def test_high_confidence_for_specific_match(self) -> None:
        router = CapabilityRouter()
        d = router.route("Refactor the authentication module to use JWT tokens")
        assert d.confidence >= 0.5

    def test_no_match_fallback_confidence(self) -> None:
        router = CapabilityRouter()
        d = router.route("do something vague")
        assert d.confidence <= 0.5


class TestGetRigorForComplexity:
    def test_simple_task(self) -> None:
        router = CapabilityRouter()
        assert router.get_rigor_for_complexity("Add a comment") == RigorLevel.MINIMAL

    def test_complex_task(self) -> None:
        router = CapabilityRouter()
        rigor = router.get_rigor_for_complexity(
            "Refactor the authentication system and also migrate the database schema "
            "and add tests and update documentation for the module"
        )
        assert rigor in (RigorLevel.THOROUGH, RigorLevel.EXHAUSTIVE)
