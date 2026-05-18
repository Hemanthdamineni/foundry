"""Integration tests for the SDLC MCP server over stdio transport."""

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
    """Start the SDLC MCP server as a stdio subprocess in a temp workspace."""
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


def _send_request(server: subprocess.Popen, request: dict) -> dict:
    """Send a JSON-RPC request and read the response."""
    line = json.dumps(request) + "\n"
    server.stdin.write(line.encode())
    server.stdin.flush()
    response = server.stdout.readline()
    if not response:
        stderr_output = server.stderr.read().decode() if server.stderr else "no stderr"
        raise AssertionError(
            f"Empty response from server. stderr:\n{stderr_output}"
        )
    data = json.loads(response.decode().strip())
    if "error" in data:
        raise AssertionError(f"RPC error: {data['error']}")
    return data


def _send_notification(server: subprocess.Popen, notification: dict) -> None:
    """Send a JSON-RPC notification (no response expected)."""
    line = json.dumps(notification) + "\n"
    server.stdin.write(line.encode())
    server.stdin.flush()


def _stop_server(server: subprocess.Popen) -> None:
    """Kill a test server and close its pipes."""
    if server.poll() is None:
        server.kill()
    server.wait(timeout=5)
    for pipe in (server.stdin, server.stdout, server.stderr):
        if pipe and not pipe.closed:
            pipe.close()


def _next_id() -> int:
    _next_id.counter += 1
    return _next_id.counter


_next_id.counter = 1


class TestServerLifespan:
    def test_initialize(self, sdlc_server: subprocess.Popen) -> None:
        resp = _send_request(sdlc_server, MCP_INITIALIZE)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "foundry-orchestrator"
        assert "tools" in resp["result"]["capabilities"]

    def test_initialized_notification(self, sdlc_server: subprocess.Popen) -> None:
        _send_request(sdlc_server, MCP_INITIALIZE)
        _send_notification(sdlc_server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        _send_notification(sdlc_server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })


