"""EvalDiffer — regression and improvement detection between eval runs.

Compares a current ``EvalResult`` against a baseline to identify
scenarios that regressed (previously passed now fail), improved
(previously failed now pass), or remained unchanged.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from foundry.features.eval_harness.runners.runner import EvalResult, EvalScenarioResult


class DiffStatus(StrEnum):
    """Classification of a scenario-level change between two runs."""

    UNCHANGED = "unchanged"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    NEW = "new"
    REMOVED = "removed"
    ERRORED = "errored"


class EvalDiffEntry(BaseModel):
    """A single scenario-level diff entry.

    Attributes
    ----------
    scenario_name:
        Name of the scenario.
    status:
        How this scenario changed.
    baseline_pass:
        Pass/fail in the baseline run (``None`` if the scenario did not
        exist in the baseline).
    current_pass:
        Pass/fail in the current run (``None`` if the scenario was
        removed).
    baseline_duration_ms:
        Duration in the baseline run.
    current_duration_ms:
        Duration in the current run.
    notes:
        Human-readable explanation of the change.
    """

    scenario_name: str
    status: DiffStatus = DiffStatus.UNCHANGED
    baseline_pass: bool | None = None
    current_pass: bool | None = None
    baseline_duration_ms: int = 0
    current_duration_ms: int = 0
    notes: str = ""


class EvalDiff(BaseModel):
    """Full diff between two evaluation runs.

    Attributes
    ----------
    suite_name:
        Name of the suite being compared.
    baseline_timestamp:
        When the baseline run was made.
    current_timestamp:
        When the current run was made.
    entries:
        Per-scenario diffs.
    total:
        Total number of scenarios compared.
    regressions:
        Number of scenarios that regressed.
    improvements:
        Number of scenarios that improved.
    unchanged:
        Number of scenarios that stayed the same.
    new:
        Number of scenarios only in the current run.
    removed:
        Number of scenarios only in the baseline run.
    """

    suite_name: str
    baseline_timestamp: str = ""
    current_timestamp: str = ""
    entries: list[EvalDiffEntry] = Field(default_factory=list)
    total: int = 0
    regressions: int = 0
    improvements: int = 0
    unchanged: int = 0
    new: int = 0
    removed: int = 0


class EvalDiffer:
    """Computes diffs between two ``EvalResult`` runs.

    Usage::

        differ = EvalDiffer()
        diff = differ.diff(current_result, baseline_result)
        print(f"{diff.regressions} regressions, {diff.improvements} improvements")
    """

    def diff(
        self,
        current: EvalResult,
        baseline: EvalResult | None,
    ) -> EvalDiff:
        """Compare *current* against *baseline* and produce an ``EvalDiff``.

        Parameters
        ----------
        current:
            The result of the most recent run.
        baseline:
            An earlier run to compare against.  When ``None``, every
            scenario is reported as ``NEW``.
        """
        if baseline is None:
            return self._all_new(current)

        current_map: dict[str, EvalScenarioResult] = {
            r.scenario_name: r for r in current.scenarios
        }
        baseline_map: dict[str, EvalScenarioResult] = {
            r.scenario_name: r for r in baseline.scenarios
        }

        all_names: set[str] = set(current_map) | set(baseline_map)
        entries: list[EvalDiffEntry] = []

        for name in sorted(all_names):
            cur_result = current_map.get(name)
            base_result = baseline_map.get(name)

            if cur_result is None:
                # Removed from current.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.REMOVED,
                        baseline_pass=base_result.passed if base_result else None,
                        current_pass=None,
                        baseline_duration_ms=base_result.duration_ms if base_result else 0,
                        current_duration_ms=0,
                        notes="Scenario present in baseline but missing from current run",
                    ),
                )
            elif base_result is None:
                # New in current.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.NEW,
                        baseline_pass=None,
                        current_pass=cur_result.passed,
                        baseline_duration_ms=0,
                        current_duration_ms=cur_result.duration_ms,
                        notes="New scenario not present in baseline",
                    ),
                )
            elif cur_result.error and base_result.passed:
                # Previously passing, now errored.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.REGRESSED,
                        baseline_pass=base_result.passed,
                        current_pass=False,
                        baseline_duration_ms=base_result.duration_ms,
                        current_duration_ms=cur_result.duration_ms,
                        notes=f"Now errors: {cur_result.error}",
                    ),
                )
            elif base_result.passed and not cur_result.passed:
                # Regressed.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.REGRESSED,
                        baseline_pass=base_result.passed,
                        current_pass=cur_result.passed,
                        baseline_duration_ms=base_result.duration_ms,
                        current_duration_ms=cur_result.duration_ms,
                        notes=(
                            f"Expected {base_result.passed}, got {cur_result.actual_pass}"
                            if cur_result.actual_pass is not None
                            else "Evaluation failed"
                        ),
                    ),
                )
            elif not base_result.passed and cur_result.passed:
                # Improved.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.IMPROVED,
                        baseline_pass=base_result.passed,
                        current_pass=cur_result.passed,
                        baseline_duration_ms=base_result.duration_ms,
                        current_duration_ms=cur_result.duration_ms,
                        notes="Previously failing scenario now passes",
                    ),
                )
            elif cur_result.error:
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.ERRORED,
                        baseline_pass=base_result.passed,
                        current_pass=False,
                        baseline_duration_ms=base_result.duration_ms,
                        current_duration_ms=cur_result.duration_ms,
                        notes=f"Error: {cur_result.error}",
                    ),
                )
            else:
                # Unchanged.
                entries.append(
                    EvalDiffEntry(
                        scenario_name=name,
                        status=DiffStatus.UNCHANGED,
                        baseline_pass=base_result.passed,
                        current_pass=cur_result.passed,
                        baseline_duration_ms=base_result.duration_ms,
                        current_duration_ms=cur_result.duration_ms,
                        notes="",
                    ),
                )

        regressions = sum(1 for e in entries if e.status == DiffStatus.REGRESSED)
        improvements = sum(1 for e in entries if e.status == DiffStatus.IMPROVED)
        unchanged = sum(1 for e in entries if e.status == DiffStatus.UNCHANGED)
        new = sum(1 for e in entries if e.status == DiffStatus.NEW)
        removed = sum(1 for e in entries if e.status == DiffStatus.REMOVED)

        return EvalDiff(
            suite_name=current.suite_name,
            baseline_timestamp=baseline.timestamp,
            current_timestamp=current.timestamp,
            entries=entries,
            total=len(entries),
            regressions=regressions,
            improvements=improvements,
            unchanged=unchanged,
            new=new,
            removed=removed,
        )

    def _all_new(self, current: EvalResult) -> EvalDiff:
        """Build a diff where every scenario is new (no baseline)."""
        entries = [
            EvalDiffEntry(
                scenario_name=r.scenario_name,
                status=DiffStatus.NEW,
                baseline_pass=None,
                current_pass=r.passed,
                current_duration_ms=r.duration_ms,
                notes="No baseline — initial run",
            )
            for r in current.scenarios
        ]
        return EvalDiff(
            suite_name=current.suite_name,
            current_timestamp=current.timestamp,
            entries=entries,
            total=len(entries),
            new=len(entries),
        )
