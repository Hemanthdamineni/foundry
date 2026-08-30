"""Protocol-level tests for the MCP server.

Each test drives the real FastMCP app through an in-memory client session —
the same JSON-RPC surface a stdio/SSE client sees — against an isolated
workspace and runtime directory.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session,
)

from foundry.features.mcp.server import app

CALC_PY = '''def add(a, b):
    """Add two numbers."""
    return a + b


class Calculator:
    """A simple calculator."""

    def run(self):
        """Run a calculation using add()."""
        return add(1, 2)
'''

MAIN_PY = '''from src.calc import add


def main():
    """Entry point that calls add()."""
    print(add(2, 3))
'''


async def _call(session, name: str, **args) -> dict:
    result = await session.call_tool(name, args)
    assert not result.isError, f"{name} errored: {result.content}"
    if getattr(result, "structuredContent", None) is not None:
        return dict(result.structuredContent)
    text = result.content[0].text
    return json.loads(text)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "workspace"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "calc.py").write_text(CALC_PY)
    (ws / "src" / "main.py").write_text(MAIN_PY)

    rt = tmp_path / "runtime" / ".foundry"
    monkeypatch.setenv("FOUNDRY_DB_PATH", str(rt / "sdlc.db"))
    monkeypatch.setenv("FOUNDRY_CHECKPOINT_DIR", str(rt / "checkpoints"))
    monkeypatch.setenv("FOUNDRY_LOG_PATH", str(rt / "logs" / "sdlc.log"))
    monkeypatch.setenv("FOUNDRY_TRACE_DIR", str(rt / "traces"))
    monkeypatch.setenv("FOUNDRY_INDEX_DIR", str(rt / "index"))
    monkeypatch.setenv("FOUNDRY_MEMORY_DIR", str(rt / "memory"))
    monkeypatch.setenv("FOUNDRY_WORKSPACE_PATH", str(ws))
    monkeypatch.setenv("FOUNDRY_MCP_DISABLE_LLM", "1")
    return ws


@asynccontextmanager
async def client() -> AsyncIterator:
    """Open an in-memory client session; the lifespan runs per connection."""
    async with create_connected_server_and_client_session(app) as s:
        yield s


# ── Handshake & discovery ────────────────────────────────────────────────


async def test_tools_list_complete(workspace) -> None:
    async with client() as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        expected = {
            "sdlc_create_task",
            "sdlc_get_next_action",
            "sdlc_submit_output",
            "sdlc_request_approval",
            "sdlc_get_status",
            "sdlc_list_tasks",
            "sdlc_cancel_task",
            "sdlc_resume_task",
            "sdlc_get_trace",
            "sdlc_list_traces",
            "sdlc_get_summaries",
            "sdlc_enforce_retention",
            "sdlc_index_repository",
            "sdlc_index_files",
            "sdlc_get_dependency_context",
            "sdlc_get_index_stats",
            "sdlc_query_symbols",
            "sdlc_get_callers",
            "sdlc_get_symbol_context",
            "sdlc_debate_get_turn",
            "sdlc_debate_submit_turn",
            "sdlc_agent_get_turn",
            "sdlc_agent_submit_turn",
            "sdlc_memory_store",
            "sdlc_memory_query",
            "sdlc_memory_stats",
            "sdlc_harvest_context",
            "sdlc_check_spec_drift",
            "sdlc_schema_check",
        }
        missing = expected - names
        assert not missing, f"missing tools: {missing}"
        assert all(t.inputSchema.get("type") == "object" for t in tools.tools)



# ── Lifecycle ────────────────────────────────────────────────────────────


async def test_create_task_invalid_mode(workspace) -> None:
    async with client() as session:
        result = await session.call_tool(
            "sdlc_create_task", {"description": "x", "mode": "bogus"}
        )
        assert result.isError



async def test_full_phase_lifecycle(workspace) -> None:
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Build a calculator module"
        )
        task_id = created["task_id"]

        status = await _call(session, "sdlc_get_status", task_id=task_id)
        assert status["current_phase"] == "Chatting"

        action = await _call(session, "sdlc_get_next_action", task_id=task_id)
        assert action["phase"] == "Chatting"

        submitted = await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Chatting",
            output="User wants a calculator.",
        )
        assert submitted["accepted"] is True
        assert submitted["next_phase"] == "Specs"

        specs = await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Specs",
            output=(
                "## Requirements\n- add numbers\n## Scope\n- calc only\n"
                "## Acceptance Criteria\n- tests pass"
            ),
        )
        assert specs["accepted"] is True
        assert specs["next_phase"] == "Planning"



async def test_approval_list_cancel_resume(workspace) -> None:
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Task for admin ops"
        )
        task_id = created["task_id"]

        approval = await _call(
            session,
            "sdlc_request_approval",
            task_id=task_id,
            phase="Chatting",
            summary="Proceed?",
            approved=True,
        )
        assert approval.get("approved") is True or approval.get("status") == "ok"

        listed = await _call(session, "sdlc_list_tasks")
        ids = [t["task_id"] for t in listed["tasks"]]
        assert task_id in ids

        cancelled = await _call(session, "sdlc_cancel_task", task_id=task_id)
        assert cancelled["status"] == "cancelled"

        resumed = await _call(session, "sdlc_resume_task", task_id=task_id)
        assert resumed.get("task_id") == task_id
        assert "error" not in resumed



async def test_get_status_missing_task(workspace) -> None:
    async with client() as session:
        result = await _call(session, "sdlc_get_status", task_id="nope")
        assert "error" in result



# ── Tracing ──────────────────────────────────────────────────────────────


async def test_trace_tools_respond(workspace) -> None:
    async with client() as session:
        traces = await _call(session, "sdlc_list_traces")
        assert isinstance(traces, dict)
        summaries = await _call(session, "sdlc_get_summaries")
        assert isinstance(summaries, dict)
        retention = await _call(session, "sdlc_enforce_retention")
        assert isinstance(retention, dict)



# ── Indexing & symbols ───────────────────────────────────────────────────


async def test_index_repository_and_files(workspace) -> None:
    async with client() as session:
        stats_before = await _call(session, "sdlc_get_index_stats")
        assert "error" not in stats_before

        indexed = await _call(session, "sdlc_index_repository", mode="incremental")
        assert indexed.get("errors", 0) == 0 or "indexed" in indexed

        files = await _call(
            session, "sdlc_index_files", file_paths=["src/calc.py"]
        )
        assert "error" not in files

        bad_mode = await _call(session, "sdlc_index_repository", mode="bogus")
        assert "error" in bad_mode



async def test_dependency_context(workspace) -> None:
    async with client() as session:
        await _call(session, "sdlc_index_repository", mode="incremental")
        dep = await _call(
            session, "sdlc_get_dependency_context", file_path="src/main.py"
        )
        assert "error" not in dep



async def test_symbol_tools(workspace) -> None:
    async with client() as session:
        query = await _call(session, "sdlc_query_symbols", query="Calculator")
        assert query["count"] >= 1
        assert any(s["name"] == "Calculator" for s in query["symbols"])

        ctx_result = await _call(
            session, "sdlc_get_symbol_context", qualified_name="calc.add"
        )
        assert ctx_result["symbol"]["name"] == "add"
        assert {"callers", "callees", "imports", "inherits"} <= set(ctx_result)

        callers = await _call(session, "sdlc_get_callers", qualified_name="calc.add")
        assert "callers" in callers



# ── Memory ───────────────────────────────────────────────────────────────


async def test_memory_store_query_stats(workspace) -> None:
    async with client() as session:
        stored = await _call(
            session,
            "sdlc_memory_store",
            content="Prefer pytest fixtures over setUp",
            tags=["protocol-test"],
            importance=0.9,
        )
        assert stored["status"] == "ok"

        found = await _call(
            session, "sdlc_memory_query", tags=["protocol-test"]
        )
        assert found["count"] >= 1
        assert any("pytest fixtures" in e["content"] for e in found["engrams"])

        stats = await _call(session, "sdlc_memory_stats")
        assert stats["status"] == "ok"



# ── Debate turn engine ───────────────────────────────────────────────────


async def _task_with_spec(session) -> str:
    created = await _call(
        session, "sdlc_create_task", description="Debate target task"
    )
    task_id = created["task_id"]
    await _call(
        session,
        "sdlc_submit_output",
        task_id=task_id,
        phase="Chatting",
        output="Wants feature.",
    )
    await _call(
        session,
        "sdlc_submit_output",
        task_id=task_id,
        phase="Specs",
        output=(
            "## Requirements\n- thing\n## Scope\n- minimal\n"
            "## Acceptance Criteria\n- works"
        ),
    )
    return task_id


async def test_debate_full_cycle(workspace) -> None:
    async with client() as session:
        task_id = await _task_with_spec(session)

        first = await _call(
            session, "sdlc_debate_get_turn", task_id=task_id, phase="Specs"
        )
        assert first["role"] == "debater_a"
        assert first["prompt"]
        assert first["done"] is False

        for persona in ("debater_a", "debater_b"):
            step = await _call(
                session,
                "sdlc_debate_submit_turn",
                task_id=task_id,
                phase="Specs",
                persona=persona,
                output=f"{persona} evaluation notes.",
            )
            assert step["accepted"] is True

        wrong = await _call(
            session,
            "sdlc_debate_submit_turn",
            task_id=task_id,
            phase="Specs",
            persona="consensus",
            output="too early",
        )
        assert wrong["accepted"] is False
        assert "Role mismatch" in wrong["error"]

        final = await _call(
            session,
            "sdlc_debate_submit_turn",
            task_id=task_id,
            phase="Specs",
            persona="debater_c",
            output="debater_c agrees.",
        )
        assert final["accepted"] is True
        assert final["next_role"] == "consensus"

        consensus = await _call(
            session,
            "sdlc_debate_submit_turn",
            task_id=task_id,
            phase="Specs",
            persona="consensus",
            output="Consensus reached.",
        )
        assert consensus["done"] is True
        assert consensus["result"] == "Consensus reached."



# ── Agent-loop turn engine ───────────────────────────────────────────────


async def test_agent_loop_cycle(workspace) -> None:
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Agent loop target"
        )
        task_id = created["task_id"]

        first = await _call(session, "sdlc_agent_get_turn", task_id=task_id)
        assert first["role"] == "planner"

        step = await _call(
            session,
            "sdlc_agent_submit_turn",
            task_id=task_id,
            role="planner",
            output="1. implement 2. verify",
        )
        assert step["next_role"] == "executor"

        step = await _call(
            session,
            "sdlc_agent_submit_turn",
            task_id=task_id,
            role="executor",
            output="Implemented the change.",
        )
        assert step["next_role"] == "verifier"

        done = await _call(
            session,
            "sdlc_agent_submit_turn",
            task_id=task_id,
            role="verifier",
            output="PASS all checks green",
        )
        assert done["done"] is True



# ── Context harvesting & spec drift ──────────────────────────────────────


async def test_harvest_context(workspace) -> None:
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Add OAuth login support"
        )
        bundle = await _call(
            session, "sdlc_harvest_context", task_id=created["task_id"]
        )
        assert bundle["total_questions"] > 0
        assert isinstance(bundle["ready_for_spec"], bool)
        assert bundle["context_text"]



async def test_check_spec_drift_no_spec_then_detection(workspace) -> None:
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Drift check task"
        )
        task_id = created["task_id"]

        none = await _call(
            session,
            "sdlc_check_spec_drift",
            task_id=task_id,
            output="anything",
        )
        assert none["status"] == "no_spec"

        spec_text = (
            "## Requirements\n- must use SQLite storage\n- CLI only\n"
            "## Scope\n- no server\n## Constraints\n- stdlib only"
        )
        await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Chatting",
            output="ok",
        )
        submitted = await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Specs",
            output=spec_text,
        )
        assert submitted["next_phase"] == "Planning"

        drifted = await _call(
            session,
            "sdlc_check_spec_drift",
            task_id=task_id,
            output="Also implement a Postgres backend and a web dashboard.",
        )
        assert drifted["drift_detected"] is True
        assert drifted["violation_count"] >= 1



# ── Deterministic schema checks ──────────────────────────────────────────


async def test_schema_check_valid_and_invalid(workspace) -> None:
    async with client() as session:
        good = await _call(
            session,
            "sdlc_schema_check",
            phase="Specs",
            output="## Requirements\nr\n## Scope\ns\n## Constraints\nc",
        )
        assert good["valid"] is True

        bad = await _call(
            session, "sdlc_schema_check", phase="Specs", output="no sections"
        )
        assert bad["valid"] is False
        assert bad["violation_count"] >= 1



# ── Resources ────────────────────────────────────────────────────────────


async def test_phase_graph_resource(workspace) -> None:
    async with client() as session:
        result = await session.read_resource("sdlc://phase-graph")
        text = result.contents[0].text
        assert "Phase Graph" in text
        assert "->" in text



# ── Judge wiring (fake provider) ─────────────────────────────────────────


async def test_judge_verdict_flows_through_submit(workspace, monkeypatch) -> None:
    """With FOUNDRY_MCP_FAKE_LLM the judge evaluates and its verdict is returned."""
    monkeypatch.setenv("FOUNDRY_MCP_FAKE_LLM", "1")
    async with client() as session:
        created = await _call(
            session, "sdlc_create_task", description="Judged task"
        )
        task_id = created["task_id"]

        await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Chatting",
            output="Wants a thing.",
        )
        await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Specs",
            output=(
                "## Requirements\n- thing\n## Scope\n- minimal\n"
                "## Constraints\n- none"
            ),
        )
        result = await _call(
            session,
            "sdlc_submit_output",
            task_id=task_id,
            phase="Planning",
            output=(
                "## Implementation Plan\n1. build\n## File Changes\n- x.py\n"
                "## Risks\n- low"
            ),
        )

        assert result["accepted"] is True
        verdict = result["judge_verdict"]
        assert verdict is not None, "expected judge verdict on Planning->Coding"
        assert verdict["passed"] is True
        assert verdict["reason"] == "fake judge pass"
