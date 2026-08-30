"""CapabilityRouter — role-based capability routing and adaptive rigor.

Implements the **Capability MoE (Mixture of Experts)** pattern from the
Helix architecture. Routes tasks to the appropriate capabilities based on:
- Task type and complexity
- Workspace boundaries (allowed/denied tools)
- Current system load and budget

Also implements **Adaptive Rigor** — orchestration intensity scales with
task complexity. Simple tasks get lightweight orchestration; complex tasks
get full debate + repair cycles.

Architecture reference:
    GV Governance — "Capability MoE — role-based routing"
    Adaptive Rigor — "Orchestration intensity scales with complexity"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.capability_router")


# --------------------------------------------------------------------------- #
#  Capability types
# --------------------------------------------------------------------------- #


class Capability(StrEnum):
    """Available system capabilities."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REFACTORY = "refactoring"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    ARCHITECTURE = "architecture"
    DATA_PROCESSING = "data_processing"
    DEPLOYMENT = "deployment"
    MEMORY = "memory"
    INDEXING = "indexing"
    DEBATE = "debate"


class RigorLevel(StrEnum):
    """Orchestration intensity levels."""

    MINIMAL = "minimal"      # Single pass, no review
    STANDARD = "standard"    # Agent loop (planner → executor → verifier)
    THOROUGH = "thorough"    # Agent loop + debate review
    EXHAUSTIVE = "exhaustive"  # Agent loop + debate + multiple repair rounds


# --------------------------------------------------------------------------- #
#  Capability mapping rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CapabilityRule:
    """A rule that maps task patterns to capabilities and rigor levels."""

    pattern: str  # Regex pattern to match against task prompt
    capabilities: tuple[Capability, ...]  # Capabilities needed
    rigor: RigorLevel  # Orchestration intensity
    priority: int = 0  # Higher = checked first

    def matches(self, prompt: str) -> bool:
        return bool(re.search(self.pattern, prompt, re.IGNORECASE))


# Default rules — ordered by priority (highest first)
_DEFAULT_RULES: list[CapabilityRule] = [
    CapabilityRule(
        pattern=r"\b(refactor|reorganize|restructure|clean up|technical debt)\b",
        capabilities=(Capability.REFACTORY, Capability.ARCHITECTURE),
        rigor=RigorLevel.THOROUGH,
        priority=90,
    ),
    CapabilityRule(
        pattern=r"\b(review|audit|check|verify|validate|lint)\b",
        capabilities=(Capability.CODE_REVIEW,),
        rigor=RigorLevel.STANDARD,
        priority=80,
    ),
    CapabilityRule(
        pattern=r"\b(test|spec|assert|pytest|unittest|coverage)\b",
        capabilities=(Capability.TESTING,),
        rigor=RigorLevel.STANDARD,
        priority=70,
    ),
    CapabilityRule(
        pattern=r"\b(bug|fix|error|crash|fail|broken|debug)\b",
        capabilities=(Capability.DEBUGGING, Capability.CODE_GENERATION),
        rigor=RigorLevel.THOROUGH,
        priority=85,
    ),
    CapabilityRule(
        pattern=r"\b(deploy|release|ship|CI|CD|pipeline|docker)\b",
        capabilities=(Capability.DEPLOYMENT,),
        rigor=RigorLevel.MINIMAL,
        priority=60,
    ),
    CapabilityRule(
        pattern=r"\b(doc|document|readme|comment|docstring|explain)\b",
        capabilities=(Capability.DOCUMENTATION,),
        rigor=RigorLevel.MINIMAL,
        priority=50,
    ),
    CapabilityRule(
        pattern=r"\b(implement|build|create|write|add|feature|develop)\b",
        capabilities=(Capability.CODE_GENERATION,),
        rigor=RigorLevel.STANDARD,
        priority=40,
    ),
    CapabilityRule(
        pattern=r"\b(index|search|query|graph|dependency)\b",
        capabilities=(Capability.INDEXING,),
        rigor=RigorLevel.MINIMAL,
        priority=30,
    ),
    CapabilityRule(
        pattern=r"\b(memory|remember|recall|engram)\b",
        capabilities=(Capability.MEMORY,),
        rigor=RigorLevel.MINIMAL,
        priority=30,
    ),
    CapabilityRule(
        pattern=r"\b(debate|discuss|argue|consensus|agree|disagree)\b",
        capabilities=(Capability.DEBATE,),
        rigor=RigorLevel.THOROUGH,
        priority=85,
    ),
]


# --------------------------------------------------------------------------- #
#  CapabilityRouter
# --------------------------------------------------------------------------- #


@dataclass
class RoutingDecision:
    """Result of routing a task to appropriate capabilities."""

    capabilities: tuple[Capability, ...]
    rigor: RigorLevel
    max_repairs: int
    use_debate: bool
    matched_rule: str | None  # Pattern that matched
    confidence: float  # 0.0–1.0


