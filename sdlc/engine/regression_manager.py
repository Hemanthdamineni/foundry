"""Regression manager — rolling regression suite, benchmark baselines, historical comparison.

Responsibilities:
- Maintain a rolling regression test suite
- Track benchmark baselines with tolerance bands
- Historical failure pattern comparison
- API compatibility validation across versions
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.regression_manager")


class RegressionEntry(BaseModel):
    """A single regression test entry with historical data."""

    test_id: str
    name: str
    command: str = ""
    category: str = "unit"  # unit, integration, performance, security, api
    baseline_passed: bool = True
    baseline_duration_ms: float = 0.0
    baseline_coverage: float = 0.0
    last_run_passed: bool | None = None
    last_run_duration_ms: float = 0.0
    failure_count: int = 0
    consecutive_passes: int = 0
    last_failure_reason: str = ""
    created_at: str = ""
    updated_at: str = ""


class BenchmarkBaseline(BaseModel):
    """A performance benchmark with tolerance bands."""

    name: str
    baseline_ms: float
    tolerance_percent: float = 15.0  # Allow 15% regression
    samples: list[float] = Field(default_factory=list)
    trend: str = "stable"  # improving, stable, degrading

    @property
    def upper_bound(self) -> float:
        return self.baseline_ms * (1 + self.tolerance_percent / 100)

    @property
    def mean(self) -> float:
        if not self.samples:
            return self.baseline_ms
        return sum(self.samples) / len(self.samples)


class APIContract(BaseModel):
    """An API compatibility contract for version tracking."""

    module: str
    version: str
    public_symbols: list[str] = Field(default_factory=list)
    type_signatures: dict[str, str] = Field(default_factory=dict)


class RegressionReport(BaseModel):
    """Report from a regression analysis run."""

    timestamp: str = ""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    new_failures: int = 0
    fixed: int = 0
    performance_regressions: int = 0
    api_breaks: int = 0
    details: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.new_failures == 0 and self.api_breaks == 0


class RegressionManager:
    """Manages the rolling regression suite with baselines and historical comparison."""

    def __init__(self, state_dir: str | Path = "data/regression") -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._suite: dict[str, RegressionEntry] = {}
        self._benchmarks: dict[str, BenchmarkBaseline] = {}
        self._api_contracts: dict[str, APIContract] = {}
        self._history: list[RegressionReport] = []

    # ── Suite Management ────────────────────────────────────────

    def register_test(
        self,
        test_id: str,
        name: str,
        *,
        command: str = "",
        category: str = "unit",
    ) -> RegressionEntry:
        """Register a test in the regression suite."""
        entry = RegressionEntry(
            test_id=test_id,
            name=name,
            command=command,
            category=category,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._suite[test_id] = entry
        return entry

    def record_result(
        self,
        test_id: str,
        *,
        passed: bool,
        duration_ms: float = 0.0,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        """Record a test result and detect regressions."""
        entry = self._suite.get(test_id)
        if entry is None:
            return {"error": f"Test not registered: {test_id}"}

        was_passing = entry.last_run_passed
        entry.last_run_passed = passed
        entry.last_run_duration_ms = duration_ms
        entry.updated_at = datetime.now(UTC).isoformat()

        regression = False
        fixed = False

        if passed:
            entry.consecutive_passes += 1
            if was_passing is False:
                fixed = True
        else:
            entry.failure_count += 1
            entry.consecutive_passes = 0
            entry.last_failure_reason = failure_reason
            if was_passing is True:
                regression = True

        return {
            "test_id": test_id,
            "passed": passed,
            "regression": regression,
            "fixed": fixed,
            "duration_ms": duration_ms,
            "failure_count": entry.failure_count,
        }

    # ── Benchmark Baselines ─────────────────────────────────────

    def set_benchmark_baseline(
        self,
        name: str,
        baseline_ms: float,
        tolerance_percent: float = 15.0,
    ) -> BenchmarkBaseline:
        """Set a performance benchmark baseline."""
        benchmark = BenchmarkBaseline(
            name=name,
            baseline_ms=baseline_ms,
            tolerance_percent=tolerance_percent,
        )
        self._benchmarks[name] = benchmark
        return benchmark

    def record_benchmark(self, name: str, elapsed_ms: float) -> dict[str, Any]:
        """Record a benchmark sample and check for regression."""
        benchmark = self._benchmarks.get(name)
        if benchmark is None:
            return {"error": f"Benchmark not registered: {name}"}

        benchmark.samples.append(elapsed_ms)
        # Keep last 50 samples
        if len(benchmark.samples) > 50:
            benchmark.samples = benchmark.samples[-50:]

        # Update trend
        if len(benchmark.samples) >= 5:
            recent = benchmark.samples[-5:]
            older = benchmark.samples[-10:-5] if len(benchmark.samples) >= 10 else [benchmark.baseline_ms]
            recent_mean = sum(recent) / len(recent)
            older_mean = sum(older) / len(older)
            if recent_mean > older_mean * 1.1:
                benchmark.trend = "degrading"
            elif recent_mean < older_mean * 0.9:
                benchmark.trend = "improving"
            else:
                benchmark.trend = "stable"

        regression = elapsed_ms > benchmark.upper_bound
        return {
            "name": name,
            "elapsed_ms": elapsed_ms,
            "baseline_ms": benchmark.baseline_ms,
            "upper_bound": benchmark.upper_bound,
            "regression": regression,
            "trend": benchmark.trend,
            "mean": round(benchmark.mean, 2),
        }

    # ── API Compatibility ───────────────────────────────────────

    def register_api_contract(
        self,
        module: str,
        version: str,
        public_symbols: list[str],
        type_signatures: dict[str, str] | None = None,
    ) -> APIContract:
        """Register an API compatibility contract."""
        contract = APIContract(
            module=module,
            version=version,
            public_symbols=public_symbols,
            type_signatures=type_signatures or {},
        )
        self._api_contracts[module] = contract
        return contract

    def check_api_compatibility(
        self,
        module: str,
        current_symbols: list[str],
    ) -> dict[str, Any]:
        """Check if current API is compatible with registered contract."""
        contract = self._api_contracts.get(module)
        if contract is None:
            return {"status": "no_contract", "module": module}

        removed = [s for s in contract.public_symbols if s not in current_symbols]
        added = [s for s in current_symbols if s not in contract.public_symbols]

        return {
            "module": module,
            "compatible": len(removed) == 0,
            "removed_symbols": removed,
            "added_symbols": added,
            "breaking": len(removed) > 0,
        }

    # ── Regression Analysis ─────────────────────────────────────

    def run_analysis(self) -> RegressionReport:
        """Generate a regression analysis report."""
        report = RegressionReport(
            timestamp=datetime.now(UTC).isoformat(),
            total_tests=len(self._suite),
        )

        for entry in self._suite.values():
            if entry.last_run_passed is True:
                report.passed += 1
            elif entry.last_run_passed is False:
                report.failed += 1
                if entry.baseline_passed and entry.failure_count == 1:
                    report.new_failures += 1
                    report.details.append({
                        "type": "new_failure",
                        "test_id": entry.test_id,
                        "name": entry.name,
                        "reason": entry.last_failure_reason,
                    })

        for benchmark in self._benchmarks.values():
            if benchmark.samples and benchmark.samples[-1] > benchmark.upper_bound:
                report.performance_regressions += 1
                report.details.append({
                    "type": "performance_regression",
                    "benchmark": benchmark.name,
                    "baseline_ms": benchmark.baseline_ms,
                    "current_ms": benchmark.samples[-1],
                    "trend": benchmark.trend,
                })

        self._history.append(report)
        return report

    # ── Persistence ─────────────────────────────────────────────

    def save(self) -> None:
        """Persist regression state to disk."""
        data = {
            "suite": {tid: e.model_dump() for tid, e in self._suite.items()},
            "benchmarks": {n: b.model_dump() for n, b in self._benchmarks.items()},
            "api_contracts": {m: c.model_dump() for m, c in self._api_contracts.items()},
        }
        path = self._state_dir / "regression_state.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.rename(path)

    def load(self) -> bool:
        """Load regression state from disk."""
        path = self._state_dir / "regression_state.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for tid, entry_data in data.get("suite", {}).items():
                self._suite[tid] = RegressionEntry(**entry_data)
            for name, bench_data in data.get("benchmarks", {}).items():
                self._benchmarks[name] = BenchmarkBaseline(**bench_data)
            for module, contract_data in data.get("api_contracts", {}).items():
                self._api_contracts[module] = APIContract(**contract_data)
            return True
        except (json.JSONDecodeError, KeyError):
            return False
