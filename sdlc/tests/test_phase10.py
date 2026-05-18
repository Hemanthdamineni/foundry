from __future__ import annotations

import pytest

from sdlc.adapters.execution import ProcessWatchdog, SandboxAdapter
from sdlc.config import SandboxConfig


class TestSandboxAdapter:
    @pytest.mark.asyncio
    async def test_validate_with_command(self) -> None:
        adapter = SandboxAdapter()
        assert await adapter.validate({"command": "echo hello"}) is True

    @pytest.mark.asyncio
    async def test_validate_no_command(self) -> None:
        adapter = SandboxAdapter()
        assert await adapter.validate({}) is False

    @pytest.mark.asyncio
    async def test_execute_no_command(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({})
        assert result["passed"] is False
        assert "No command" in result["summary"]

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({"command": "echo hello"})
        assert result["passed"] is True
        assert result["details"]["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_execute_failure(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({"command": "exit 42"})
        assert result["passed"] is False
        assert result["details"]["exit_code"] == 42

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({
            "command": "sleep 10",
            "timeout": 1,
        })
        assert result["passed"] is False
        assert result["details"]["timeout"] is True

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self, tmp_path) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({
            "command": "pwd",
            "cwd": str(tmp_path),
        })
        assert result["passed"] is True
        assert str(tmp_path) in result["details"]["stdout"]

    @pytest.mark.asyncio
    async def test_healthcheck_disabled(self) -> None:
        adapter = SandboxAdapter(config=SandboxConfig(enabled=False))
        assert await adapter.healthcheck() is True

    @pytest.mark.asyncio
    async def test_execute_captures_stderr(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({"command": "echo error >&2 && exit 1"})
        assert result["details"]["stderr"] != ""

    @pytest.mark.asyncio
    async def test_execute_large_output_truncated(self) -> None:
        adapter = SandboxAdapter()
        result = await adapter.execute({"command": "python3 -c 'print(\"x\" * 2000000)'"})
        assert len(result["details"]["stdout"]) <= 1_048_576


class TestProcessWatchdog:
    @pytest.mark.asyncio
    async def test_track_and_stats(self) -> None:
        watchdog = ProcessWatchdog()
        proc = type("Proc", (), {"pid": 12345})()
        watchdog.track(proc)
        assert watchdog.stats["tracked"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_no_processes(self) -> None:
        watchdog = ProcessWatchdog()
        result = await watchdog.cleanup()
        assert result["cleaned"] == 0
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        watchdog = ProcessWatchdog()
        watchdog._pids = [1, 2, 3]
        watchdog.clear()
        assert watchdog.stats["tracked"] == 0
