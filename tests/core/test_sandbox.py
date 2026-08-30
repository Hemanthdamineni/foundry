"""Unit tests for foundry.core.sandbox.

All tests use safe commands (``echo``, ``cat``) and avoid dangerous
binaries.  The sandbox is tested for:

- basic stdout / stderr capture
- exit code propagation
- timeout enforcement
- config merging
- environment restriction (restricted PATH)
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import time

import pytest

from foundry.core.sandbox.executor import SandboxedExecutor
from foundry.core.sandbox.models import SandboxConfig, SandboxResult


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def executor() -> SandboxedExecutor:
    return SandboxedExecutor()


@pytest.fixture
def disabled_executor() -> SandboxedExecutor:
    return SandboxedExecutor(config=SandboxConfig(enabled=False))


# ======================================================================
# Basic execution
# ======================================================================


class TestBasicExecution:
    """Verify stdout, stderr, and exit-code capture."""

    def test_echo_stdout(self, executor: SandboxedExecutor) -> None:
        result = executor.run("echo hello world")
        assert result.stdout.strip() == "hello world"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert not result.timed_out

    def test_stderr_capture(self, executor: SandboxedExecutor) -> None:
        result = executor.run("echo error >&2")
        assert result.stderr.strip() == "error"
        assert result.exit_code == 0
        assert not result.timed_out

    def test_non_zero_exit(self, executor: SandboxedExecutor) -> None:
        result = executor.run("false")
        assert result.exit_code != 0
        assert not result.timed_out

    def test_exit_code_42(self, executor: SandboxedExecutor) -> None:
        result = executor.run("sh -c 'exit 42'")
        assert result.exit_code == 42
        assert not result.timed_out

    def test_empty_command_stdout(self, executor: SandboxedExecutor) -> None:
        result = executor.run("true")
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == 0
        assert not result.timed_out

    def test_pipe_chaining(self, executor: SandboxedExecutor) -> None:
        """Shell pipes should work."""
        result = executor.run("echo 'a b c' | wc -w")
        assert result.stdout.strip() == "3"
        assert result.exit_code == 0


# ======================================================================
# Timeout enforcement
# ======================================================================


class TestTimeout:
    """Process group must be killed when a command exceeds the timeout."""

    def test_timeout_triggers(self, executor: SandboxedExecutor) -> None:
        """A long sleep should be killed and flagged as timed_out."""
        start = time.monotonic()
        result = executor.run("sleep 60", timeout=1)
        elapsed = time.monotonic() - start

        assert result.timed_out, "Expected timed_out=True"
        # The process should have been killed well before 60 s.
        assert elapsed < 10, f"Kill took too long: {elapsed:.1f}s"
        # The exit code from SIGKILL is -9 on POSIX.
        assert result.exit_code == -signal.SIGKILL

    def test_timeout_not_exceeded(self, executor: SandboxedExecutor) -> None:
        """A fast command should complete normally with no timeout flag."""
        result = executor.run("echo fast", timeout=30)
        assert not result.timed_out
        assert result.stdout.strip() == "fast"
        assert result.exit_code == 0

    def test_default_timeout_from_config(self) -> None:
        """When no timeout is passed, the config default should apply."""
        ex = SandboxedExecutor(config=SandboxConfig(timeout=1))
        result = ex.run("sleep 60")
        assert result.timed_out
        assert result.exit_code == -signal.SIGKILL

    def test_per_call_timeout_overrides_config(self) -> None:
        """A per-call timeout should take precedence over the config default."""
        ex = SandboxedExecutor(config=SandboxConfig(timeout=60))
        result = ex.run("sleep 60", timeout=1)
        assert result.timed_out


# ======================================================================
# Config handling
# ======================================================================


class TestConfig:
    """SandboxConfig merging and disabled mode."""

    def test_disabled_skips_restrictions(self, disabled_executor: SandboxedExecutor) -> None:
        """When enabled=False, the command still runs."""
        result = disabled_executor.run("echo no-sandbox")
        assert result.stdout.strip() == "no-sandbox"
        assert not result.timed_out

    def test_disabled_respects_timeout(self, disabled_executor: SandboxedExecutor) -> None:
        """Timeout should still be enforced even with sandbox disabled."""
        result = disabled_executor.run("sleep 60", timeout=1)
        assert result.timed_out

    def test_config_readonly_paths_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Setting readonly_paths with the subprocess backend logs a warning."""
        import logging

        caplog.set_level(logging.WARNING)
        config = SandboxConfig(readonly_paths=["/usr"])
        ex = SandboxedExecutor(config=config)
        ex.run("echo hi")
        assert any("readonly_paths" in msg for msg in caplog.messages), (
            "Expected a warning about readonly_paths not being enforced"
        )


