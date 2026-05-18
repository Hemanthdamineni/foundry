"""Pre-Spec Context Harvesting — ensures every important question is asked before spec approval.

After SPEC_APPROVED = TRUE, no human questions are allowed.
Only autonomous replanning, compromises, and recovery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

if TYPE_CHECKING:
    from sdlc.runtime.pipelines.default import IndexPipeline

logger = get_logger("engine.context_harvester")


# ── Question Categories ─────────────────────────────────────────────


class HarvestQuestion(BaseModel):
    """A single question generated during context harvesting."""

    category: str
    question: str
    priority: str = "medium"  # "critical", "high", "medium", "low"
    resolved: bool = False
    answer: str | None = None


class ContextBundle(BaseModel):
    """The complete context bundle produced by harvesting."""

    task_description: str
    questions: list[HarvestQuestion] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    architecture: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    coding_standards: dict[str, Any] = Field(default_factory=dict)
    risk_factors: list[str] = Field(default_factory=list)
    scalability: dict[str, Any] = Field(default_factory=dict)
    deployment: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False

    @property
    def unresolved_questions(self) -> list[HarvestQuestion]:
        return [q for q in self.questions if not q.resolved]

    @property
    def critical_unresolved(self) -> list[HarvestQuestion]:
        return [q for q in self.unresolved_questions if q.priority == "critical"]


# ── Question Templates ──────────────────────────────────────────────

HARVEST_TEMPLATES: dict[str, list[str]] = {
    "requirements": [
        "What are the exact functional requirements?",
        "Are there non-functional requirements (performance, availability)?",
        "What is the acceptance criteria for this task?",
        "Are there any implicit requirements not stated?",
    ],
    "constraints": [
        "What languages/frameworks must be used?",
        "Are there version compatibility constraints?",
        "Are there API contract constraints?",
        "What are the performance constraints (latency, throughput, memory)?",
    ],
    "environment": [
        "What is the target deployment environment?",
        "Are there OS-specific requirements?",
        "What databases/services are available?",
        "Are there existing CI/CD pipelines to integrate with?",
    ],
    "deployment": [
        "How will this be deployed?",
        "Are there staging/production environment differences?",
        "What rollback strategy is expected?",
        "Are there downtime constraints?",
    ],
    "edge_cases": [
        "What happens on empty/null input?",
        "What are the error handling expectations?",
        "How should concurrent access be handled?",
        "What are the boundary conditions?",
    ],
    "scalability": [
        "What are the expected data volumes?",
        "What is the expected user/request load?",
        "Are there caching requirements?",
        "Is horizontal scaling needed?",
    ],
    "risk_tolerance": [
        "What is the acceptable failure rate?",
        "How critical is this system?",
        "What is the data sensitivity level?",
        "Are there compliance requirements?",
    ],
    "architecture": [
        "Should this follow existing architectural patterns?",
        "Are there microservice/monolith preferences?",
        "What are the integration points with existing systems?",
        "Are there authentication/authorization requirements?",
    ],
    "dependencies": [
        "What external dependencies are allowed?",
        "Are there approved package lists?",
        "Are there licensing constraints on dependencies?",
        "What are the minimum version requirements?",
    ],
    "coding_standards": [
        "What coding style conventions should be followed?",
        "Are there naming conventions to follow?",
        "What testing coverage is expected?",
        "Are there documentation requirements?",
    ],
}


# ── Harvester ────────────────────────────────────────────────────────


class ContextHarvester:
    """Generates context questions and analyzes the environment before spec generation.

    The harvester runs BEFORE the Specs phase to ensure all important
    questions are asked upfront. After spec approval, no human questions
    are allowed — only autonomous decision-making.
    """

    def __init__(self, index_pipeline: IndexPipeline | None = None) -> None:
        self._index_pipeline = index_pipeline

    async def harvest(
        self,
        task_description: str,
        *,
        repo_analysis: bool = True,
    ) -> ContextBundle:
        """Generate the full context bundle with questions and environment analysis."""
        bundle = ContextBundle(task_description=task_description)

        # Generate questions from templates
        self._generate_questions(bundle, task_description)

        # Analyze the repository if index pipeline is available
        if repo_analysis and self._index_pipeline is not None:
            await self._analyze_environment(bundle)

        logger.info(
            "Context harvesting complete",
            extra={
                "total_questions": len(bundle.questions),
                "critical_questions": len(bundle.critical_unresolved),
                "categories": list({q.category for q in bundle.questions}),
            },
        )
        return bundle

    def _generate_questions(
        self,
        bundle: ContextBundle,
        description: str,
    ) -> None:
        """Generate relevant questions based on the task description."""
        desc_lower = description.lower()

        for category, templates in HARVEST_TEMPLATES.items():
            relevance = self._category_relevance(category, desc_lower)
            if relevance == "skip":
                continue

            priority = "high" if relevance == "high" else "medium"
            for question_text in templates:
                bundle.questions.append(
                    HarvestQuestion(
                        category=category,
                        question=question_text,
                        priority=priority,
                    ),
                )

        # Always add critical questions
        bundle.questions.extend([
            HarvestQuestion(
                category="requirements",
                question="Is the task description complete and unambiguous?",
                priority="critical",
            ),
            HarvestQuestion(
                category="constraints",
                question="Are there any hard constraints that would make this task impossible?",
                priority="critical",
            ),
        ])

    def _category_relevance(self, category: str, desc_lower: str) -> str:
        """Determine how relevant a category is to the task."""
        relevance_keywords: dict[str, list[str]] = {
            "deployment": ["deploy", "release", "production", "staging", "ci/cd"],
            "scalability": ["scale", "performance", "load", "concurrent", "throughput"],
            "architecture": ["api", "service", "endpoint", "module", "component"],
            "edge_cases": ["error", "handle", "edge", "boundary", "validate"],
            "risk_tolerance": ["critical", "security", "compliance", "sensitive"],
        }

        keywords = relevance_keywords.get(category, [])
        if any(kw in desc_lower for kw in keywords):
            return "high"
        # Always include requirements, constraints, coding_standards, dependencies
        if category in {"requirements", "constraints", "coding_standards", "dependencies"}:
            return "normal"
        return "normal"  # include all by default

    async def _analyze_environment(self, bundle: ContextBundle) -> None:
        """Analyze the existing codebase for patterns and conventions."""
        if self._index_pipeline is None:
            return

        try:
            stats = self._index_pipeline.stats
            bundle.environment = {
                "indexed_files": stats.get("file_count", 0),
                "languages": stats.get("languages", {}),
                "has_tests": stats.get("has_tests", False),
            }

            # Auto-resolve coding standards from existing code
            if stats.get("file_count", 0) > 0:
                bundle.coding_standards = {
                    "detected": True,
                    "languages": stats.get("languages", {}),
                    "note": "Coding standards detected from existing codebase",
                }
                # Resolve the coding standards question
                for q in bundle.questions:
                    if q.category == "coding_standards":
                        q.resolved = True
                        q.answer = "Auto-detected from existing codebase"

        except Exception:
            logger.warning("Environment analysis failed", exc_info=True)

    def resolve_question(
        self,
        bundle: ContextBundle,
        category: str,
        answer: str,
    ) -> int:
        """Resolve all unresolved questions in a category with the given answer.

        Returns the number of questions resolved.
        """
        resolved_count = 0
        for q in bundle.questions:
            if q.category == category and not q.resolved:
                q.resolved = True
                q.answer = answer
                resolved_count += 1
        return resolved_count

    def resolve_all(self, bundle: ContextBundle, answers: dict[str, str]) -> None:
        """Resolve questions in bulk from a category→answer mapping."""
        for category, answer in answers.items():
            self.resolve_question(bundle, category, answer)

    def is_ready_for_spec(self, bundle: ContextBundle) -> tuple[bool, list[str]]:
        """Check if all critical questions have been answered.

        Returns (ready, list_of_blocking_reasons).
        """
        blocking = []
        critical = bundle.critical_unresolved
        if critical:
            blocking.extend(
                f"[{q.category}] {q.question}" for q in critical
            )
        return len(blocking) == 0, blocking

    def to_spec_context(self, bundle: ContextBundle) -> str:
        """Format the resolved bundle as context text for the Specs phase."""
        parts: list[str] = [
            f"# Context Bundle for: {bundle.task_description}",
            "",
        ]

        if bundle.constraints:
            parts.append("## Constraints")
            for k, v in bundle.constraints.items():
                parts.append(f"- **{k}**: {v}")
            parts.append("")

        if bundle.environment:
            parts.append("## Environment")
            for k, v in bundle.environment.items():
                parts.append(f"- **{k}**: {v}")
            parts.append("")

        if bundle.coding_standards:
            parts.append("## Coding Standards")
            for k, v in bundle.coding_standards.items():
                parts.append(f"- **{k}**: {v}")
            parts.append("")

        resolved = [q for q in bundle.questions if q.resolved and q.answer]
        if resolved:
            parts.append("## Resolved Questions")
            for q in resolved:
                parts.append(f"- **[{q.category}]** {q.question}")
                parts.append(f"  → {q.answer}")
            parts.append("")

        return "\n".join(parts)


# ── Spec-Lock Enforcement ────────────────────────────────────────────


class SpecLockViolation(BaseModel):
    """A detected violation of the spec-lock rule."""

    field: str
    original: str
    detected: str
    severity: str = "warning"  # "warning", "error"


def check_spec_drift(
    locked_spec: str,
    current_output: str,
    *,
    strict: bool = False,
) -> list[SpecLockViolation]:
    """Check if a post-spec output drifts from the locked spec.

    Detects:
    - New requirements added that weren't in the spec
    - Scope changes (features added/removed)
    - Constraint violations

    In strict mode, any drift is an error. In normal mode, implementation
    adaptations are allowed but requirement changes are flagged.
    """
    violations: list[SpecLockViolation] = []
    spec_lower = locked_spec.lower()
    output_lower = current_output.lower()

    # Check for scope expansion signals
    expansion_signals = [
        "additional feature",
        "also implement",
        "bonus feature",
        "while we're at it",
        "scope expansion",
        "new requirement",
        "added requirement",
    ]
    for signal in expansion_signals:
        if signal in output_lower and signal not in spec_lower:
            violations.append(
                SpecLockViolation(
                    field="scope",
                    original="Locked spec does not mention this",
                    detected=f"Scope expansion signal detected: '{signal}'",
                    severity="error" if strict else "warning",
                ),
            )

    # Check for requirement change signals
    change_signals = [
        "changed requirement",
        "updated requirement",
        "instead of",
        "no longer need",
        "replacing the requirement",
    ]
    for signal in change_signals:
        if signal in output_lower and signal not in spec_lower:
            violations.append(
                SpecLockViolation(
                    field="requirements",
                    original="Original spec requirements",
                    detected=f"Requirement change signal: '{signal}'",
                    severity="error",
                ),
            )

    return violations
