"""Security scanning gate — optional semgrep/bandit wrapper.

Provides a configurable security scanning gate that runs ``semgrep`` or
``bandit`` on the workspace path.  Disabled by default — enable via the
``SDLC_SECURITY_GATE_ENABLED`` environment variable.

Tool selection is governed by ``SDLC_SECURITY_TOOL``:
  - ``"semgrep"`` — use semgrep only
  - ``"bandit"`` — use bandit only
  - ``"auto"`` (default) — try semgrep first, fall back to bandit

Minimum severity can be set via ``SDLC_SECURITY_MIN_SEVERITY``
(default ``"medium"``).  Findings below this threshold are ignored.

If neither tool is installed, the gate is skipped gracefully.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger
from foundry.features.sdlc_runtime.runtime.tool_gate import GateResult

logger = get_logger("runtime.security_gate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_SEVERITY = "medium"

# Severity ordering (highest to lowest)
SEVERITY_ORDER = ["critical", "high", "medium", "low"]

# Environment variable names
ENV_ENABLED = "SDLC_SECURITY_GATE_ENABLED"
ENV_TOOL = "SDLC_SECURITY_TOOL"
ENV_MIN_SEVERITY = "SDLC_SECURITY_MIN_SEVERITY"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _severity_index(severity: str) -> int:
    """Return a numeric rank for *severity* (lower = more severe)."""
    sev = severity.lower().strip()
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return len(SEVERITY_ORDER)  # unknown → lowest


def _meets_min_severity(severity: str, min_severity: str) -> bool:
    """Return ``True`` if *severity* is at least as severe as *min_severity*."""
    return _severity_index(severity) <= _severity_index(min_severity)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Check if the security scanning gate is enabled.

    Reads the ``SDLC_SECURITY_GATE_ENABLED`` environment variable.
    Returns ``True`` for values ``1``, ``true``, ``yes`` (case-insensitive).
    """
    val = os.environ.get(ENV_ENABLED, "").lower().strip()
    return val in ("1", "true", "yes", "enabled")


def get_tool() -> str:
    """Get the configured security scanning tool.

    Reads ``SDLC_SECURITY_TOOL``.  Valid values: ``"semgrep"``,
    ``"bandit"``, ``"auto"``.  Falls back to ``"auto"``.
    """
    val = os.environ.get(ENV_TOOL, "auto").lower().strip()
    if val in ("semgrep", "bandit", "auto"):
        return val
    logger.warning("Unknown SDLC_SECURITY_TOOL %r, falling back to 'auto'", val)
    return "auto"


def get_min_severity() -> str:
    """Get the configured minimum severity threshold.

    Reads ``SDLC_SECURITY_MIN_SEVERITY``.  Valid values: ``"low"``,
    ``"medium"``, ``"high"``, ``"critical"``.  Falls back to ``"medium"``.
    """
    val = os.environ.get(ENV_MIN_SEVERITY, DEFAULT_MIN_SEVERITY).lower().strip()
    if val in SEVERITY_ORDER:
        return val
    logger.warning(
        "Unknown SDLC_SECURITY_MIN_SEVERITY %r, falling back to '%s'",
        val,
        DEFAULT_MIN_SEVERITY,
    )
    return DEFAULT_MIN_SEVERITY


# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------


def _semgrep_available() -> bool:
    """Check whether ``semgrep`` is installed and on ``PATH``."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "semgrep", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _bandit_available() -> bool:
    """Check whether ``bandit`` is installed and on ``PATH``."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "bandit", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _resolve_tool() -> str | None:
    """Resolve which security tool to use based on config and availability.

    Returns ``"semgrep"``, ``"bandit"``, or ``None`` if no tool is available.
    """
    preferred = get_tool()

    if preferred == "semgrep":
        return "semgrep" if _semgrep_available() else None

    if preferred == "bandit":
        return "bandit" if _bandit_available() else None

    # "auto" — try semgrep first, fall back to bandit
    if _semgrep_available():
        return "semgrep"
    if _bandit_available():
        return "bandit"
    return None


# ---------------------------------------------------------------------------
# Semgrep runner
# ---------------------------------------------------------------------------


