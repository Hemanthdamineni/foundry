"""Integration tests for the SDLC MCP server over stdio transport."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent
REPO_DIR = PROJECT_DIR.parent

# Find the Python that has all dependencies installed
_PIXI_PYTHON = str(PROJECT_DIR / ".pixi" / "envs" / "default" / "bin" / "python")
_VENV_PYTHON = str(REPO_DIR / ".venv" / "bin" / "python")
if os.path.exists(_PIXI_PYTHON):
    _PYTHON = _PIXI_PYTHON
    _TOOL_BIN = str(PROJECT_DIR / ".pixi" / "envs" / "default" / "bin")
elif os.path.exists(_VENV_PYTHON):
    _PYTHON = _VENV_PYTHON
    _TOOL_BIN = str(REPO_DIR / ".venv" / "bin")
else:
    _PYTHON = sys.executable
    _TOOL_BIN = ""

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
    env["PYTHONPATH"] = str(REPO_DIR)
    # Ensure tool binaries (ruff, mypy, pytest) are on PATH for gate enforcement
    if _TOOL_BIN and os.path.exists(_TOOL_BIN):
        env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
    server = subprocess.Popen(
        [_PYTHON, "-m", "sdlc"],
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
    """Send a JSON-RPC request and read the response, skipping notifications."""
    line = json.dumps(request) + "\n"
    server.stdin.write(line.encode())
    server.stdin.flush()
    while True:
        response = server.stdout.readline()
        if not response:
            stderr_output = server.stderr.read().decode() if server.stderr else "no stderr"
            raise AssertionError(
                f"Empty response from server. stderr:\n{stderr_output}"
            )
        data = json.loads(response.decode().strip())
        # Skip notifications (no "id" field) — only return responses
        if "id" in data:
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
        assert resp["result"]["serverInfo"]["name"] == "sdlc-orchestrator"
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

    def test_submit_output_advances_phase(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_pass.py").write_text(
            "def test_pass():\n    assert True\n",
        )
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
        checkpoint_dir = PROJECT_DIR / "data" / "checkpoints"
        cp_file = checkpoint_dir / f"{task_id}.json"
        assert cp_file.exists(), f"Checkpoint file not found: {cp_file}"
        cp_data = json.loads(cp_file.read_text())
        assert cp_data["task_id"] == task_id
        assert cp_data["phase"] == "Specs"

    def test_cancelled_task_rejected(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        rid = _next_id()
        _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_cancel_task",
                "arguments": {"task_id": task_id},
            },
        })
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id,
                    "phase": "Chatting",
                    "output": "Should be rejected.",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert "cancelled" in result["error"].lower()

    def test_done_task_rejected(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_pass.py").write_text(
            "def test_pass():\n    assert True\n",
        )
        _, task_id = self._initialize_and_create_task(sdlc_server)

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

        submit("Chatting", "Clarified task scope.")
        submit("Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        submit("Planning", "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low")
        submit("Coding", "## Files Modified\n- a.py (modify)")
        submit("Review", "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing", next_phase="Testing")
        done_resp = submit("Testing", "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none")
        assert done_resp["accepted"]
        assert done_resp["next_phase"] == "Done"

        # Now try to submit again to a done task
        result = submit("Chatting", "Should be rejected.")
        assert not result["accepted"]
        assert "done" in result["error"].lower()

    def test_chatting_to_done_shortcut_rejected(self, sdlc_server: subprocess.Popen) -> None:
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
                    "phase": "Chatting",
                    "output": "Skip everything.",
                    "next_phase": "Done",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert "shortcut" in result["error"].lower() or "disabled" in result["error"].lower()

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


class TestModeEnforcement:
    """P1-04: Only feature workflow mode is supported in MVP."""

    def _raw_create_task(self, server: subprocess.Popen, mode: str) -> dict:
        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        line = json.dumps({
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Mode test", "mode": mode},
            },
        }) + "\n"
        server.stdin.write(line.encode())
        server.stdin.flush()
        response = server.stdout.readline()
        return json.loads(response.decode().strip())

    def test_feature_mode_accepted(self, sdlc_server: subprocess.Popen) -> None:
        data = self._raw_create_task(sdlc_server, "feature")
        result = json.loads(data["result"]["content"][0]["text"])
        assert result.get("task_id") is not None
        assert result.get("initial_phase") == "Chatting"

    def test_bugfix_mode_rejected(self, sdlc_server: subprocess.Popen) -> None:
        """Non-feature modes must return a clear unsupported error."""
        data = self._raw_create_task(sdlc_server, "bugfix")
        assert data.get("result", {}).get("isError")
        text = data["result"]["content"][0]["text"].lower()
        assert "unsupported" in text or "deferred" in text

    def test_refactor_mode_rejected(self, sdlc_server: subprocess.Popen) -> None:
        data = self._raw_create_task(sdlc_server, "refactor")
        assert data.get("result", {}).get("isError")
        text = data["result"]["content"][0]["text"].lower()
        assert "unsupported" in text or "deferred" in text


class TestSchemaValidation:
    """P1-02: Schema validation rejects invalid output before judge runs."""

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
                "arguments": {"description": "Schema test", "mode": "feature"},
            },
        })
        data = json.loads(create_resp["result"]["content"][0]["text"])
        return data, data["task_id"]

    def _submit(self, server: subprocess.Popen, task_id: str, phase: str, output: str, next_phase: str | None = None) -> dict:
        args: dict = {"task_id": task_id, "phase": phase, "output": output}
        if next_phase:
            args["next_phase"] = next_phase
        rid = _next_id()
        resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": args,
            },
        })
        return json.loads(resp["result"]["content"][0]["text"])

    def test_invalid_specs_schema_rejected(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        result = self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing")
        assert not result["accepted"]
        assert "schema" in result["error"].lower()
        assert "violations" in result
        assert len(result["violations"]) >= 2  # Missing Scope + Constraints

    def test_invalid_planning_schema_rejected(self, sdlc_server: subprocess.Popen) -> None:
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        result = self._submit(sdlc_server, task_id, "Planning", "## Implementation Plan\n- step1")
        assert not result["accepted"]
        assert "schema" in result["error"].lower()
        assert "violations" in result
        assert len(result["violations"]) >= 2  # Missing File Changes + Risks

    def test_invalid_review_schema_rejected(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        self._submit(sdlc_server, task_id, "Planning", "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low")
        self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        result = self._submit(sdlc_server, task_id, "Review", "## Issues Found\n- bug\n## Severity\n- high", next_phase="Testing")
        assert not result["accepted"]
        assert "schema" in result["error"].lower()
        assert "violations" in result
        # Missing Must Fix
        assert any("Must Fix" in str(v) for v in result["violations"])

    def test_invalid_testing_schema_rejected(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_pass.py").write_text(
            "def test_pass():\n    assert True\n",
        )
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        self._submit(sdlc_server, task_id, "Planning", "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low")
        self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        self._submit(sdlc_server, task_id, "Review", "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing", next_phase="Testing")
        result = self._submit(sdlc_server, task_id, "Testing", "## Test Results\n- all pass\n## Coverage\n- 100%")
        assert not result["accepted"]
        assert "schema" in result["error"].lower()
        assert "violations" in result
        # Missing Failed section
        assert any("Failed" in str(v) for v in result["violations"])

    def test_schema_failure_skips_judge(self, sdlc_server: subprocess.Popen) -> None:
        """Prove judge is never reached when schema validation fails."""
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        result = self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing")
        assert not result["accepted"]
        assert "schema" in result["error"].lower()
        # The error message says "Schema validation failed", NOT "Judge rejected"
        # proving the judge path was never reached
        assert "judge" not in result.get("error", "").lower()
        assert "violations" in result

    def test_schema_failure_keeps_phase_unchanged(self, sdlc_server: subprocess.Popen) -> None:
        """Phase must not advance on schema failure."""
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")

        # Submit invalid Specs
        result = self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing")
        assert not result["accepted"]

        # Verify phase is still Specs
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
        next_action = json.loads(resp["result"]["content"][0]["text"])
        assert next_action["phase"] == "Specs"

    def test_valid_specs_still_passes_schema(self, sdlc_server: subprocess.Popen) -> None:
        """Ensure valid output still passes schema and advances correctly."""
        _, task_id = self._initialize_and_create_task(sdlc_server)
        self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        result = self._submit(sdlc_server, task_id, "Specs", "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none")
        assert result["accepted"]
        assert result["next_phase"] == "Planning"


class TestCrashRecovery:
    def test_checkpoint_restore_after_restart(self, tmp_path: Path) -> None:
        """Phase advancement writes a checkpoint; restarting restores state."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        cp_file = PROJECT_DIR / "data" / "checkpoints" / f"{task_id}.json"
        assert cp_file.exists()
        cp_data = json.loads(cp_file.read_text())
        assert cp_data["phase"] == "Planning", f"Expected Planning, got {cp_data['phase']}"
        assert len(cp_data["history"]) == 2

        # Restart server
        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        env["PYTHONPATH"] = str(REPO_DIR)

        def start_server():
            s = subprocess.Popen(
                [_PYTHON, "-m", "sdlc"],
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


class TestRestartResume:
    """P3-04: Accepted progress survives process restart with isolated runtime paths."""

    def _start_isolated_server(self, tmp_path: Path, env: dict[str, str]):
        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        return server

    def test_restart_resume_preserves_phase_and_history(self, tmp_path: Path) -> None:
        """Create task, advance to Planning, restart, verify phase/history."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"

        # Isolate runtime paths into tmp_path
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        log_path = log_dir / "sdlc.log"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)
        env["SDLC_LOGGING__PATH"] = str(log_path)

        # Phase 1: start server, create task, advance to Planning
        server = self._start_isolated_server(tmp_path, env)
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P3-04 restart test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Chatting", "output": "Clarified.",
                },
            },
        })

        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Specs",
                    "output": "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
                },
            },
        })

        # Capture pre-restart state
        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        pre_status = json.loads(status_resp["result"]["content"][0]["text"])
        assert pre_status["phase"] == "Planning", (
            f"Expected Planning, got {pre_status['phase']}"
        )
        pre_history_len = len(pre_status["history"])
        pre_iteration = pre_status["iteration_count"]

        _stop_server(server)

        # Verify checkpoint was written to isolated directory
        cp_file = cp_dir / f"{task_id}.json"
        assert cp_file.exists(), f"Checkpoint not found: {cp_file}"
        cp_data = json.loads(cp_file.read_text())
        assert cp_data["phase"] == "Planning"
        assert len(cp_data["history"]) == 2

        # Verify SQLite was written to isolated path
        assert db_path.exists(), f"SQLite DB not found: {db_path}"

        # Phase 2: restart with same isolated runtime paths
        server2 = self._start_isolated_server(tmp_path, env)

        # Status should match pre-restart state
        rid = _next_id()
        status_resp2 = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        post_status = json.loads(status_resp2["result"]["content"][0]["text"])
        assert post_status["phase"] == "Planning", (
            f"Expected Planning after restart, got {post_status['phase']}"
        )
        assert post_status["iteration_count"] == pre_iteration
        assert len(post_status["history"]) == pre_history_len

        # Next action should resume from Planning
        rid = _next_id()
        action_resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_next_action", "arguments": {"task_id": task_id}},
        })
        action = json.loads(action_resp["result"]["content"][0]["text"])
        assert action["phase"] == "Planning"

        # Continue submitting — advance from Planning to Coding
        rid = _next_id()
        submit_resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Planning",
                    "output": "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low",
                },
            },
        })
        result = json.loads(submit_resp["result"]["content"][0]["text"])
        assert result["accepted"], f"Submit after restart failed: {result}"
        assert result["next_phase"] == "Coding"

        # Verify checkpoint + history consistency after restart + submit
        cp_data2 = json.loads(cp_file.read_text())
        assert cp_data2["phase"] == "Coding"

        rid = _next_id()
        status_resp3 = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        post_submit_status = json.loads(status_resp3["result"]["content"][0]["text"])
        assert post_submit_status["phase"] == "Coding"
        assert len(post_submit_status["history"]) == pre_history_len + 1

        _stop_server(server2)

    def test_restart_resume_checkpoint_sqlite_consistency(self, tmp_path: Path) -> None:
        """After restart, checkpoint phase and SQLite phase must agree."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"

        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        log_path = log_dir / "sdlc.log"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)
        env["SDLC_LOGGING__PATH"] = str(log_path)

        server = self._start_isolated_server(tmp_path, env)
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P3-04 consistency", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        # Advance to Planning
        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Chatting", "output": "Clarified.",
                },
            },
        })
        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Specs",
                    "output": "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
                },
            },
        })
        _stop_server(server)

        # Verify checkpoint and SQLite agree
        cp_file = cp_dir / f"{task_id}.json"
        assert cp_file.exists()
        cp_data = json.loads(cp_file.read_text())

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT data FROM tasks WHERE task_id = ?", (task_id,),
        ).fetchone()
        db_data = json.loads(row[0])
        conn.close()

        assert cp_data["phase"] == db_data["current_phase"], (
            f"Checkpoint phase {cp_data['phase']} != SQLite phase {db_data['current_phase']}"
        )
        assert len(cp_data["history"]) == len(db_data.get("history", []))

        # Restart and verify sdlc_resume_task agrees
        server2 = self._start_isolated_server(tmp_path, env)
        rid = _next_id()
        resume_resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": task_id},
            },
        })
        resume_data = json.loads(resume_resp["result"]["content"][0]["text"])
        assert resume_data["recovered"], f"Resume after restart failed: {resume_data}"
        assert resume_data["phase"] == db_data["current_phase"]

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


