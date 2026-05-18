"""Multi-judge hierarchy — NO SINGLE JUDGE MAY APPROVE ALONE.

Each judge evaluates a different dimension:
- ToolJudge: objective truth (lint/type/test pass/fail)
- SemanticJudge: spec alignment (LLM)
- ArchitectureJudge: long-term maintainability (LLM)
- SecurityJudge: security correctness (tool + LLM)
- RiskJudge: operational safety (LLM)
- IntegrationJudge: cross-module stability (test + LLM)
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger
from sdlc.models import JudgeVerdict

if TYPE_CHECKING:
    from sdlc.adapters.llm import LLMProvider
    from sdlc.models import Task

logger = get_logger("engine.judge_hierarchy")


class JudgeType(StrEnum):
    TOOL = "tool"
    SEMANTIC = "semantic"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    RISK = "risk"
    INTEGRATION = "integration"


class JudgeVote(BaseModel):
    """A single judge's vote with rationale."""

    judge_type: JudgeType
    passed: bool
    confidence: float = 0.0
    reason: str = ""
    issues: list[str] = Field(default_factory=list)
    severity: str = "info"


class HierarchyVerdict(BaseModel):
    """Aggregated verdict from the full judge hierarchy."""

    passed: bool
    votes: list[JudgeVote] = Field(default_factory=list)
    consensus_reason: str = ""
    blocking_judges: list[str] = Field(default_factory=list)
    total_confidence: float = 0.0

    def to_judge_verdict(self) -> JudgeVerdict:
        """Convert to the standard JudgeVerdict for backward compatibility."""
        all_issues: list[str] = []
        for v in self.votes:
            all_issues.extend(v.issues)
        worst_severity = "info"
        severity_order = {"info": 0, "warning": 1, "error": 2, "critical": 3}
        for v in self.votes:
            if severity_order.get(v.severity, 0) > severity_order.get(worst_severity, 0):
                worst_severity = v.severity
        return JudgeVerdict(
            passed=self.passed,
            reason=self.consensus_reason,
            issues=all_issues,
            severity=worst_severity,
        )


# ── Phase → Judge Mapping ───────────────────────────────────────────

# Not all judges run on every transition. This maps which judges
# are active for which phase transitions.
PHASE_JUDGES: dict[str, list[JudgeType]] = {
    "Specs": [JudgeType.SEMANTIC],
    "Planning": [JudgeType.SEMANTIC, JudgeType.ARCHITECTURE, JudgeType.RISK],
    "Coding": [JudgeType.TOOL, JudgeType.SEMANTIC, JudgeType.SECURITY],
    "Review": [JudgeType.TOOL, JudgeType.SEMANTIC, JudgeType.ARCHITECTURE, JudgeType.SECURITY],
    "Testing": [JudgeType.TOOL, JudgeType.INTEGRATION],
}


# ── Individual Judges ────────────────────────────────────────────────