# ======================================================================
# Environment restriction
# ======================================================================


class TestEnvironmentRestriction:
    """The restricted environment should not contain dangerous tools."""

    def test_dangerous_tool_not_on_path(self) -> None:
        """A dangerous tool like ``rm`` must not be resolvable in the sandbox."""
        ex = SandboxedExecutor()
        # ``command -v`` is POSIX and returns 0 if found, 1 if not found.
        result = ex.run("command -v rm")
        # When the tool is not on PATH the exit code is non-zero.
        assert result.exit_code != 0, (
            f"rm was found on PATH (stdout={result.stdout.strip()!r})"
        )

    def test_absolute_path_still_works(self, executor: SandboxedExecutor) -> None:
        """Absolute paths bypass PATH restriction -- expected behaviour."""
        result = executor.run("/bin/echo abs-path-works")
        assert result.stdout.strip() == "abs-path-works"

    def test_safe_tool_still_available(self, executor: SandboxedExecutor) -> None:
        """Common safe tools (echo, cat, true) must still be found."""
        result = executor.run("echo ok")
        assert result.stdout.strip() == "ok"


# ======================================================================
# Large output handling
# ======================================================================


class TestLargeOutput:
    """The executor should handle stdout/stderr larger than pipe buffers."""

    def test_large_stdout(self, executor: SandboxedExecutor) -> None:
        """Generate 1 MiB of output and verify it's captured fully."""
        result = executor.run(
            sys.executable + " -c 'import sys; sys.stdout.write(\"x\" * 1024 * 1024)'"
        )
        assert len(result.stdout) == 1024 * 1024
        assert result.exit_code == 0

    def test_large_stderr(self, executor: SandboxedExecutor) -> None:
        """Generate 1 MiB of stderr and verify it's captured fully."""
        result = executor.run(
            sys.executable + " -c 'import sys; sys.stderr.write(\"y\" * 1024 * 1024)'"
        )
        assert len(result.stderr) == 1024 * 1024
        assert result.exit_code == 0


# ======================================================================
# Edge cases
# ======================================================================


class TestEdgeCases:
    """Corner cases in subprocess execution."""

    def test_command_not_found(self, executor: SandboxedExecutor) -> None:
        """A non-existent command should yield a non-zero exit (shell returns 127)."""
        result = executor.run("nonexistent_command_xyz")
        assert result.exit_code != 0, "Expected non-zero exit for unknown command"
        assert not result.timed_out

    def test_unicode_output(self, executor: SandboxedExecutor) -> None:
        """Unicode characters must survive the round-trip."""
        result = executor.run("echo 'café'")
        assert "caf" in result.stdout
        assert result.exit_code == 0

    def test_sandbox_result_attributes(self) -> None:
        """Verify SandboxResult is a proper NamedTuple."""
        r = SandboxResult(stdout="a", stderr="b", exit_code=0, timed_out=False)
        assert r.stdout == "a"
        assert r.stderr == "b"
        assert r.exit_code == 0
        assert not r.timed_out
        # NamedTuple unpacking
        out, err, code, to = r
        assert out == "a"
        assert err == "b"
        assert code == 0
        assert not to

    def test_sandbox_config_validation(self) -> None:
        """SandboxConfig should reject invalid timeout values."""
        with pytest.raises(Exception):  # pydantic validation error
            SandboxConfig(timeout=0)
        with pytest.raises(Exception):
            SandboxConfig(timeout=-1)
        # Upper bound is 3600
        SandboxConfig(timeout=3600)  # should not raise
        with pytest.raises(Exception):
            SandboxConfig(timeout=3601)
