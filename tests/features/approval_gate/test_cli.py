"""Unit tests for foundry.cli.approve."""

from __future__ import annotations

import argparse

import pytest

from foundry.cli.approve import build_parser, run_approve


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return build_parser()


class TestBuildParser:
    def test_parser_created(self, parser: argparse.ArgumentParser) -> None:
        assert parser.prog == "foundry approve"

    def test_list_flag(self, parser: argparse.ArgumentParser) -> None:
        ns = parser.parse_args(["--list"])
        assert ns.list is True

    def test_approve_option(self, parser: argparse.ArgumentParser) -> None:
        ns = parser.parse_args(["--approve", "abc123"])
        assert ns.approve == "abc123"

    def test_reject_option(self, parser: argparse.ArgumentParser) -> None:
        ns = parser.parse_args(["--reject", "abc123", "--reason", "not ready"])
        assert ns.reject == "abc123"
        assert ns.reason == "not ready"

    def test_mutual_exclusivity_not_required(self, parser: argparse.ArgumentParser) -> None:
        """All flags are optional; the parser should not error on no args."""
        ns = parser.parse_args([])
        assert ns.list is False
        assert ns.approve is None
        assert ns.reject is None


class TestRunApprove:
    def test_list_empty(self, capsys: pytest.CaptureFixture) -> None:
        ns = argparse.Namespace(list=True, approve=None, reject=None, reason="")
        rc = run_approve(ns)
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "No pending" in out

    def test_approve_missing(self, capsys: pytest.CaptureFixture) -> None:
        ns = argparse.Namespace(list=False, approve="nonexistent", reject=None, reason="")
        rc = run_approve(ns)
        out, err = capsys.readouterr()
        assert rc == 1
        assert "not found" in out or "not found" in err

    def test_reject_missing(self, capsys: pytest.CaptureFixture) -> None:
        ns = argparse.Namespace(list=False, approve=None, reject="nonexistent", reason="some reason")
        rc = run_approve(ns)
        out, err = capsys.readouterr()
        assert rc == 1
        assert "not found" in out or "not found" in err

    def test_reject_without_reason(self, capsys: pytest.CaptureFixture) -> None:
        ns = argparse.Namespace(list=False, approve=None, reject="abc123", reason="")
        rc = run_approve(ns)
        out, err = capsys.readouterr()
        assert rc == 1
        assert "--reason" in out or "--reason" in err

    def test_no_action_provided(self, capsys: pytest.CaptureFixture) -> None:
        ns = argparse.Namespace(list=False, approve=None, reject=None, reason="")
        rc = run_approve(ns)
        out, err = capsys.readouterr()
        assert rc == 1
        assert "--list" in out or "--list" in err or "specify" in out or "specify" in err
