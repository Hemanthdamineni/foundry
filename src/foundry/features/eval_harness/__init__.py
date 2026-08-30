"""Eval harness — regression evaluation for Foundry.

Provides suites of evaluation scenarios, runners that execute them against
the SDLC judge and debate engines, and differ tools for comparing results.
"""

from __future__ import annotations

from foundry.features.eval_harness.suites.base import EvalScenario, EvalSuite
from foundry.features.eval_harness.runners.runner import EvalResult, EvalScenarioResult, EvalRunner
from foundry.features.eval_harness.reports.differ import EvalDiff, EvalDiffEntry, EvalDiffer

__all__ = [
    "EvalScenario",
    "EvalSuite",
    "EvalScenarioResult",
    "EvalResult",
    "EvalRunner",
    "EvalDiff",
    "EvalDiffEntry",
    "EvalDiffer",
]
