"""ValidationRunner — orchestrates deterministic checks before any LLM evaluation.

Runs all registered adapters in parallel, aggregates results into a
ValidationReport, and maps failures to FailureType for the ExecutionPolicy.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from sdlc.engine.schema_checks import validate_phase_output
from sdlc.models import FailureType
from sdlc.validators.deterministic.results import ValidationReport, ValidationResult

if TYPE_CHECKING:
    from sdlc.adapters.base import ToolAdapter, ToolCapability


class ValidationRunner:
    """Aggregates adapter outputs and schema checks into a single report.

    Usage:
        runner = ValidationRunner(adapters=[ruff, mypy, pytest])
        report = await runner.run_all("path/to/workspace", phase="Review")
    """

    def __init__(self, adapters: list[ToolAdapter] | None = None) -> None:
        """Initialize with an optional list of adapters."""
        self._adapters: list[ToolAdapter] = adapters or []

    def register(self, adapter: ToolAdapter) -> None:
        """Register a new adapter to run during validation."""
        self._adapters.append(adapter)

    def registered_capabilities(self) -> list[ToolCapability]:
        """Return the capabilities of all registered adapters."""
        return [a.capability for a in self._adapters]

    async def run_all(
        self,
        task: dict[str, Any],
        phase: str,
        output: str | None = None,
    ) -> ValidationReport:
        """Run all validation adapters in parallel against the given task.

        Args:
            task: Task dict with at minimum a "path" key pointing to the
                  workspace root.
            phase: Current phase name (e.g. "Review", "Coding").
            output: Optional phase output text for schema section checks.

        Returns:
            Aggregated ValidationReport with all adapter results and any
            schema violations.

        """
        report = ValidationReport(
            phase=phase,
            task_id=task.get("task_id", "unknown"),
            output_summary=(output or "")[:200],
        )

        if output:
            violations = validate_phase_output(phase, output)
            for v in violations:
                report.schema_violations.append(str(v))
            report.all_passed = len(violations) == 0

        valid_adapters = [a for a in self._adapters if await a.validate(task)]

        results = await asyncio.gather(
            *[self._run_single(a, task) for a in valid_adapters],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                report.add_result(
                    ValidationResult(
                        adapter="unknown",
                        capability="unknown",
                        passed=False,
                        summary=f"Adapter crashed: {result}",
                        failure_type=FailureType.RETRYABLE_INFRA,
                    ),
                )
            elif isinstance(result, ValidationResult):
                report.add_result(result)

        return report

    async def run_for_phase(
        self,
        task: dict[str, Any],
        phase: str,
        output: str | None = None,
    ) -> ValidationReport:
        """Run validation for one phase."""
        return await self.run_all(task, phase=phase, output=output)

    async def _run_single(
        self, adapter: ToolAdapter, task: dict[str, Any],
    ) -> ValidationResult:
        start = time.monotonic()
        try:
            result = await adapter.execute(task)
            duration = int((time.monotonic() - start) * 1000)
            passed = bool(result.get("passed", False))
            return ValidationResult(
                adapter=str(result.get("adapter", adapter.name)),
                capability=str(result.get("capability", adapter.capability.value)),
                passed=passed,
                summary=str(result.get("summary", "")),
                details=result.get("details", []),
                failure_type=None if passed else FailureType.TERMINAL_VALIDATION,
                duration_ms=duration,
            )
        except Exception as e:  # noqa: BLE001
            duration = int((time.monotonic() - start) * 1000)
            return ValidationResult(
                adapter=adapter.name,
                capability=adapter.capability.value,
                passed=False,
                summary=f"Execution error: {e}",
                failure_type=FailureType.RETRYABLE_INFRA,
                duration_ms=duration,
            )