class TestTaskLifecycle:
    def _initialize_and_create_task(self, server: subprocess.Popen) -> tuple[dict, str]:
        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Integration test task", "mode": "feature"},
            },
        })
        result = create_resp["result"]
        assert result["content"][0]["text"] is not None
        data = json.loads(result["content"][0]["text"])
        return data, data["task_id"]

    def test_create_task(self, sdlc_server: subprocess.Popen) -> None:
        data, task_id = self._initialize_and_create_task(sdlc_server)
        assert task_id is not None
        assert data["initial_phase"] == "Chatting"

    def test_get_next_action(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_get_next_action",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["phase"] == "Chatting"
        assert result["progress"] > 0
        assert "constraints" in result

    def test_submit_output_advances_phase(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)

        def get_phase() -> str:
            rid = _next_id()
            resp = _send_request(sdlc_server, {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/call",
                "params": {
                    "name": "sdlc_get_next_action",
                    "arguments": {"task_id": task_id},
                },
            })
            return json.loads(resp["result"]["content"][0]["text"])["phase"]

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args: dict = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(sdlc_server, {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/call",
                "params": {
                    "name": "sdlc_submit_output",
                    "arguments": args,
                },
            })
            return json.loads(resp["result"]["content"][0]["text"])

        # Advance through phases
        assert get_phase() == "Chatting"

        result = submit("Chatting", "Clarified task scope.")
        assert result["accepted"]
        assert result["next_phase"] == "Specs"

        result = submit("Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        assert result["accepted"]
        assert result["next_phase"] == "Planning"

        result = submit("Planning", "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low")
        assert result["accepted"]
        assert result["next_phase"] == "Coding"

        result = submit("Coding", "## Files Modified\n- a.py (modify)")
        assert result["accepted"]
        assert result["next_phase"] == "Review"

        # Review has two possible next phases: Coding or Testing
        # Without target, with 2+ options and Done not one of them, it's ambiguous
        # So we must provide target
        result = submit("Review", "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing", next_phase="Testing")
        assert result["accepted"]
        assert result["next_phase"] == "Testing"

        result = submit("Testing", "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none")
        assert result["accepted"]
        assert result["next_phase"] == "Done"

    def test_get_status(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_get_status",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["task_id"] == task_id
        assert result["status"] == "active"

    def test_list_tasks(self, sdlc_server: subprocess.Popen) -> None:
        self._initialize_and_create_task(sdlc_server)
        self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_list_tasks",
                "arguments": {},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert len(result["tasks"]) >= 2

    def test_cancel_task(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_cancel_task",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["success"]

        # Verify status is cancelled
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_get_status",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["status"] == "cancelled"

    def test_checkpoint_persistence(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        """Verify checkpoints are written to disk after each submit."""
        _, task_id = self._initialize_and_create_task(sdlc_server)

        rid = _next_id()
        _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Chatting",
                    "output": "Clarified.",
                },
            },
        })

        # Check checkpoint dir for the task file
        checkpoint_dir = tmp_path / ".sdlc" / "checkpoints"
        cp_file = checkpoint_dir / f"{task_id}.json"
        assert cp_file.exists(), f"Checkpoint file not found: {cp_file}"
        cp_data = json.loads(cp_file.read_text())
        assert cp_data["task_id"] == task_id
        assert cp_data["phase"] == "Specs"

    def test_phase_mismatch_rejected(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Coding",
                    "output": "Wrong phase.",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert "phase mismatch" in result["error"].lower()


class TestCrashRecovery:
    def test_checkpoint_restore_after_restart(self, tmp_path: Path) -> None:
        """Phase advancement writes a checkpoint; restarting restores state."""
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

        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })

        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Crash test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        # Advance to Planning
        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Chatting",
                    "output": "Clarified.",
                },
            },
        })

        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Specs",
                    "output": "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
                },
            },
        })

        # Kill the server
        _stop_server(server)

        # The checkpoint file must exist
        cp_file = tmp_path / ".sdlc" / "checkpoints" / f"{task_id}.json"
        assert cp_file.exists()
        cp_data = json.loads(cp_file.read_text())
        assert cp_data["phase"] == "Planning", f"Expected Planning, got {cp_data['phase']}"
        assert len(cp_data["history"]) == 2

        # Restart server
        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc_mcp"],
            cwd=tmp_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        _send_request(server2, MCP_INITIALIZE)
        _send_notification(server2, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })

        # Check that task still exists with correct phase
        rid = _next_id()
        status_resp = _send_request(server2, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_get_status",
                "arguments": {"task_id": task_id},
            },
        })
        status = json.loads(status_resp["result"]["content"][0]["text"])
        assert status["phase"] == "Planning", f"Expected Planning after restart, got {status['phase']}"
        assert status["iteration_count"] == 2

        _stop_server(server2)

    def test_submit_after_restart_continues(self, tmp_path: Path) -> None:
        """After restart, can continue submitting from restored phase."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_DIR)

        def start_server():
            s = subprocess.Popen(
                [_PYTHON, "-m", "sdlc_mcp"],
                cwd=tmp_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            _send_request(s, MCP_INITIALIZE)
            _send_notification(s, {
                "jsonrpc": "2.0", "method": "notifications/initialized",
            })
            return s

        # Phase 1: create + advance to Planning
        server = start_server()
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Continue test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Chatting",
                    "output": "Clarified.",
                },
            },
        })
        _stop_server(server)

        # Phase 2: restart and continue
        server2 = start_server()
        rid = _next_id()
        submit_resp = _send_request(server2, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Specs",
                    "output": "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
                },
            },
        })
        result = json.loads(submit_resp["result"]["content"][0]["text"])
        assert result["accepted"]
        assert result["next_phase"] == "Planning"

        _stop_server(server2)


class TestApprovalFlow:
    def test_request_approval(self, sdlc_server: subprocess.Popen) -> None:
        _send_request(sdlc_server, MCP_INITIALIZE)
        _send_notification(sdlc_server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })

        rid = _next_id()
        create_resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Approval test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_request_approval",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Coding",
                    "summary": "Please approve this phase.",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["approved"] is False
        assert "pending" in result["feedback"].lower()