class CapabilityRouter:
    """Routes tasks to capabilities based on content analysis.

    Usage::

        router = CapabilityRouter()
        decision = router.route("Implement a REST API with tests")
        # decision.capabilities = (Capability.CODE_GENERATION,)
        # decision.rigor = RigorLevel.STANDARD
    """

    def __init__(self, custom_rules: list[CapabilityRule] | None = None) -> None:
        self._rules = sorted(
            custom_rules or _DEFAULT_RULES,
            key=lambda r: r.priority,
            reverse=True,
        )

    def route(self, prompt: str, *, workspace_boundaries: Any = None) -> RoutingDecision:
        """Route a task prompt to the appropriate capabilities and rigor level.

        Args:
            prompt: The task description/prompt to route.
            workspace_boundaries: Optional WorkspaceBoundaries to check tool permissions.

        Returns:
            RoutingDecision with capabilities, rigor, and confidence.
        """
        prompt_lower = prompt.strip().lower()

        # Match against rules (highest priority first)
        for rule in self._rules:
            if rule.matches(prompt_lower):
                # Filter capabilities by workspace boundaries if provided
                caps = rule.capabilities
                rigor = rule.rigor
                if workspace_boundaries is not None:
                    filtered = tuple(
                        c for c in caps
                        if workspace_boundaries.tool_allowed(c.value)
                    )
                    if not filtered:
                        # No allowed capabilities — fallback to minimal
                        # but still respect denylist
                        fallback = Capability.CODE_GENERATION
                        if not workspace_boundaries.tool_allowed(fallback.value):
                            # Even the fallback is denied — return empty with minimal rigor
                            caps = ()
                            rigor = RigorLevel.MINIMAL
                        else:
                            caps = (fallback,)
                            rigor = RigorLevel.MINIMAL
                    else:
                        caps = filtered

                # Determine max repairs and debate usage based on rigor
                max_repairs, use_debate = self._rigor_to_params(rigor)

                # Estimate confidence from pattern specificity
                confidence = self._estimate_confidence(prompt_lower, rule)

                return RoutingDecision(
                    capabilities=caps,
                    rigor=rigor,
                    max_repairs=max_repairs,
                    use_debate=use_debate,
                    matched_rule=rule.pattern,
                    confidence=confidence,
                )

        # No rule matched — use defaults
        return RoutingDecision(
            capabilities=(Capability.CODE_GENERATION,),
            rigor=RigorLevel.STANDARD,
            max_repairs=2,
            use_debate=False,
            matched_rule=None,
            confidence=0.3,
        )

    def _rigor_to_params(self, rigor: RigorLevel) -> tuple[int, bool]:
        """Map rigor level to max_repairs and use_debate."""
        return {
            RigorLevel.MINIMAL: (0, False),
            RigorLevel.STANDARD: (2, False),
            RigorLevel.THOROUGH: (3, True),
            RigorLevel.EXHAUSTIVE: (5, True),
        }[rigor]

    def _estimate_confidence(self, prompt: str, rule: CapabilityRule) -> float:
        """Estimate routing confidence based on pattern match quality."""
        match = re.search(rule.pattern, prompt, re.IGNORECASE)
        if not match:
            return 0.0

        # Longer matches in the prompt = higher confidence
        match_len = match.end() - match.start()
        prompt_len = max(len(prompt), 1)
        match_ratio = match_len / prompt_len

        # Base confidence from match quality
        base = 0.5 + (match_ratio * 0.3)

        # Boost for higher-priority rules
        priority_boost = rule.priority / 100.0 * 0.2

        return min(1.0, base + priority_boost)

    def add_rule(self, rule: CapabilityRule) -> None:
        """Add a custom routing rule."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def get_rigor_for_complexity(self, prompt: str) -> RigorLevel:
        """Determine appropriate rigor level based on task complexity.

        Complexity signals:
        - Number of requirements/statements
        - Presence of specific technical terms
        - Task scope (single file vs. multi-module)
        """
        words = len(prompt.split())
        has_architecture_terms = bool(re.search(
            r"\b(system|architecture|module|service|integration|migration)\b",
            prompt, re.IGNORECASE,
        ))
        has_multiple_requirements = bool(re.search(
            r"\b(and|also|additionally|plus|then|after that)\b",
            prompt, re.IGNORECASE,
        ))

        score = 0
        if words > 30:
            score += 2
        elif words > 15:
            score += 1
        if has_architecture_terms:
            score += 2
        if has_multiple_requirements:
            score += 1

        if score >= 4:
            return RigorLevel.EXHAUSTIVE
        elif score >= 3:
            return RigorLevel.THOROUGH
        elif score >= 1:
            return RigorLevel.STANDARD
        else:
            return RigorLevel.MINIMAL