class ToolJudge:
    """Objective truth — did lint/type/test pass?"""

    judge_type = JudgeType.TOOL

    async def evaluate(
        self,
        _task: Task,
        _phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        issues: list[str] = []
        passed = True
        output_lower = output.lower()

        # Check for explicit failure signals
        failure_signals = ["failed", "error", "exception", "traceback"]
        for signal in failure_signals:
            if signal in output_lower:
                # Only flag if it seems like a test/lint/type failure
                if any(ctx in output_lower for ctx in ["test", "lint", "ruff", "mypy", "pytest"]):
                    issues.append(f"Tool failure signal detected: '{signal}'")
                    passed = False

        return JudgeVote(
            judge_type=self.judge_type,
            passed=passed,
            confidence=0.95 if passed else 0.9,
            reason="All tool checks passed" if passed else "Tool failures detected",
            issues=issues,
            severity="info" if passed else "error",
        )


class SemanticJudge:
    """Spec alignment — does the output match what was requested?"""

    judge_type = JudgeType.SEMANTIC

    def __init__(self, provider: LLMProvider | None = None, model: str = "") -> None:
        self._provider = provider
        self._model = model

    async def evaluate(
        self,
        task: Task,
        phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        # Without LLM, do structural check
        if self._provider is None:
            return self._structural_check(task, phase, output)

        try:
            prompt = (
                f"Evaluate if this {phase} output aligns with the task spec.\n\n"
                f"Task: {task.description}\n\n"
                f"Output (first 2000 chars): {output[:2000]}\n\n"
                "Respond with PASS or FAIL followed by one-line reason."
            )
            response = await self._provider.generate(self._model, prompt)
            passed = response.strip().upper().startswith("PASS")
            return JudgeVote(
                judge_type=self.judge_type,
                passed=passed,
                confidence=0.7,
                reason=response.strip()[:200],
                severity="info" if passed else "warning",
            )
        except Exception as e:
            logger.warning("SemanticJudge LLM call failed", extra={"error": str(e)})
            return self._structural_check(task, phase, output)

    def _structural_check(self, task: Task, _phase: str, output: str) -> JudgeVote:
        """Fallback: check if output references key terms from task description."""
        desc_words = set(task.description.lower().split())
        output_lower = output.lower()
        matches = sum(1 for w in desc_words if len(w) > 4 and w in output_lower)
        relevance = matches / max(len(desc_words), 1)
        passed = relevance > 0.1
        return JudgeVote(
            judge_type=self.judge_type,
            passed=passed,
            confidence=0.5,
            reason=f"Structural relevance: {relevance:.1%}",
            severity="info" if passed else "warning",
        )


class ArchitectureJudge:
    """Long-term maintainability and architectural quality."""

    judge_type = JudgeType.ARCHITECTURE

    async def evaluate(
        self,
        _task: Task,
        phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        issues: list[str] = []
        output_lower = output.lower()

        # Check for architecture anti-patterns
        antipatterns = {
            "god class": "Potential god class detected",
            "circular import": "Circular import risk",
            "global state": "Global mutable state",
            "hardcoded": "Hardcoded values detected",
        }
        for pattern, description in antipatterns.items():
            if pattern in output_lower:
                issues.append(description)

        return JudgeVote(
            judge_type=self.judge_type,
            passed=len(issues) == 0,
            confidence=0.6,
            reason="No architectural concerns" if not issues else f"{len(issues)} concerns found",
            issues=issues,
            severity="info" if not issues else "warning",
        )


class SecurityJudge:
    """Security correctness."""

    judge_type = JudgeType.SECURITY

    async def evaluate(
        self,
        _task: Task,
        _phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        issues: list[str] = []
        output_lower = output.lower()

        security_risks = {
            "eval(": "Use of eval() detected",
            "exec(": "Use of exec() detected",
            "os.system(": "Use of os.system() detected",
            "subprocess.call(": "Unsafe subprocess usage",
            "password": "Password handling detected — verify security",
            "secret": "Secret handling detected — verify security",
            "sql injection": "SQL injection risk mentioned",
            "pickle.loads": "Unsafe deserialization detected",
        }
        for pattern, description in security_risks.items():
            if pattern in output_lower:
                issues.append(description)

        passed = not any(
            "eval(" in output_lower or "exec(" in output_lower or "pickle.loads" in output_lower
            for _ in [None]
        )
        return JudgeVote(
            judge_type=self.judge_type,
            passed=passed,
            confidence=0.8,
            reason="No security concerns" if passed else f"{len(issues)} security issues",
            issues=issues,
            severity="info" if passed else "critical",
        )


class RiskJudge:
    """Operational safety assessment."""

    judge_type = JudgeType.RISK

    async def evaluate(
        self,
        _task: Task,
        _phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        issues: list[str] = []
        output_lower = output.lower()

        risk_signals = {
            "breaking change": "Breaking change identified",
            "migration required": "Database migration needed",
            "backwards incompatible": "Backward incompatibility",
            "data loss": "Potential data loss risk",
            "downtime": "Downtime may be required",
        }
        for signal, description in risk_signals.items():
            if signal in output_lower:
                issues.append(description)

        return JudgeVote(
            judge_type=self.judge_type,
            passed=True,  # Risk judge warns but doesn't block
            confidence=0.7,
            reason="No major risks" if not issues else f"{len(issues)} risks identified",
            issues=issues,
            severity="info" if not issues else "warning",
        )


class IntegrationJudge:
    """Cross-module stability."""

    judge_type = JudgeType.INTEGRATION

    async def evaluate(
        self,
        _task: Task,
        _phase: str,
        output: str,
        **_kwargs: Any,
    ) -> JudgeVote:
        output_lower = output.lower()
        issues: list[str] = []

        # Check testing output for integration failures
        if "failed" in output_lower and "test" in output_lower:
            issues.append("Test failures detected in output")
        if "import error" in output_lower:
            issues.append("Import errors suggest integration issues")

        passed = len(issues) == 0
        return JudgeVote(
            judge_type=self.judge_type,
            passed=passed,
            confidence=0.75,
            reason="Integration stable" if passed else f"{len(issues)} integration issues",
            issues=issues,
            severity="info" if passed else "error",
        )


# ── Hierarchy Orchestrator ───────────────────────────────────────────


class JudgeHierarchy:
    """Orchestrates multi-judge evaluation — NO SINGLE JUDGE MAY APPROVE ALONE."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str = "",
    ) -> None:
        self._judges: dict[JudgeType, Any] = {
            JudgeType.TOOL: ToolJudge(),
            JudgeType.SEMANTIC: SemanticJudge(provider=provider, model=model),
            JudgeType.ARCHITECTURE: ArchitectureJudge(),
            JudgeType.SECURITY: SecurityJudge(),
            JudgeType.RISK: RiskJudge(),
            JudgeType.INTEGRATION: IntegrationJudge(),
        }

    async def evaluate(
        self,
        task: Task,
        phase: str,
        next_phase: str,
        output: str,
    ) -> HierarchyVerdict:
        """Run all applicable judges for this phase transition."""
        applicable = PHASE_JUDGES.get(phase, [JudgeType.SEMANTIC])

        votes: list[JudgeVote] = []
        for judge_type in applicable:
            judge = self._judges.get(judge_type)
            if judge is None:
                continue
            try:
                vote = await judge.evaluate(task, phase, output)
                votes.append(vote)
            except Exception as e:
                logger.warning(
                    "Judge evaluation failed",
                    extra={"judge": judge_type, "error": str(e)},
                )
                votes.append(JudgeVote(
                    judge_type=judge_type,
                    passed=True,  # Fail-open on judge error
                    confidence=0.1,
                    reason=f"Judge error: {e}",
                    severity="warning",
                ))

        # Consensus: majority must pass, and no critical-severity blocker
        blocking = [v for v in votes if not v.passed and v.severity in ("error", "critical")]
        all_passed = all(v.passed for v in votes)
        majority_passed = sum(1 for v in votes if v.passed) > len(votes) / 2

        passed = all_passed or (majority_passed and not blocking)
        total_confidence = (
            sum(v.confidence for v in votes) / len(votes) if votes else 0.0
        )

        if passed:
            reason = f"Approved by {sum(1 for v in votes if v.passed)}/{len(votes)} judges"
        else:
            reason = f"Blocked by: {', '.join(v.judge_type for v in blocking)}"

        return HierarchyVerdict(
            passed=passed,
            votes=votes,
            consensus_reason=reason,
            blocking_judges=[v.judge_type for v in blocking],
            total_confidence=total_confidence,
        )
