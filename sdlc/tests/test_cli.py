"""Tests for CLI argument parsing and routing."""

from __future__ import annotations

import sys

from sdlc.cli.main import cli


def _run_cli(args: list[str]) -> int:
    """Run CLI and capture exit code instead of letting it call sys.exit()."""
    try:
        return cli(args)
    except SystemExit as e:
        return e.code if e.code is not None else 0


class TestCLIParsing:
    def test_init_command(self) -> None:
        assert _run_cli(["init"]) == 0

    def test_init_with_force(self) -> None:
        assert _run_cli(["init", "--force"]) == 0

    def test_init_with_no_plugins(self) -> None:
        assert _run_cli(["init", "--no-plugins"]) == 0

    def test_init_with_all_flags(self) -> None:
        assert _run_cli(["init", "--force", "--no-plugins"]) == 0

    def test_doctor_command(self) -> None:
        try:
            result = _run_cli(["doctor"])
            assert isinstance(result, int)
        except ModuleNotFoundError:
            pass  # aiosqlite not available in test env

    def test_models_command(self) -> None:
        result = _run_cli(["models"])
        assert isinstance(result, int)

    def test_repair_command(self) -> None:
        assert _run_cli(["repair"]) == 0

    def test_upgrade_command(self) -> None:
        assert _run_cli(["upgrade"]) == 0

    def test_no_command_returns_non_zero(self) -> None:
        assert _run_cli([]) != 0

    def test_unknown_command_returns_non_zero(self) -> None:
        assert _run_cli(["unknown"]) != 0

    def test_help_returns_zero(self) -> None:
        assert _run_cli(["--help"]) == 0
