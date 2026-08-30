"""EvalRunner — orchestrates scenario execution against judge and debate.

Uses ``sdlc_judge.JudgeEngine`` for single-phase evaluation and
``sdlc_debate.DebateRuntime`` for multi-agent debate evaluation.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sdlc_debate import DebateRuntime
from sdlc_judge import JudgeEngine
from sdlc_judge.base import LLMProvider
from sdlc_models.judge import JudgeVerdict
from sdlc_models.debate import DebateTranscript
from sdlc_models.phases import BudgetPolicy, Task

from foundry.features.eval_harness.suites.base import EvalScenario, EvalSuite


class EvalScenarioResult(BaseModel):
    """Outcome of evaluating a single scenario.

    Attributes
    ----------
    scenario_name:
        Matches ``EvalScenario.name``.
    passed:
        ``True`` when the scenario's expected outcome matches the actual
        result (or when no expectation is set and the evaluation did not
        error).
    judge_verdict:
        The structured verdict returned by the JudgeEngine, if used.
    debate_transcript:
        The full debate transcript, if debate was used.
    actual_pass:
        The raw pass/fail from the evaluation (before comparing to
        *expected*).
    error:
        Error message if the evaluation itself failed.
    duration_ms:
        Wall-clock time for this scenario in milliseconds.
    metadata:
        Arbitrary extra data collected during evaluation.
    """

    scenario_name: str
    passed: bool = False
    judge_verdict: JudgeVerdict | None = None
    debate_transcript: DebateTranscript | None = None
    actual_pass: bool | None = None
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """Aggregated result of running a full suite.

    Attributes
    ----------
    suite_name:
        Matches ``EvalSuite.name``.
    timestamp:
        When the run completed.
    scenarios:
        Per-scenario results in the same order as the suite.
    total:
        Number of scenarios evaluated.
    passed:
        Number of scenarios that passed.
    failed:
        Number of scenarios that failed.
    errors:
        Number of scenarios that errored during evaluation.
    metadata:
        Arbitrary extra data about the run (model info, provider
        details, etc.).
    """

    suite_name: str
    timestamp: str = ""
    scenarios: list[EvalScenarioResult] = Field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalRunner:
    """Executes evaluation scenarios against judge and debate engines.

    Parameters
    ----------
    judge_provider:
        LLMProvider for the JudgeEngine.
    debate_provider:
        LLMProvider for the DebateRuntime (may be the same instance).
    judge_model:
        Model identifier for the judge.
    debate_model:
        Model identifier for debate agents.
    max_debate_rounds:
        Maximum debate rounds per scenario.
    """

    def __init__(
        self,
        judge_provider: LLMProvider,
        debate_provider: LLMProvider,
        judge_model: str = "qwen3:8b",
        debate_model: str = "qwen3:8b",
        max_debate_rounds: int = 3,
    ) -> None:
        self._judge = JudgeEngine(provider=judge_provider, model=judge_model)
        self._debate = DebateRuntime(provider=debate_provider, model=debate_model)
        self._judge_model = judge_model
        self._debate_model = debate_model
        self._max_debate_rounds = max_debate_rounds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_suite(
        self,
        suite: EvalSuite,
        task: Task | None = None,
        use_debate: bool = False,
    ) -> EvalResult:
        """Evaluate every scenario in *suite* and return an aggregated result.

        Parameters
        ----------
        suite:
            The suite to run.
        task:
            Optional ``Task`` to pass to judge/debate engines.  A minimal
            default is constructed when ``None``.
        use_debate:
            When ``True``, each scenario runs through the full debate
            protocol in addition to the judge.
        """
        if task is None:
            task = self._default_task()

        scenario_results: list[EvalScenarioResult] = []
        for scenario in suite.scenarios:
            result = await self._evaluate_scenario(scenario, task, use_debate)
            scenario_results.append(result)

        total = len(scenario_results)
        passed = sum(1 for r in scenario_results if r.passed)
        failed = sum(1 for r in scenario_results if not r.passed and r.error is None)
        errors_count = sum(1 for r in scenario_results if r.error is not None)

        return EvalResult(
            suite_name=suite.name,
            timestamp=datetime.now(UTC).isoformat(),
            scenarios=scenario_results,
            total=total,
            passed=passed,
            failed=failed,
            errors=errors_count,
            metadata={
                "judge_model": self._judge_model,
                "debate_model": self._debate_model,
                "use_debate": use_debate,
                "max_debate_rounds": self._max_debate_rounds,
            },
        )

    def list_suites(self, suites: dict[str, EvalSuite]) -> list[dict[str, str | int]]:
        """Return a summary of available suites for CLI display."""
        return [
            {
                "name": s.name,
                "description": s.description or "",
                "scenarios": len(s.scenarios),
            }
            for s in suites.values()
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _evaluate_scenario(
        self,
        scenario: EvalScenario,
        task: Task,
        use_debate: bool,
    ) -> EvalScenarioResult:
        """Evaluate a single scenario and produce a result."""
        started = time.perf_counter()
        error: str | None = None
        judge_verdict: JudgeVerdict | None = None
        debate_transcript: DebateTranscript | None = None
        actual_pass: bool | None = None

        try:
            from_phase = scenario.from_phase or scenario.phase

            judge_verdict = await self._judge.evaluate(
                task=task,
                from_phase=from_phase,
                to_phase=scenario.to_phase,
                output=scenario.input,
            )
            actual_pass = judge_verdict.passed

            if use_debate:
                debate_transcript = await self._debate.run_debate(
                    task=task,
                    phase=scenario.phase,
                    output=scenario.input,
                )
                if debate_transcript.consensus is not None:
                    actual_pass = actual_pass and debate_transcript.consensus.passed

        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

        duration_ms = int((time.perf_counter() - started) * 1000)

        # Determine pass/fail relative to expected result.
        if error is not None:
            passed = False
        elif scenario.expected_pass is None:
            passed = True  # No expectation — success if no error.
        else:
            passed = actual_pass == scenario.expected_pass

        return EvalScenarioResult(
            scenario_name=scenario.name,
            passed=passed,
            judge_verdict=judge_verdict,
            debate_transcript=debate_transcript,
            actual_pass=actual_pass,
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _default_task() -> Task:
        """Create a minimal Task suitable for evaluation harness use."""
        return Task(
            task_id="eval-harness",
            description="Eval harness run",
            budget=BudgetPolicy(max_debate_rounds=3),
        )