class TestToolGates:
    """P2-03/P2-04: Tool gates enforce lint/type/test validation before phase advancement."""

    def _init_and_create(self, server: subprocess.Popen) -> str:
        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Gate test", "mode": "feature"},
            },
        })
        return json.loads(resp["result"]["content"][0]["text"])["task_id"]

    def _submit(
        self,
        server: subprocess.Popen,
        task_id: str,
        phase: str,
        output: str,
        next_phase: str | None = None,
    ) -> dict:
        args: dict = {"task_id": task_id, "phase": phase, "output": output}
        if next_phase:
            args["next_phase"] = next_phase
        rid = _next_id()
        resp = _send_request(server, {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": args,
            },
        })
        return json.loads(resp["result"]["content"][0]["text"])

    def _advance_to_coding(self, server: subprocess.Popen, task_id: str) -> None:
        self._submit(server, task_id, "Chatting", "Clarified.")
        self._submit(
            server, task_id, "Specs",
            "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
        )
        self._submit(
            server, task_id, "Planning",
            "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low",
        )

    def test_ruff_failure_blocks_coding(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "bad_lint.py").write_text("import os\nimport os\n")
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)
        result = self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        assert not result["accepted"], "Expected gate rejection"
        assert "gate" in result["error"].lower()
        assert result["gate_summary"]["passed"] is False
        assert result["gate_summary"]["failed_at"] == "lint"

    def test_mypy_failure_blocks_coding(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "bad_types.py").write_text("x: int = \"string\"\n")
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)
        result = self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        assert not result["accepted"], "Expected gate rejection"
        assert "gate" in result["error"].lower()
        assert result["gate_summary"]["passed"] is False
        assert result["gate_summary"]["failed_at"] == "types"

    def test_pytest_failure_blocks_testing(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "test_bad.py").write_text("def test_fail():\n    assert False\n")
        (tmp_path / "clean.py").write_text("x = 1\n")
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)
        self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        self._submit(
            sdlc_server, task_id, "Review",
            "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing",
            next_phase="Testing",
        )
        result = self._submit(
            sdlc_server, task_id, "Testing",
            "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none",
        )
        assert not result["accepted"], "Expected gate rejection"
        assert "gate" in result["error"].lower()
        assert result["gate_summary"]["passed"] is False
        assert result["gate_summary"]["failed_at"] == "tests"

    def test_gate_failure_keeps_phase_unchanged(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "bad_lint.py").write_text("import os\nimport os\n")
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)
        result = self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        assert not result["accepted"]

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
        next_action = json.loads(resp["result"]["content"][0]["text"])
        assert next_action["phase"] == "Coding", "Phase must remain Coding after gate rejection"

    def test_non_code_phases_not_blocked_by_bad_files(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        bad_files = [
            tmp_path / "bad_lint.py",
            tmp_path / "bad_types.py",
        ]
        for f in bad_files:
            f.write_text("import os\nimport os\nx: int = \"string\"\n")
        task_id = self._init_and_create(sdlc_server)
        result = self._submit(sdlc_server, task_id, "Chatting", "Clarified.")
        assert result["accepted"]
        result = self._submit(
            sdlc_server, task_id, "Specs",
            "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
        )
        assert result["accepted"]
        result = self._submit(
            sdlc_server, task_id, "Planning",
            "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low",
        )
        assert result["accepted"]

    def test_successful_validation_allows_advancement(self, sdlc_server: subprocess.Popen, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_good.py").write_text(
            "def test_pass():\n    assert True\n",
        )
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)

        result = self._submit(sdlc_server, task_id, "Coding", "## Files Modified\n- a.py (modify)")
        assert result["accepted"], f"Coding gate failed: {result.get('error', '')}"
        assert result["next_phase"] == "Review"
        assert result["gate_summary"]["passed"] is True
        assert "lint" in result["gate_summary"]["passed_gates"]
        assert "types" in result["gate_summary"]["passed_gates"]

        result = self._submit(
            sdlc_server, task_id, "Review",
            "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing",
            next_phase="Testing",
        )
        assert result["accepted"]

        result = self._submit(
            sdlc_server, task_id, "Testing",
            "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none",
        )
        assert result["accepted"], f"Testing gate failed: {result.get('error', '')}"
        assert result["next_phase"] == "Done"
        assert result["gate_summary"]["passed"] is True
        assert "tests" in result["gate_summary"]["passed_gates"]


