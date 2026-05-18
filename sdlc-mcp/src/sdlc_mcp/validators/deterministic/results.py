"""Validation report aggregation — models for collecting deterministic check results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc_mcp.models import FailureType


class ValidationResult(BaseModel):
    """Single validation result from one adapter run."""

    adapter: str
    capability: str
    passed: bool
    summary: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    failure_type: FailureType | None = None
    duration_ms: int | None = None


class ValidationReport(BaseModel):
    """Aggregated report from all validation adapters run against a phase output."""

    phase: str
    task_id: str
    output_summary: str = ""
    results: list[ValidationResult] = Field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    all_passed: bool = False
    schema_violations: list[str] = Field(default_factory=list)

    def add_result(self, result: ValidationResult) -> None:
        """Append a single validation result and update counters."""
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
        self.all_passed = self.failed_checks == 0

    def merge(self, other: ValidationReport) -> ValidationReport:
        """Merge another report's results and schema violations into this one."""
        for result in other.results:
            self.add_result(result)
        self.schema_violations.extend(other.schema_violations)
        return self

    def primary_failure(self) -> FailureType | None:
        """Return the FailureType of the first failing result, if any."""
        for result in self.results:
            if not result.passed and result.failure_type is not None:
                return result.failure_type
        return None

    def summary(self) -> str:
        """Render a human-readable validation summary."""
        status = "PASS" if self.all_passed else "FAIL"
        parts = [
            f"[{status}] Validation Report for {self.phase} phase",
            f"  Passed: {self.passed_checks}/{self.total_checks}",
            f"  Failed: {self.failed_checks}/{self.total_checks}",
        ]
        if self.schema_violations:
            parts.append("  Schema violations:")
            parts.extend(f"    - {v}" for v in self.schema_violations)
        parts.extend(
            f"  {result.adapter}: {result.summary}"
            for result in self.results
            if not result.passed
        )
        return "\n".join(parts)
