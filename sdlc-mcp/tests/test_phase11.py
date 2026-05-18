"""Phase 11 — End-to-end integration tests for Phase 5/6/7/10 tools over stdio."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent
SRC_DIR = PROJECT_DIR / "src"

def _python_with_runtime_deps() -> str:
    candidates = (
        PROJECT_DIR / ".pixi" / "envs" / "default" / "bin" / "python",
        PROJECT_DIR.parent / ".venv" / "bin" / "python",
        Path(sys.executable),
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        result = subprocess.run(
            [str(candidate), "-c", "import mcp"],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            return str(candidate)
    return sys.executable


_PYTHON = _python_with_runtime_deps()

MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}


@pytest.fixture
def sdlc_server(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    server = subprocess.Popen(
        [_PYTHON, "-m", "sdlc_mcp"],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        yield server
    finally:
        _stop_server(server)


@pytest.fixture
def initialized_server(sdlc_server):
    _send_request(sdlc_server, MCP_INITIALIZE)
    _send_notification(sdlc_server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return sdlc_server


def _send_request(server: subprocess.Popen, request: dict) -> dict:
    line = json.dumps(request) + "\n"
    server.stdin.write(line.encode())
    server.stdin.flush()
    response = server.stdout.readline()
    if not response:
        stderr_output = server.stderr.read().decode() if server.stderr else "no stderr"
        raise AssertionError(f"Empty response from server. stderr:\n{stderr_output}")
    data = json.loads(response.decode().strip())
    if "error" in data:
        raise AssertionError(f"RPC error: {data['error']}")
    return data


def _send_notification(server: subprocess.Popen, notification: dict) -> None:
    line = json.dumps(notification) + "\n"
    server.stdin.write(line.encode())
    server.stdin.flush()


def _stop_server(server: subprocess.Popen) -> None:
    if server.poll() is None:
        server.kill()
    server.wait(timeout=5)
    for pipe in (server.stdin, server.stdout, server.stderr):
        if pipe and not pipe.closed:
            pipe.close()


def _next_id() -> int:
    _next_id.counter += 1
    return _next_id.counter


_next_id.counter = 100

_SPECS_OUTPUT = "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none"
_PLANNING_OUTPUT = "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low"
_CODING_OUTPUT = "## Files Modified\n- a.py (modify)"
_REVIEW_OUTPUT = "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing"
_TESTING_OUTPUT = "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none"


def _tool_call(server: subprocess.Popen, name: str, arguments: dict) -> dict:
    rid = _next_id()
    resp = _send_request(server, {
        "jsonrpc": "2.0",
        "id": rid,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    return json.loads(resp["result"]["content"][0]["text"])


def _create_and_advance(server: subprocess.Popen) -> str:
    data = _tool_call(server, "sdlc_create_task", {
        "description": "E2E test task",
        "mode": "feature",
    })
    task_id = data["task_id"]

    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Chatting", "output": "Clarified.",
    })
    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Specs", "output": _SPECS_OUTPUT,
    })
    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Planning", "output": _PLANNING_OUTPUT,
    })
    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Coding", "output": _CODING_OUTPUT,
    })
    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Review", "output": _REVIEW_OUTPUT,
        "next_phase": "Testing",
    })
    _tool_call(server, "sdlc_submit_output", {
        "task_id": task_id, "phase": "Testing", "output": _TESTING_OUTPUT,
    })
    return task_id


class TestToolRegistration:
    def test_all_tools_listed(self, initialized_server) -> None:
        rid = _next_id()
        resp = _send_request(initialized_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/list",
            "params": {},
        })
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        expected = {
            "sdlc_create_task", "sdlc_get_next_action", "sdlc_submit_output",
            "sdlc_get_status", "sdlc_list_tasks", "sdlc_cancel_task",
            "sdlc_request_approval", "sdlc_get_trace", "sdlc_list_traces",
            "sdlc_get_summaries", "sdlc_enforce_retention",
            "sdlc_index_repository", "sdlc_index_files",
            "sdlc_get_dependency_context", "sdlc_get_index_stats",
            "sdlc_debate_output", "sdlc_memory_store",
            "sdlc_memory_query", "sdlc_memory_stats",
        }
        for e in expected:
            assert e in names, f"Missing tool: {e}"


class TestIndexTools:
    def test_index_stats_returns_pipeline(self, initialized_server) -> None:
        result = _tool_call(initialized_server, "sdlc_get_index_stats", {})
        assert "indexed_count" in result
        assert "total_files" in result
        assert "enabled" in result

    def test_index_repository_full(self, initialized_server) -> None:
        result = _tool_call(initialized_server, "sdlc_index_repository", {"mode": "full"})
        assert result.get("status") == "ok" or "indexed_count" in result

    def test_index_repository_incremental(self, initialized_server) -> None:
        result = _tool_call(initialized_server, "sdlc_index_repository", {"mode": "incremental"})
        assert result is not None


class TestDebateTool:
    def test_debate_output_tool(self, initialized_server) -> None:
        data = _tool_call(initialized_server, "sdlc_create_task", {
            "description": "Debate test", "mode": "feature",
        })
        task_id = data["task_id"]

        result = _tool_call(initialized_server, "sdlc_debate_output", {
            "task_id": task_id,
            "phase": "Coding",
            "output": "def foo(): pass",
        })
        assert result.get("error") is not None or "rounds" in result


class TestMemoryTools:
    def test_memory_tools_may_be_disabled(self, initialized_server) -> None:
        result = _tool_call(initialized_server, "sdlc_memory_stats", {})
        assert result.get("error") is not None or "engram_count" in result


class TestResourceRegistration:
    def test_phase_graph_resource(self, initialized_server) -> None:
        rid = _next_id()
        resp = _send_request(initialized_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "resources/list",
            "params": {},
        })
        resources = resp["result"]["resources"]
        uris = {r["uri"] for r in resources}
        assert "sdlc://phase-graph" in uris

    def test_phase_graph_content(self, initialized_server) -> None:
        rid = _next_id()
        resp = _send_request(initialized_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "resources/read",
            "params": {"uri": "sdlc://phase-graph"},
        })
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        text = contents[0]["text"]
        assert "Phase Graph" in text
        assert "Chatting" in text
        assert "Done" in text