class TestGateFailureE2E:
    """P4-02: Comprehensive gate failure path — all assertions in one place."""

    _PLANNING = "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low"
    _REVIEW = "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing"
    _TESTING = "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none"

    def _start_isolated_server(self, tmp_path: Path, env: dict[str, str]):
        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        return server

    def test_coding_gate_failure_preserves_phase_and_no_checkpoint(
        self, tmp_path: Path,
    ) -> None:
        """Coding gate failure: rejected, phase unchanged, persisted, no checkpoint written."""
        (tmp_path / "bad_lint.py").write_text("import os\nimport os\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)

        server = self._start_isolated_server(tmp_path, env)

        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-02 Coding gate", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args: dict = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        # Advance to Coding
        submit("Chatting", "Clarified.")
        submit("Specs", "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z")
        submit("Planning", self._PLANNING)

        # Capture checkpoint state before rejected Coding
        cp_before = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp_before["phase"] == "Coding"
        history_before = len(cp_before["history"])

        # Submit Coding with bad lint — should fail gates
        r = submit("Coding", "## Files Modified\n- a.py (modify)")
        assert not r["accepted"], "Expected Coding gate rejection"
        assert "gate" in r["error"].lower()
        assert r["gate_summary"]["passed"] is False
        assert r["gate_summary"]["failed_at"] == "lint"

        # Phase must remain Coding
        rid = _next_id()
        action_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_next_action", "arguments": {"task_id": task_id}},
        })
        action = json.loads(action_resp["result"]["content"][0]["text"])
        assert action["phase"] == "Coding", f"Expected Coding after gate failure, got {action['phase']}"

        # Rejected attempt must be persisted in history
        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(status_resp["result"]["content"][0]["text"])
        assert len(status["history"]) == history_before + 1, "Rejected attempt not in history"
        last_entry = status["history"][-1]
        assert last_entry["status"] == "rejected"
        assert "gate" in (last_entry.get("error") or "").lower()

        # No accepted checkpoint written — checkpoint content must be unchanged
        cp_after = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp_after["phase"] == "Coding"
        assert len(cp_after["history"]) == history_before
        assert cp_after == cp_before

        # Failure not classified as transient retry
        assert status.get("retry_count") == 0

        _stop_server(server)

    def test_testing_gate_failure_preserves_phase_and_no_checkpoint(
        self, tmp_path: Path,
    ) -> None:
        """Testing gate failure: rejected, phase unchanged, persisted, no checkpoint, not transient."""
        (tmp_path / "test_bad.py").write_text("def test_fail():\n    assert False\n")
        (tmp_path / "clean.py").write_text("x = 1\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)

        server = self._start_isolated_server(tmp_path, env)

        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-02 Testing gate", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args: dict = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        # Advance to Testing
        submit("Chatting", "Clarified.")
        submit("Specs", "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z")
        submit("Planning", self._PLANNING)
        submit("Coding", "## Files Modified\n- a.py (modify)")
        submit("Review", self._REVIEW, next_phase="Testing")

        # Capture checkpoint state before rejected Testing
        cp_before = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp_before["phase"] == "Testing"
        history_before = len(cp_before["history"])

        # Submit Testing with failing test — gates should fail at 'tests'
        r = submit("Testing", self._TESTING)
        assert not r["accepted"], "Expected Testing gate rejection"
        assert "gate" in r["error"].lower()
        assert r["gate_summary"]["passed"] is False
        assert r["gate_summary"]["failed_at"] == "tests"

        # Phase must remain Testing
        rid = _next_id()
        action_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_next_action", "arguments": {"task_id": task_id}},
        })
        action = json.loads(action_resp["result"]["content"][0]["text"])
        assert action["phase"] == "Testing", f"Expected Testing after gate failure, got {action['phase']}"

        # Rejected attempt must be persisted in history
        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(status_resp["result"]["content"][0]["text"])
        assert len(status["history"]) == history_before + 1, "Rejected attempt not in history"
        last_entry = status["history"][-1]
        assert last_entry["status"] == "rejected"
        assert "gate" in (last_entry.get("error") or "").lower()

        # No accepted checkpoint written — checkpoint content unchanged
        cp_after = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp_after["phase"] == "Testing"
        assert len(cp_after["history"]) == history_before
        assert cp_after == cp_before

        # Failure not classified as transient retry
        assert status.get("retry_count") == 0

        _stop_server(server)


