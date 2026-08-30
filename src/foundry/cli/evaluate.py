"""``foundry eval`` CLI command — list suites, run suites, diff results.

Subcommands
-----------
list
    List available evaluation suites.
run <suite>
    Run a named suite and print results.
diff <suite>
    Compare the last run of *suite* with the current/previous run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from foundry.features.eval_harness import EvalDiffer, EvalResult, EvalRunner, EvalSuite
from foundry.features.eval_harness.suites.base import EvalScenario

# ---------------------------------------------------------------------------
# Built-in regression suites
# ---------------------------------------------------------------------------

_BUILTIN_SUITES: dict[str, EvalSuite] = {
    "specs-regression": EvalSuite(
        name="specs-regression",
        description="Regression suite for the Specs phase — validates that spec output passes basic quality gates",
        scenarios=[
            EvalScenario(
                name="complete-spec",
                input=(
                    "## Requirements\n"
                    "- User shall be able to log in with email and password\n"
                    "- Failed login attempts shall be rate-limited to 5 per minute\n"
                    "- Password reset shall require email verification\n\n"
                    "## Constraints\n"
                    "- Must support 10,000 concurrent users\n"
                    "- Response time under 200ms at P95\n"
                    "- Must pass WCAG 2.1 AA\n\n"
                    "## Out of Scope\n"
                    "- Social login (future iteration)\n"
                    "- Biometric authentication\n"
                ),
                expected_pass=True,
                phase="Specs",
                to_phase="Planning",
            ),
            EvalScenario(
                name="vague-spec",
                input=(
                    "## Requirements\n"
                    "- Make it better\n"
                    "- Add more features\n"
                    "- Improve performance\n"
                ),
                expected_pass=False,
                phase="Specs",
                to_phase="Planning",
            ),
        ],
    ),
    "coding-regression": EvalSuite(
        name="coding-regression",
        description="Regression suite for the Coding phase — validates code output quality",
        scenarios=[
            EvalScenario(
                name="valid-function",
                input=(
                    "def add(a: int, b: int) -> int:\n"
                    '    """Return the sum of a and b."""\n'
                    "    return a + b\n"
                ),
                expected_pass=True,
                phase="Coding",
                to_phase="Review",
            ),
            EvalScenario(
                name="sql-injection-risk",
                input=(
                    "def get_user(username: str) -> dict | None:\n"
                    '    """Fetch a user by username."""\n'
                    '    query = f"SELECT * FROM users WHERE username = \'{username}\'"\n'
                    "    return db.execute(query).fetchone()\n"
                ),
                expected_pass=False,
                phase="Coding",
                to_phase="Review",
            ),
        ],
    ),
    "review-regression": EvalSuite(
        name="review-regression",
        description="Regression suite for the Review phase",
        scenarios=[
            EvalScenario(
                name="thorough-review",
                input=(
                    "## Issues Found\n"
                    "- Security: SQL injection vulnerability in get_user() — "
                    "uses f-string interpolation instead of parameterized query\n"
                    "- Readability: add() lacks type hints\n\n"
                    "## Verdict: CHANGES_REQUIRED\n"
                    "The code has a critical security issue that must be fixed "
                    "before it can be merged.\n"
                ),
                expected_pass=True,
                phase="Review",
                to_phase="Testing",
            ),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Data directory for persisted eval results
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Return the directory where eval results are stored."""
    return Path.home() / ".foundry" / "eval-results"


def _result_path(suite_name: str) -> Path:
    """Return the file path for a suite's last result."""
    return _data_dir() / f"{suite_name}.json"


