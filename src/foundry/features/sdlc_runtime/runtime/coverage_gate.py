"""Coverage gate — optional, configurable threshold.

Provides a test coverage gate that verifies code coverage meets a minimum
threshold before a phase can pass.  Disabled by default — enable via the
``SDLC_COVERAGE_GATE_ENABLED`` environment variable.

The coverage threshold is configurable via ``SDLC_COVERAGE_THRESHOLD``
(default ``80.0``, meaning 80 %).

If the ``coverage`` package (or ``pytest-cov``) is not installed, the gate
is skipped gracefully so that existing workflows are not disrupted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger
from foundry.features.sdlc_runtime.runtime.tool_gate import GateResult

logger = get_logger("runtime.coverage_gate")

DEFAULT_COVERAGE_THRESHOLD = 80.0

# Environment variable names
ENV_ENABLED = "SDLC_COVERAGE_GATE_ENABLED"
ENV_THRESHOLD = "SDLC_COVERAGE_THRESHOLD"


def is_enabled() -> bool:
    """Check if the coverage gate is enabled.

    Reads the ``SDLC_COVERAGE_GATE_ENABLED`` environment variable.
    Returns ``True`` for values ``1``, ``true``, ``yes`` (case-insensitive).
    """
    val = os.environ.get(ENV_ENABLED, "").lower().strip()
    return val in ("1", "true", "yes")


def get_threshold() -> float:
    """Get the configured coverage threshold.

    Reads the ``SDLC_COVERAGE_THRESHOLD`` environment variable.  Falls
    back to ``DEFAULT_COVERAGE_THRESHOLD`` (80.0) if the value is missing
    or unparseable.
    """
    val = os.environ.get(ENV_THRESHOLD, str(DEFAULT_COVERAGE_THRESHOLD))
    try:
        return float(val)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid coverage threshold %r, using default %s",
            val,
            DEFAULT_COVERAGE_THRESHOLD,
        )
        return DEFAULT_COVERAGE_THRESHOLD


def _coverage_available() -> bool:
    """Check whether coverage measurement tools are installed.

    Tries importing ``coverage`` first (the standalone ``coverage.py``
    package), then falls back to checking for ``pytest_cov``.
    """
    try:
        import coverage  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import pytest_cov  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def _parse_coverage_percentage(report: str) -> float | None:
    """Parse the total coverage percentage from a ``coverage report`` output.

    The expected format of the TOTAL line is::

        TOTAL        1234    567    78%

    Returns:
        The coverage percentage as a float, or ``None`` if it cannot be
        parsed (e.g. because no data was collected).
    """
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("TOTAL"):
            parts = stripped.split()
            # The percentage is the last column before potential trailing
            # whitespace: ``TOTAL  n  m  87%``  →  parts[-1] == "87%"
            if len(parts) >= 4:
                pct_str = parts[-1].rstrip("%")
                try:
                    return float(pct_str)
                except ValueError:
                    continue
    return None


async def run_coverage_gate(
    gate_name: str,
    workspace_path: str,
) -> GateResult:
    """Run coverage measurement and check against the configured threshold.

    This function:
    1. Checks if the gate is enabled (env var).  If not, returns skipped.
    2. Checks if a coverage tool is installed.  If not, returns skipped.
    3. Runs ``coverage run -m pytest`` in the workspace.
    4. Generates a ``coverage report`` and parses the total percentage.
    5. Compares against the configured threshold.

    Args:
        gate_name: The logical name for this gate (e.g. ``"coverage"``).
        workspace_path: Absolute or relative path to the workspace root.

    Returns:
        A ``GateResult`` with the appropriate pass / fail / skip status.
    """
    # ── Early skip if gate is not enabled ──────────────────────────────────
    if not is_enabled():
        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=True,
            skipped=True,
            skip_reason=(
                f"Coverage gate disabled (set {ENV_ENABLED}=1 to enable)"
            ),
        )

    # ── Early skip if coverage tooling is not installed ────────────────────
    if not _coverage_available():
        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=True,
            skipped=True,
            skip_reason=(
                "Coverage gate skipped — neither 'coverage' nor 'pytest-cov' "
                "is installed.  Install one of them and set "
                f"{ENV_ENABLED}=1 to enable this gate."
            ),
        )

    threshold = get_threshold()
    workspace = Path(workspace_path)

    try:
        # ── Phase 1: run tests with coverage ───────────────────────────────
        run_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "-m",
                "pytest",
                str(workspace),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(workspace),
        )

        # ── Phase 2: generate the report ──────────────────────────────────
        report_result = subprocess.run(
            [sys.executable, "-m", "coverage", "report"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(workspace),
        )

        output = report_result.stdout
        errors = report_result.stderr
        if run_result.stderr:
            errors = (errors + "\n" + run_result.stderr).strip()

        coverage_pct = _parse_coverage_percentage(output)

        if coverage_pct is None:
            return GateResult(
                gate=gate_name,
                tool="coverage",
                passed=False,
                output=output[:2000],
                errors="Could not parse coverage percentage from report. "
                "Ensure tests produce measurable coverage data.",
                failure_class="permanent",
            )

        if coverage_pct >= threshold:
            return GateResult(
                gate=gate_name,
                tool="coverage",
                passed=True,
                output=(
                    f"Coverage: {coverage_pct:.1f}% "
                    f"(threshold: {threshold:.1f}%)"
                ),
                duration_ms=0.0,
            )

        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=False,
            output=output[:2000],
            errors=(
                f"Coverage {coverage_pct:.1f}% is below threshold "
                f"{threshold:.1f}%"
            ),
            failure_class="permanent",
        )

    except subprocess.TimeoutExpired:
        logger.warning("Coverage gate timed out for %s", workspace_path)
        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=False,
            errors="Coverage measurement timed out after 300s",
            failure_class="timeout",
        )
    except FileNotFoundError:
        logger.warning("Coverage binary not found for %s", workspace_path)
        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=False,
            errors="Coverage tool binary not found",
            failure_class="not_found",
        )
    except Exception as exc:
        logger.error(
            "Coverage gate failed unexpectedly",
            extra={"error": str(exc)},
        )
        return GateResult(
            gate=gate_name,
            tool="coverage",
            passed=False,
            errors=f"Unexpected error: {exc}",
            failure_class="transient",
        )