class TestBoundedTransientRetry:
    """P3-03: Bounded transient retry and exhaustion handling."""

    def _init_and_create(self, server: subprocess.Popen) -> str:
        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Retry test", "mode": "feature"},
            },
        })
        return json.loads(resp["result"]["content"][0]["text"])["task_id"]

    def _advance_to_coding(self, server: subprocess.Popen, task_id: str) -> None:
        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args: dict = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])
        submit("Chatting", "Clarified.")
        submit(
            "Specs", "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z",
        )
        submit(
            "Planning", "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low",
        )

    def test_permanent_gate_failure_does_not_increment_retry(
        self, sdlc_server: subprocess.Popen, tmp_path: Path,
    ) -> None:
        (tmp_path / "bad_lint.py").write_text("import os\nimport os\n")
        task_id = self._init_and_create(sdlc_server)
        self._advance_to_coding(sdlc_server, task_id)

        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Coding",
                    "output": "## Files Modified\n- a.py (modify)",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert not result.get("task_stalled", False)

        # Verify retry metadata was NOT incremented (permanent failure)
        rid = _next_id()
        resp2 = _send_request(sdlc_server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(resp2["result"]["content"][0]["text"])
        assert status.get("retry_count") == 0, (
            f"Expected retry_count=0 for permanent failure, got {status.get('retry_count')}"
        )
        assert status["status"] == "active"

    def test_retry_exhaustion_stalls_task(
        self, tmp_path: Path,
    ) -> None:
        """Set retry_count to ceiling in DB, then verify submit returns STALLED."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)

        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
            cwd=tmp_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        task_id = self._init_and_create(server)
        self._advance_to_coding(server, task_id)

        # Stop server to modify DB directly
        _stop_server(server)

        # Set retry_count to ceiling in SQLite
        db_path = PROJECT_DIR / "data" / "sdlc.db"
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT data FROM tasks WHERE task_id = ?", (task_id,),
        ).fetchone()
        data = json.loads(row[0])
        data["retry_count"] = 999  # Well above ceiling
        data["last_failure_reason"] = "previous transient failures"
        data["last_failure_type"] = "timeout"
        conn.execute(
            "UPDATE tasks SET data = ? WHERE task_id = ?",
            (json.dumps(data), task_id),
        )
        conn.commit()
        conn.close()

        # Restart server
        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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

        # Submit should hit retry ceiling and return STALLED
        rid = _next_id()
        resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Coding",
                    "output": "## Files Modified\n- a.py (modify)",
                },
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert result.get("task_stalled"), (
            f"Expected task_stalled=True, got: {result}"
        )
        assert "ceiling exhausted" in result["error"].lower()

        # Verify task is STALLED in DB
        rid = _next_id()
        resp2 = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(resp2["result"]["content"][0]["text"])
        assert status["status"] == "stalled", (
            f"Expected stalled, got {status['status']}"
        )

        _stop_server(server2)


class TestResumeTask:
    """P3-01: sdlc_resume_task restores from latest checkpoint."""

    def _advance_to_specs(
        self,
        server: subprocess.Popen,
        task_id: str,
    ) -> None:
        _send_request(server, MCP_INITIALIZE)
        _send_notification(server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Chatting", "output": "Clarified.",
                },
            },
        })

    def test_resume_consistent_state(self, sdlc_server: subprocess.Popen) -> None:
        _send_request(sdlc_server, MCP_INITIALIZE)
        _send_notification(sdlc_server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        create_resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Resume consistent", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_specs(sdlc_server, task_id)

        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["recovered"]
        assert not result["restored_from_checkpoint"]
        assert result["phase"] == "Specs"

    def test_resume_missing_checkpoint(self, sdlc_server: subprocess.Popen) -> None:
        _send_request(sdlc_server, MCP_INITIALIZE)
        _send_notification(sdlc_server, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        rid = _next_id()
        resp = _send_request(sdlc_server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": "nonexistent-task"},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["recovered"]
        assert result.get("not_recoverable")

    def test_resume_missing_task_restores_from_checkpoint(self, tmp_path: Path) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)

        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Restore test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_specs(server, task_id)
        _stop_server(server)

        db_path = PROJECT_DIR / "data" / "sdlc.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()

        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        rid = _next_id()
        resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["recovered"], f"Expected recovery: {result}"
        assert result["restored_from_checkpoint"]
        assert result["phase"] == "Specs"
        assert result["history_count"] == 1
        assert result["iteration_count"] == 1

        _stop_server(server2)

    def test_resume_corrupt_checkpoint(self, tmp_path: Path) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)

        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Corrupt test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_specs(server, task_id)
        _stop_server(server)

        cp_file = PROJECT_DIR / "data" / "checkpoints" / f"{task_id}.json"
        assert cp_file.exists(), f"Checkpoint file not found: {cp_file}"
        cp_file.write_text("THIS IS NOT VALID JSON")

        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        rid = _next_id()
        resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["recovered"]
        assert result.get("corrupt")

        _stop_server(server2)

    def test_resume_phase_mismatch(self, tmp_path: Path) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)

        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "Mismatch test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_specs(server, task_id)
        _stop_server(server)

        db_path = PROJECT_DIR / "data" / "sdlc.db"
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT data FROM tasks WHERE task_id = ?", (task_id,),
        ).fetchone()
        data = json.loads(row[0])
        data["current_phase"] = "Planning"
        conn.execute(
            "UPDATE tasks SET data = ? WHERE task_id = ?",
            (json.dumps(data), task_id),
        )
        conn.commit()
        conn.close()

        server2 = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        rid = _next_id()
        resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_resume_task",
                "arguments": {"task_id": task_id},
            },
        })
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["recovered"]
        assert result.get("mismatch")
        assert result["sqlite_phase"] == "Planning"
        assert result["checkpoint_phase"] == "Specs"

        _stop_server(server2)


class TestFeatureWorkflowE2E:
    """P4-01: Deterministic feature workflow end-to-end through all 6 phases."""

    _SPECS = "## Requirements\n- thing\n## Scope\n- in\n## Constraints\n- none"
    _PLANNING = "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low"
    _CODING = "## Files Modified\n- a.py (modify)"
    _REVIEW = "## Issues Found\n- none\n## Severity\n- low\n## Must Fix\n- nothing"
    _TESTING = "## Test Results\n- all pass\n## Coverage\n- 100%\n## Failed\n- none"

    def _start_isolated_server(self, tmp_path: Path, env: dict[str, str]):
        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        return server

    def test_feature_workflow_reaches_done(self, tmp_path: Path) -> None:
        """Full feature workflow: Chatting → Specs → Planning → Coding → Review → Testing → Done."""
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_pass.py").write_text(
            "def test_pass():\n    assert True\n",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        log_path = log_dir / "sdlc.log"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)
        env["SDLC_LOGGING__PATH"] = str(log_path)

        server = self._start_isolated_server(tmp_path, env)

        # Create task
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-01 E2E test", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args: dict = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        # Phase 1: Chatting → Specs
        r = submit("Chatting", "Clarified task scope.")
        assert r["accepted"], f"Chatting failed: {r}"
        assert r["next_phase"] == "Specs"
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Specs", f"Chatting checkpoint: expected Specs, got {cp['phase']}"

        r = submit("Specs", self._SPECS)
        assert r["accepted"], f"Specs failed: {r}"
        assert r["next_phase"] == "Planning"
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Planning"
        assert len(cp["history"]) == 2

        r = submit("Planning", self._PLANNING)
        assert r["accepted"], f"Planning failed: {r}"
        assert r["next_phase"] == "Coding"
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Coding"
        assert len(cp["history"]) == 3

        # Coding — gates run, should pass with clean files
        r = submit("Coding", self._CODING)
        assert r["accepted"], f"Coding failed: {r}"
        assert r["next_phase"] == "Review"
        assert "gate_summary" in r, "Coding missing gate_summary"
        assert r["gate_summary"]["passed"] is True
        assert "lint" in r["gate_summary"]["passed_gates"]
        assert "types" in r["gate_summary"]["passed_gates"]
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Review"
        assert len(cp["history"]) == 4

        # Review → Testing
        r = submit("Review", self._REVIEW, next_phase="Testing")
        assert r["accepted"], f"Review failed: {r}"
        assert r["next_phase"] == "Testing"
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Testing"
        assert len(cp["history"]) == 5

        # Testing — gates run (tests only), should pass
        r = submit("Testing", self._TESTING)
        assert r["accepted"], f"Testing failed: {r}"
        assert r["next_phase"] == "Done"
        assert "gate_summary" in r, "Testing missing gate_summary"
        assert r["gate_summary"]["passed"] is True
        assert "tests" in r["gate_summary"]["passed_gates"]
        cp = json.loads((cp_dir / f"{task_id}.json").read_text())
        assert cp["phase"] == "Done"
        assert len(cp["history"]) == 6

        # Final status check
        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(status_resp["result"]["content"][0]["text"])
        assert status["status"] == "done", f"Expected done, got {status['status']}"
        assert status["phase"] == "Done"
        assert status["iteration_count"] == 6

        _stop_server(server)


class TestRecoveryRetryE2E:
    """P4-03: Validate recovery and retry E2E with deterministic transient injection."""

    _SPECS = "## Requirements\n- x\n## Scope\n- y\n## Constraints\n- z"
    _PLANNING = "## Implementation Plan\n- step1\n## File Changes\n- a.py\n## Risks\n- low"
    _CODING = "## Files Modified\n- a.py (modify)"

    def _start_isolated(self, tmp_path: Path, env: dict[str, str]) -> subprocess.Popen:
        server = subprocess.Popen(
            [_PYTHON, "-m", "sdlc"],
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
        return server

    def _advance_to_coding(self, task_id: str, server: subprocess.Popen) -> None:
        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        submit("Chatting", "Clarified.")
        submit("Specs", self._SPECS)
        submit("Planning", self._PLANNING)

    def test_transient_failure_then_success(self, tmp_path: Path) -> None:
        """Transient gate failure retries and succeeds on subsequent attempt."""
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)
        env["SDLC_TOOL_EXECUTOR_MAX_RETRIES"] = "0"
        env["SDLC_MAX_GATE_RETRY_CEILING"] = "2"
        env["SDLC_INJECT_TRANSIENT_TOOL_FAILURES"] = "1"

        server = self._start_isolated(tmp_path, env)
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-03 transient success", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_coding(task_id, server)

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        r = submit("Coding", self._CODING)
        assert r["accepted"], f"Expected accepted after transient retry success: {r}"
        assert r["next_phase"] == "Review"
        assert "gate_summary" in r
        assert r["gate_summary"]["passed"] is True

        _stop_server(server)

    def test_transient_exhaustion_stalls(self, tmp_path: Path) -> None:
        """Transient gate failure exhaustion stalls the task."""
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)
        env["SDLC_TOOL_EXECUTOR_MAX_RETRIES"] = "0"
        env["SDLC_MAX_GATE_RETRY_CEILING"] = "1"
        env["SDLC_INJECT_TRANSIENT_TOOL_FAILURES"] = "2"

        server = self._start_isolated(tmp_path, env)
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-03 exhaustion", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_coding(task_id, server)

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        r = submit("Coding", self._CODING)
        assert not r["accepted"], "Expected stall after transient exhaustion"
        assert r.get("task_stalled"), f"Expected task_stalled=True: {r}"
        assert "ceiling exhausted" in r["error"].lower()

        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        status = json.loads(status_resp["result"]["content"][0]["text"])
        assert status["status"] == "stalled"

        _stop_server(server)

    def test_retry_state_survives_restart(self, tmp_path: Path) -> None:
        """Retry state persisted in SQLite survives process restart."""
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "clean.py").write_text("x = 1\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_DIR)
        if _TOOL_BIN and os.path.exists(_TOOL_BIN):
            env["PATH"] = f"{_TOOL_BIN}:{env.get('PATH', '')}"
        db_path = tmp_path / "sdlc.db"
        cp_dir = tmp_path / "checkpoints"
        log_dir = tmp_path / "logs"
        env["SDLC_DB_PATH"] = str(db_path)
        env["SDLC_CHECKPOINT_DIR"] = str(cp_dir)
        env["SDLC_LOG_PATH"] = str(log_dir)

        # Phase 1: exhaust retry ceiling and stall the task
        env1 = {**env, "SDLC_TOOL_EXECUTOR_MAX_RETRIES": "0",
                "SDLC_MAX_GATE_RETRY_CEILING": "1",
                "SDLC_INJECT_TRANSIENT_TOOL_FAILURES": "2"}
        server = self._start_isolated(tmp_path, env1)
        rid = _next_id()
        create_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_create_task",
                "arguments": {"description": "P4-03 retry persistence", "mode": "feature"},
            },
        })
        task_id = json.loads(create_resp["result"]["content"][0]["text"])["task_id"]
        self._advance_to_coding(task_id, server)

        def submit(phase: str, output: str, next_phase: str | None = None) -> dict:
            args = {"task_id": task_id, "phase": phase, "output": output}
            if next_phase:
                args["next_phase"] = next_phase
            rid = _next_id()
            resp = _send_request(server, {
                "jsonrpc": "2.0", "id": rid,
                "method": "tools/call",
                "params": {"name": "sdlc_submit_output", "arguments": args},
            })
            return json.loads(resp["result"]["content"][0]["text"])

        r = submit("Coding", self._CODING)
        assert not r["accepted"], "Expected stall"
        assert r.get("task_stalled"), f"Expected stalled: {r}"

        # Verify retry metadata before restart
        rid = _next_id()
        status_resp = _send_request(server, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        pre_status = json.loads(status_resp["result"]["content"][0]["text"])
        assert pre_status["status"] == "stalled"
        assert pre_status["retry_count"] == 1, (
            f"Expected retry_count=1 before restart, got {pre_status['retry_count']}"
        )
        assert pre_status.get("last_failure_type") == "retry_exhausted"
        _stop_server(server)

        # Phase 2: restart with clean env — stall state must persist
        env2 = {**env}
        server2 = self._start_isolated(tmp_path, env2)
        rid = _next_id()
        status_resp2 = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {"name": "sdlc_get_status", "arguments": {"task_id": task_id}},
        })
        post_status = json.loads(status_resp2["result"]["content"][0]["text"])
        assert post_status["status"] == "stalled", (
            f"Expected stalled after restart, got {post_status['status']}"
        )
        assert post_status["retry_count"] == 1, (
            f"Expected retry_count=1 after restart, got {post_status['retry_count']}"
        )
        assert post_status["last_failure_type"] == "retry_exhausted"

        # Stalled tasks reject new submissions
        rid = _next_id()
        submit_resp = _send_request(server2, {
            "jsonrpc": "2.0", "id": rid,
            "method": "tools/call",
            "params": {
                "name": "sdlc_submit_output",
                "arguments": {
                    "task_id": task_id, "phase": "Review",
                    "output": "## Issues Found\n- none",
                },
            },
        })
        result = json.loads(submit_resp["result"]["content"][0]["text"])
        assert not result["accepted"]
        assert "stalled" in result["error"].lower() or "stalled" in result.get("error", "")

        _stop_server(server2)
