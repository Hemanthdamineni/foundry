"""Tests for the ``foundry eval`` CLI commands."""

from __future__ import annotations

from foundry.cli.evaluate import build_parser, cmd_list, cmd_run


def _parse_args(cmd: str, *args: str) -> object:
    """Helper to parse CLI arguments for a subcommand."""
    parser = build_parser()
    return parser.parse_args([cmd, *args])


class TestEvalCliList:
    """``foundry eval list`` subcommand."""

    def test_list_suites(self) -> None:
        """list runs without error and returns 0."""
        args = _parse_args("list")
        rc = cmd_list(args)
        assert rc == 0

    def test_list_output_includes_expected_suites(self, capsys) -> None:
        """Built-in suite names appear in output."""
        args = _parse_args("list")
        cmd_list(args)
        captured = capsys.readouterr()
        assert "specs-regression" in captured.out
        assert "coding-regression" in captured.out
        assert "review-regression" in captured.out


class TestEvalCliRun:
    """``foundry eval run`` subcommand."""

    def test_run_unknown_suite(self) -> None:
        """Unknown suite name exits with code 1."""
        args = _parse_args("run", "nonexistent")
        rc = cmd_run(args)
        assert rc == 1

    def test_run_known_suite(self) -> None:
        """A known suite runs and returns a result."""
        args = _parse_args("run", "specs-regression")
        rc = cmd_run(args)
        # Uses noop provider so scenarios may "fail" on expectation mismatch
        # but the command itself should complete.
        assert rc in (0, 1)

    def test_run_output_contains_suite_name(self, capsys) -> None:
        """Output includes the suite name and scenario results."""
        args = _parse_args("run", "coding-regression")
        cmd_run(args)
        captured = capsys.readouterr()
        assert "coding-regression" in captured.out


class TestEvalCliParser:
    """Argument parser structure."""

    def test_parser_list_command(self) -> None:
        """Parsing 'eval list' yields eval_command='list'."""
        parser = build_parser()
        args = parser.parse_args(["list"])
        assert args.eval_command == "list"

    def test_parser_run_command(self) -> None:
        """Parsing 'eval run foo' yields eval_command='run' and suite='foo'."""
        parser = build_parser()
        args = parser.parse_args(["run", "my-suite"])
        assert args.eval_command == "run"
        assert args.suite == "my-suite"

    def test_parser_diff_command(self) -> None:
        """Parsing 'eval diff bar' yields eval_command='diff' and suite='bar'."""
        parser = build_parser()
        args = parser.parse_args(["diff", "bar"])
        assert args.eval_command == "diff"
        assert args.suite == "bar"

    def test_parser_no_subcommand(self) -> None:
        """No subcommand should exit with error."""
        parser = build_parser()
        try:
            parser.parse_args([])
            assert False, "Expected SystemExit"
        except SystemExit:
            pass
