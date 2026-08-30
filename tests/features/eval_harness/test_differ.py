"""Tests for EvalDiffer — regression and improvement detection."""

from __future__ import annotations

from datetime import UTC, datetime

from foundry.features.eval_harness.reports.differ import DiffStatus, EvalDiffer
from foundry.features.eval_harness.runners.runner import EvalResult, EvalScenarioResult


def _make_result(suite_name: str, *scenario_defs: tuple[str, bool, int]) -> EvalResult:
    """Build an EvalResult from compact scenario definitions.

    Each definition is ``(name, passed, duration_ms)``.
    """
    scenarios = [
        EvalScenarioResult(
            scenario_name=name,
            passed=passed,
            actual_pass=passed,
            duration_ms=duration,
        )
        for name, passed, duration in scenario_defs
    ]
    return EvalResult(
        suite_name=suite_name,
        timestamp=datetime.now(UTC).isoformat(),
        scenarios=scenarios,
        total=len(scenarios),
        passed=sum(1 for s in scenarios if s.passed),
        failed=sum(1 for s in scenarios if not s.passed),
    )


class TestEvalDiffer:
    """EvalDiffer.diff behaviour."""

    def test_diff_no_baseline(self) -> None:
        """When baseline is None, every scenario is 'new'."""
        current = _make_result("test", ("a", True, 100), ("b", False, 200))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline=None)
        assert diff.total == 2
        assert diff.new == 2
        assert diff.regressions == 0
        for entry in diff.entries:
            assert entry.status == DiffStatus.NEW

    def test_diff_unchanged(self) -> None:
        """Scenarios with same pass/fail in both runs are unchanged."""
        current = _make_result("test", ("a", True, 100))
        baseline = _make_result("test", ("a", True, 90))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.total == 1
        assert diff.unchanged == 1
        assert diff.regressions == 0
        assert diff.improvements == 0

    def test_diff_regression(self) -> None:
        """A scenario that passed in baseline but fails now is a regression."""
        current = _make_result("test", ("a", False, 100))
        baseline = _make_result("test", ("a", True, 90))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.regressions == 1
        regression = diff.entries[0]
        assert regression.status == DiffStatus.REGRESSED
        assert regression.scenario_name == "a"

    def test_diff_improvement(self) -> None:
        """A scenario that failed in baseline but passes now is an improvement."""
        current = _make_result("test", ("a", True, 100))
        baseline = _make_result("test", ("a", False, 90))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.improvements == 1
        improvement = diff.entries[0]
        assert improvement.status == DiffStatus.IMPROVED
        assert improvement.scenario_name == "a"

    def test_diff_new_scenario(self) -> None:
        """A scenario in current but not in baseline is 'new'."""
        current = _make_result("test", ("a", True, 100))
        baseline = _make_result("test")
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.new == 1
        assert diff.entries[0].status == DiffStatus.NEW

    def test_diff_removed_scenario(self) -> None:
        """A scenario in baseline but not in current is 'removed'."""
        current = _make_result("test")
        baseline = _make_result("test", ("a", True, 100))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.removed == 1
        assert diff.entries[0].status == DiffStatus.REMOVED

    def test_diff_mixed(self) -> None:
        """Multiple scenarios with different statuses are all reported."""
        current = _make_result(
            "test",
            ("unchanged", True, 100),
            ("regressed", False, 200),
            ("improved", True, 300),
            ("new", True, 400),
        )
        baseline = _make_result(
            "test",
            ("unchanged", True, 90),
            ("regressed", True, 180),
            ("improved", False, 280),
            ("removed", True, 500),
        )
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.total == 5  # 4 current + 1 removed (from baseline)
        assert diff.unchanged == 1
        assert diff.regressions == 1
        assert diff.improvements == 1
        assert diff.new == 1
        assert diff.removed == 1

        status_map = {e.scenario_name: e.status for e in diff.entries}
        assert status_map["unchanged"] == DiffStatus.UNCHANGED
        assert status_map["regressed"] == DiffStatus.REGRESSED
        assert status_map["improved"] == DiffStatus.IMPROVED
        assert status_map["new"] == DiffStatus.NEW
        assert status_map["removed"] == DiffStatus.REMOVED

    def test_diff_errors_in_current(self) -> None:
        """A previously-passing scenario that now errors is a regression."""
        current = EvalResult(
            suite_name="test",
            timestamp=datetime.now(UTC).isoformat(),
            scenarios=[
                EvalScenarioResult(
                    scenario_name="a",
                    passed=False,
                    actual_pass=None,
                    error="RuntimeError: something broke",
                    duration_ms=50,
                ),
            ],
            total=1,
            passed=0,
            failed=1,
        )
        baseline = _make_result("test", ("a", True, 100))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.regressions == 1
        assert diff.entries[0].status == DiffStatus.REGRESSED
        assert "something broke" in diff.entries[0].notes

    def test_diff_same_suite_name_mismatch(self) -> None:
        """Diff uses the current suite's name regardless of baseline name."""
        current = _make_result("current-suite", ("a", True, 100))
        baseline = _make_result("baseline-suite", ("a", True, 90))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        assert diff.suite_name == "current-suite"

    def test_diff_duration_comparison(self) -> None:
        """Duration values are carried through in diff entries."""
        current = _make_result("test", ("a", False, 500))
        baseline = _make_result("test", ("a", True, 100))
        differ = EvalDiffer()
        diff = differ.diff(current, baseline)
        entry = diff.entries[0]
        assert entry.baseline_duration_ms == 100
        assert entry.current_duration_ms == 500