def _load_last_result(suite_name: str) -> EvalResult | None:
    """Load the most recent result for *suite_name*, if it exists."""
    path = _result_path(suite_name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return EvalResult.model_validate(data)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _save_result(result: EvalResult) -> None:
    """Persist an eval result to disk for later diffing."""
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    path = _result_path(result.suite_name)
    path.write_text(result.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:  # noqa: ARG001
    """List available evaluation suites."""
    if not _BUILTIN_SUITES:
        print("No evaluation suites available.")
        return 0

    print(f"{'Name':<28} {'Scenarios':>9}  Description")
    print("-" * 70)
    for name, suite in _BUILTIN_SUITES.items():
        print(f"{name:<28} {len(suite.scenarios):>9}  {suite.description}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a named suite and print results."""
    suite_name = args.suite
    if suite_name not in _BUILTIN_SUITES:
        print(f"Unknown suite: {suite_name!r}", file=sys.stderr)
        print(f"Available: {', '.join(_BUILTIN_SUITES)}", file=sys.stderr)
        return 1

    suite = _BUILTIN_SUITES[suite_name]

    print(f"Running suite {suite_name!r} ({len(suite.scenarios)} scenarios)...")

    # Build a simple synchronous runner (no real LLM provider — requires
    # the caller to configure one or the runner falls through to judge
    # defaulting behaviour).

    class _StubLLMProvider:
        async def generate(self, messages, *, model=None, temperature=0.0,
                           max_tokens=None, response_format=None) -> str: ...

        async def healthcheck(self) -> bool: ...

    class _NoopProvider(_StubLLMProvider):
        """Placeholder — real usage requires a configured LLM provider."""

        async def generate(self, messages, *, model=None, temperature=0.0,
                           max_tokens=None, response_format=None) -> str:
            return json.dumps({"passed": True, "reason": "Noop provider — replace with real LLM"})

        async def healthcheck(self) -> bool:
            return False

    import asyncio

    provider = _NoopProvider()
    runner = EvalRunner(
        judge_provider=provider,
        debate_provider=provider,
    )

    result = asyncio.run(runner.run_suite(suite))

    # Persist for diff.
    _save_result(result)

    # Print summary.
    print()
    print(f"Suite:     {result.suite_name}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Total:     {result.total}")
    print(f"Passed:    {result.passed}")
    print(f"Failed:    {result.failed}")
    print(f"Errors:    {result.errors}")
    print()
    if result.scenarios:
        print(f"{'Scenario':<48} {'Passed':>6}  {'Duration':>8}")
        print("-" * 66)
        for sr in result.scenarios:
            status = "PASS" if sr.passed else "FAIL"
            marker = "!" if sr.error else " "
            print(f"{sr.scenario_name:<48} {status:>6}  {sr.duration_ms:>6}ms{marker}")
            if sr.error:
                print(f"  Error: {sr.error}")

    return 0 if result.errors == 0 and result.failed == 0 else 1


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare the last run of a suite with the current run."""
    suite_name = args.suite
    if suite_name not in _BUILTIN_SUITES:
        print(f"Unknown suite: {suite_name!r}", file=sys.stderr)
        print(f"Available: {', '.join(_BUILTIN_SUITES)}", file=sys.stderr)
        return 1

    baseline = _load_last_result(suite_name)
    if baseline is None:
        print(f"No previous result found for suite {suite_name!r}. Run it first.")
        return 1

    # Re-run to get current.
    import asyncio

    class _StubLLMProvider:  # noqa: PLR0903
        async def generate(self, messages, *, model=None, temperature=0.0,
                           max_tokens=None, response_format=None) -> str:
            return json.dumps({"passed": True, "reason": "Noop provider — replace with real LLM"})

        async def healthcheck(self) -> bool:
            return False

    provider = _NoopProvider()
    runner = EvalRunner(
        judge_provider=provider,
        debate_provider=provider,
    )
    current = asyncio.run(runner.run_suite(_BUILTIN_SUITES[suite_name]))
    _save_result(current)

    differ = EvalDiffer()
    diff = differ.diff(current, baseline)

    print(f"Diff for suite {suite_name!r}")
    print(f"  Baseline: {diff.baseline_timestamp}")
    print(f"  Current:  {diff.current_timestamp}")
    print(f"  Regressions:  {diff.regressions}")
    print(f"  Improvements: {diff.improvements}")
    print(f"  Unchanged:    {diff.unchanged}")
    print(f"  New:          {diff.new}")
    print(f"  Removed:      {diff.removed}")
    print()

    regressions = [e for e in diff.entries if e.status == "regressed"]
    improvements = [e for e in diff.entries if e.status == "improved"]
    new_entries = [e for e in diff.entries if e.status == "new"]

    if regressions:
        print("REGRESSIONS:")
        for entry in regressions:
            print(f"  - {entry.scenario_name}: {entry.notes}")
        print()

    if improvements:
        print("IMPROVEMENTS:")
        for entry in improvements:
            print(f"  + {entry.scenario_name}")
        print()

    if new_entries:
        print(f"NEW: {len(new_entries)} scenario(s)")
        for entry in new_entries:
            print(f"  * {entry.scenario_name}")

    return 1 if diff.regressions > 0 else 0


# ---------------------------------------------------------------------------
# Parser & entry point
# ---------------------------------------------------------------------------

def build_parser(sub: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    """Build the ``foundry eval`` argument parser.

    Returns the parser when *sub* is ``None``, otherwise adds a subcommand
    to *sub* and returns the subparser.
    """
    if sub is not None:
        parser = sub.add_parser("eval", help="Evaluation harness commands")
    else:
        parser = argparse.ArgumentParser(prog="foundry eval", description="Evaluation harness")

    eval_sub = parser.add_subparsers(dest="eval_command", required=True)

    # eval list
    eval_sub.add_parser("list", help="List available evaluation suites")

    # eval run <suite>
    run_p = eval_sub.add_parser("run", help="Run an evaluation suite")
    run_p.add_argument("suite", help="Name of the suite to run")

    # eval diff <suite>
    diff_p = eval_sub.add_parser("diff", help="Compare with last run of a suite")
    diff_p.add_argument("suite", help="Name of the suite to diff")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``foundry eval``.

    Returns exit code 0 on success, 1 on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    match args.eval_command:
        case "list":
            return cmd_list(args)
        case "run":
            return cmd_run(args)
        case "diff":
            return cmd_diff(args)
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(main())