def _run_semgrep(workspace_path: str) -> tuple[list[dict[str, Any]], str, str]:
    """Run ``semgrep`` with security rules on *workspace_path*.

    Returns ``(findings, output_summary, errors)``.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "semgrep",
                "--config", "auto",
                "--json",
                "--quiet",
                "--no-error",
                workspace_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return [], "", "semgrep scan timed out after 120s"
    except FileNotFoundError:
        return [], "", "semgrep binary not found"
    except OSError as exc:
        return [], "", f"semgrep execution failed: {exc}"

    output = result.stdout
    errors = result.stderr

    if not output.strip():
        return [], "", errors or "semgrep produced no output"

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return [], output[:2000], f"Failed to parse semgrep output: {exc}"

    results_raw = data.get("results", []) if isinstance(data, dict) else []
    findings: list[dict[str, Any]] = []
    for r in results_raw:
        severity = r.get("extra", {}).get("severity", "unknown").lower()
        path = r.get("path", "")
        line = r.get("start", {}).get("line", 0) if isinstance(r.get("start"), dict) else 0
        check_id = r.get("check_id", "unknown")
        message = r.get("extra", {}).get("message", "") if isinstance(r.get("extra"), dict) else ""

        findings.append({
            "tool": "semgrep",
            "severity": severity,
            "file": path,
            "line": line,
            "check_id": check_id,
            "message": message.strip(),
        })

    return findings, output, errors


# ---------------------------------------------------------------------------
# Bandit runner
# ---------------------------------------------------------------------------


def _run_bandit(workspace_path: str) -> tuple[list[dict[str, Any]], str, str]:
    """Run ``bandit`` on *workspace_path*.

    Returns ``(findings, output_summary, errors)``.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "bandit",
                "-r", workspace_path,
                "-f", "json",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return [], "", "bandit scan timed out after 120s"
    except FileNotFoundError:
        return [], "", "bandit binary not found"
    except OSError as exc:
        return [], "", f"bandit execution failed: {exc}"

    output = result.stdout
    errors = result.stderr

    if not output.strip():
        return [], "", errors or "bandit produced no output"

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return [], output[:2000], f"Failed to parse bandit output: {exc}"

    results_raw = data.get("results", []) if isinstance(data, dict) else []
    findings: list[dict[str, Any]] = []
    for r in results_raw:
        severity = r.get("issue_severity", "unknown").lower()
        path = r.get("filename", "")
        line = r.get("line_number", 0)
        test_id = r.get("test_id", "unknown")
        issue_text = r.get("issue_text", "").strip()

        findings.append({
            "tool": "bandit",
            "severity": severity,
            "file": path,
            "line": line,
            "check_id": test_id,
            "message": issue_text,
        })

    return findings, output, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_security_gate(
    gate_name: str,
    workspace_path: str,
) -> GateResult:
    """Run the security scanning gate.

    Steps:
    1. Check if the gate is enabled (env var).  If not, returns skipped.
    2. Resolve which tool(s) to use.  If none installed, returns skipped.
    3. Run the security scanner (semgrep or bandit) on *workspace_path*.
    4. Filter findings by the configured minimum severity.
    5. Return ``GateResult`` — passed when no qualifying findings exist.

    Args:
        gate_name: The logical name for this gate (e.g. ``"security"``).
        workspace_path: Absolute or relative path to the workspace root.

    Returns:
        A ``GateResult`` with the appropriate pass / fail / skip status.
    """
    # ── Early skip if gate is not enabled ──────────────────────────────────
    if not is_enabled():
        return GateResult(
            gate=gate_name,
            tool="security",
            passed=True,
            skipped=True,
            skip_reason=(
                f"Security gate disabled (set {ENV_ENABLED}=1 to enable)"
            ),
        )

    # ── Resolve tool ───────────────────────────────────────────────────────
    tool = _resolve_tool()
    if tool is None:
        return GateResult(
            gate=gate_name,
            tool="security",
            passed=True,
            skipped=True,
            skip_reason=(
                "Security gate skipped — neither 'semgrep' nor 'bandit' "
                "is installed.  Install one of them and set "
                f"{ENV_ENABLED}=1 to enable this gate."
            ),
        )

    workspace = Path(workspace_path)
    if not workspace.is_dir():
        return GateResult(
            gate=gate_name,
            tool=tool,
            passed=False,
            errors=f"Workspace path does not exist or is not a directory: {workspace_path}",
            failure_class="permanent",
        )

    # ── Run the scanner ────────────────────────────────────────────────────
    min_severity = get_min_severity()

    try:
        if tool == "semgrep":
            findings, output, errors = _run_semgrep(str(workspace))
        else:
            findings, output, errors = _run_bandit(str(workspace))

        # ── Filter by severity ─────────────────────────────────────────────
        filtered = [
            f for f in findings
            if _meets_min_severity(f.get("severity", "low"), min_severity)
        ]

        if not filtered:
            return GateResult(
                gate=gate_name,
                tool=tool,
                passed=True,
                output=(
                    f"No security findings above '{min_severity}' severity "
                    f"({len(findings)} total findings filtered)"
                ),
                duration_ms=0.0,
            )

        # ── Summarise findings ─────────────────────────────────────────────
        by_sev: dict[str, int] = {}
        for f in filtered:
            sev = f.get("severity", "unknown")
            by_sev[sev] = by_sev.get(sev, 0) + 1

        critical = by_sev.get("critical", 0)
        high = by_sev.get("high", 0)
        total = len(filtered)

        detail_lines: list[str] = []
        for f in filtered[:20]:
            detail_lines.append(
                f"  {f.get('file', '')}:{f.get('line', 0)} "
                f"[{f.get('severity', '?')}] "
                f"{f.get('check_id', 'Unknown')}: {f.get('message', '')}"
            )
        output_summary = (
            f"Found {total} security issue(s) "
            f"({critical} critical, {high} high)\n"
            + "\n".join(detail_lines)
        )
        if len(filtered) > 20:
            output_summary += f"\n  ... and {len(filtered) - 20} more finding(s)"

        errors_text = errors if errors else f"{total} security issue(s) detected"

        return GateResult(
            gate=gate_name,
            tool=tool,
            passed=False,
            output=output_summary[:2000],
            errors=errors_text[:500],
            duration_ms=0.0,
            failure_class="permanent",
        )

    except Exception as exc:
        logger.error(
            "Security gate failed unexpectedly",
            extra={"error": str(exc)},
        )
        return GateResult(
            gate=gate_name,
            tool=tool,
            passed=False,
            errors=f"Unexpected error: {exc}",
            failure_class="transient",
        )
