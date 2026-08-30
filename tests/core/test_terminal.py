"""Tests for TerminalSession — subprocess execution."""

from __future__ import annotations

import pytest

from foundry.core.terminal.session import (
    ManagedProcess,
    ProcessResult,
    ProcessStatus,
    TerminalSession,
)


class TestProcessResult:
    def test_success(self) -> None:
        result = ProcessResult(
            process_id="p1",
            command="echo hello",
            exit_code=0,
            stdout="hello\n",
            stderr="",
            duration_s=0.1,
            status=ProcessStatus.COMPLETED,
        )
        assert result.success is True

    def test_failure(self) -> None:
        result = ProcessResult(
            process_id="p1",
            command="false",
            exit_code=1,
            stdout="",
            stderr="error",
            duration_s=0.1,
            status=ProcessStatus.FAILED,
        )
        assert result.success is False

    def test_timeout(self) -> None:
        result = ProcessResult(
            process_id="p1",
            command="sleep 10",
            exit_code=None,
            stdout="",
            stderr="timed out",
            duration_s=10.0,
            status=ProcessStatus.TIMEOUT,
            timed_out=True,
        )
        assert result.success is False
        assert result.timed_out is True

    def test_to_dict(self) -> None:
        result = ProcessResult(
            process_id="p1",
            command="echo hi",
            exit_code=0,
            stdout="hi\n",
            stderr="",
            duration_s=0.05,
            status=ProcessStatus.COMPLETED,
        )
        d = result.to_dict()
        assert d["process_id"] == "p1"
        assert d["exit_code"] == 0


class TestTerminalSession:
    @pytest.mark.asyncio
    async def test_run_simple(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("echo hello")
        assert result.success is True
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_run_with_error(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("echo error >&2 && exit 1")
        assert result.success is False
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_timeout(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("sleep 10", timeout=0.5)
        assert result.timed_out is True
        assert result.status == ProcessStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_run_custom_cwd(self, tmp_path) -> None:
        terminal = TerminalSession()
        (tmp_path / "test.txt").write_text("content")
        result = await terminal.run("cat test.txt", cwd=str(tmp_path))
        assert result.success is True
        assert "content" in result.stdout

    @pytest.mark.asyncio
    async def test_run_with_env(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("echo $MY_VAR", env={"MY_VAR": "hello"})
        assert result.success is True
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_run_with_input(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("cat", input_data="hello from stdin")
        assert result.success is True
        assert "hello from stdin" in result.stdout

    @pytest.mark.asyncio
    async def test_list_processes(self) -> None:
        terminal = TerminalSession()
        await terminal.run("echo test")
        processes = terminal.list_processes()
        assert len(processes) >= 1

    @pytest.mark.asyncio
    async def test_get_process(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("echo test")
        proc = terminal.get_process(result.process_id)
        assert proc is not None
        assert proc.status == ProcessStatus.COMPLETED
