"""Tool gate runtime — enforced sequential tool validation gates.

TODO #14: TOOLS ARE AUTHORITATIVE. Without enforced tool gates,
"looks correct" becomes acceptable again.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.tool_gate")


class GateResult(BaseModel):
    """Result of a single gate check."""

    gate: str
    tool: str
    passed: bool
    output: str = ""
    errors: str = ""
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


class GateSequenceResult(BaseModel):
    """Result of running the full gate sequence."""

    passed: bool
    failed_at: str = ""
    gates: list[GateResult] = Field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def summary(self) -> dict[str, Any]:
        passed_gates = [g.gate for g in self.gates if g.passed]
        failed_gates = [g.gate for g in self.gates if not g.passed and not g.skipped]
        skipped_gates = [g.gate for g in self.gates if g.skipped]
        return {
            "passed": self.passed,
            "failed_at": self.failed_at,
            "passed_gates": passed_gates,
            "failed_gates": failed_gates,
            "skipped_gates": skipped_gates,
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


# Default gate order: LINT → TYPES → TESTS → COVERAGE → SECURITY → BENCHMARKS
DEFAULT_GATE_ORDER = [
    ("lint", "ruff"),
    ("types", "mypy"),
    ("tests", "pytest"),
    ("coverage", "coverage"),
    ("security", "semgrep"),
    ("benchmarks", "benchmarks"),
]


class ToolGate:
    """Sequential tool gate enforcement — tools are authoritative.

    Gates run in strict order. If a gate fails, all subsequent gates are skipped.
    Spec-aware exceptions allow certain gates to be skipped for specific phases.
    """

    def __init__(
        self,
        gate_order: list[tuple[str, str]] | None = None,
    ) -> None:
        self._gate_order = gate_order or list(DEFAULT_GATE_ORDER)
        self._exceptions: dict[str, set[str]] = {}  # phase → set of skippable gates
        self._history: list[GateSequenceResult] = []

    def set_gate_order(self, order: list[tuple[str, str]]) -> None:
        """Override the gate order."""
        self._gate_order = list(order)

    def add_exception(self, phase: str, gate: str) -> None:
        """Add a spec-aware gate exception for a phase."""
        self._exceptions.setdefault(phase, set()).add(gate)

    def get_gates_for_phase(self, phase: str) -> list[tuple[str, str]]:
        """Get the gate sequence for a phase, minus exceptions."""
        exceptions = self._exceptions.get(phase, set())
        return [(name, tool) for name, tool in self._gate_order if name not in exceptions]

    def record_gate_result(
        self,
        gate: str,
        tool: str,
        *,
        passed: bool,
        output: str = "",
        errors: str = "",
        duration_ms: float = 0.0,
    ) -> GateResult:
        """Record a single gate result."""
        return GateResult(
            gate=gate, tool=tool, passed=passed,
            output=output, errors=errors, duration_ms=duration_ms,
        )

    def evaluate_sequence(self, results: list[GateResult]) -> GateSequenceResult:
        """Evaluate a full gate sequence — fail-fast on first failure."""
        total_ms = sum(r.duration_ms for r in results)
        failed_at = ""
        all_passed = True

        for r in results:
            if not r.passed and not r.skipped:
                failed_at = r.gate
                all_passed = False
                break

        seq = GateSequenceResult(
            passed=all_passed,
            failed_at=failed_at,
            gates=results,
            total_duration_ms=total_ms,
        )
        self._history.append(seq)
        return seq

    @property
    def history(self) -> list[dict[str, Any]]:
        return [s.summary for s in self._history]
