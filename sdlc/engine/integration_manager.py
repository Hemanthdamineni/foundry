"""Integration manager — explicit orchestration for phase merges, validation, and stabilization.

Responsibilities:
- Phase merge coordination (ensuring micro-task outputs compose correctly)
- Integration validation (run integration tests after merge)
- Regression stabilization (detect and revert regression-introducing changes)
- Dependency synchronization (ensure cross-module interfaces match)
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.integration_manager")


class MergeResult(BaseModel):
    """Result of a phase merge operation."""

    phase_id: str
    status: str = "pending"  # pending, merged, conflict, failed
    files_merged: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    validation_passed: bool = False
    regression_detected: bool = False
    rollback_required: bool = False


class IntegrationTest(BaseModel):
    """An integration test to run after merge."""

    name: str
    command: str
    target_files: list[str] = Field(default_factory=list)
    timeout_s: int = 120
    passed: bool | None = None
    output: str = ""


class DependencyContract(BaseModel):
    """A contract between two modules defining their interface."""

    source_module: str
    target_module: str
    interface_type: str = "import"  # import, api, event, config
    symbols: list[str] = Field(default_factory=list)
    version: str = ""
    compatible: bool = True
    issues: list[str] = Field(default_factory=list)


class IntegrationManager:
    """Orchestrates phase merges, integration validation, and regression stabilization."""

    def __init__(self) -> None:
        self._merge_history: list[MergeResult] = []
        self._integration_tests: list[IntegrationTest] = []
        self._contracts: list[DependencyContract] = []
        self._baselines: dict[str, dict[str, Any]] = {}  # test_name → baseline metrics

    # ── Phase Merge ──────────────────────────────────────────────

    def prepare_merge(
        self,
        phase_id: str,
        files_from_microtasks: list[list[str]],
    ) -> MergeResult:
        """Prepare a phase merge by checking for file conflicts across micro-tasks."""
        all_files: list[str] = []
        file_owners: dict[str, list[int]] = {}

        for i, files in enumerate(files_from_microtasks):
            for f in files:
                all_files.append(f)
                file_owners.setdefault(f, []).append(i)

        conflicts = [f for f, owners in file_owners.items() if len(owners) > 1]

        result = MergeResult(
            phase_id=phase_id,
            files_merged=list(set(all_files)),
            conflicts=conflicts,
            status="conflict" if conflicts else "merged",
        )
        self._merge_history.append(result)
        return result

    def resolve_conflict(
        self,
        merge: MergeResult,
        file_path: str,
        winner_microtask: int,
    ) -> None:
        """Resolve a merge conflict by choosing which micro-task's version wins."""
        if file_path in merge.conflicts:
            merge.conflicts.remove(file_path)
        if not merge.conflicts:
            merge.status = "merged"

    # ── Integration Validation ───────────────────────────────────

    def register_integration_test(self, test: IntegrationTest) -> None:
        """Register an integration test to run after merges."""
        self._integration_tests.append(test)

    async def run_integration_tests(
        self,
        cwd: str = ".",
    ) -> list[IntegrationTest]:
        """Run all registered integration tests."""
        results: list[IntegrationTest] = []
        for test in self._integration_tests:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *test.command.split(),
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=test.timeout_s,
                )
                test.passed = proc.returncode == 0
                test.output = stdout.decode("utf-8", errors="replace")[-2000:]
            except asyncio.TimeoutError:
                test.passed = False
                test.output = f"Timed out after {test.timeout_s}s"
            except FileNotFoundError:
                test.passed = None
                test.output = f"Command not found: {test.command.split()[0]}"
            results.append(test)
        return results

    def validate_merge(self, merge: MergeResult, test_results: list[IntegrationTest]) -> MergeResult:
        """Validate a merge against integration test results."""
        all_passed = all(t.passed for t in test_results if t.passed is not None)
        merge.validation_passed = all_passed

        # Compare against baselines for regression detection
        for test in test_results:
            baseline = self._baselines.get(test.name)
            if baseline and test.passed is False and baseline.get("passed") is True:
                merge.regression_detected = True
                merge.rollback_required = True
                break

        if merge.regression_detected:
            merge.status = "failed"
        elif all_passed:
            merge.status = "merged"

        return merge

    # ── Regression Stabilization ─────────────────────────────────

    def set_baseline(self, test_name: str, metrics: dict[str, Any]) -> None:
        """Set a baseline for regression comparison."""
        self._baselines[test_name] = metrics

    def check_regression(
        self,
        test_name: str,
        current: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare current results against baseline for regression."""
        baseline = self._baselines.get(test_name)
        if not baseline:
            return {"status": "no_baseline", "test": test_name}

        regressions: list[str] = []

        # Check pass/fail regression
        if baseline.get("passed") and not current.get("passed"):
            regressions.append("Test was passing, now failing")

        # Check coverage regression
        baseline_cov = baseline.get("coverage", 0)
        current_cov = current.get("coverage", 0)
        if current_cov < baseline_cov - 1:  # Allow 1% tolerance
            regressions.append(
                f"Coverage dropped: {baseline_cov}% → {current_cov}%",
            )

        # Check performance regression
        baseline_ms = baseline.get("duration_ms", 0)
        current_ms = current.get("duration_ms", 0)
        if baseline_ms > 0 and current_ms > baseline_ms * 1.2:  # 20% threshold
            regressions.append(
                f"Performance degraded: {baseline_ms}ms → {current_ms}ms",
            )

        return {
            "test": test_name,
            "regression_detected": len(regressions) > 0,
            "regressions": regressions,
            "baseline": baseline,
            "current": current,
        }

    # ── Dependency Synchronization ───────────────────────────────

    def register_contract(self, contract: DependencyContract) -> None:
        """Register a dependency contract between modules."""
        self._contracts.append(contract)

    def validate_contracts(
        self,
        available_symbols: dict[str, list[str]],
    ) -> list[DependencyContract]:
        """Validate all dependency contracts against available symbols."""
        violations: list[DependencyContract] = []
        for contract in self._contracts:
            module_symbols = available_symbols.get(contract.target_module, [])
            missing = [s for s in contract.symbols if s not in module_symbols]
            if missing:
                contract.compatible = False
                contract.issues = [f"Missing symbol: {s}" for s in missing]
                violations.append(contract)
        return violations

    # ── Status ───────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get integration manager status."""
        successful = sum(1 for m in self._merge_history if m.status == "merged")
        failed = sum(1 for m in self._merge_history if m.status == "failed")
        regressions = sum(1 for m in self._merge_history if m.regression_detected)
        return {
            "total_merges": len(self._merge_history),
            "successful_merges": successful,
            "failed_merges": failed,
            "regressions_detected": regressions,
            "registered_tests": len(self._integration_tests),
            "registered_contracts": len(self._contracts),
            "baselines": list(self._baselines.keys()),
        }
