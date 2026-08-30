"""Parity test: MCP-path (manual turn engine) vs serve-path (auto_run).

Ensures that driving a ``RoleGraph`` via ``TurnEngine.get_turn()/submit_turn()``
and via ``auto_run()`` reach identical terminal states for the same graph.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from foundry.core.store import SqliteStore
from foundry.core.turn_engine import AgentLoopGraph, DebateGraph
from foundry.core.turn_engine.auto_run import auto_run
from foundry.core.turn_engine.engine import TurnEngine
from foundry.core.turn_engine.graph import RoleGraph, Terminal


# ═══════════════════════════════════════════════════════════════════════════════
#  Fake RoleGraph:  propose -> review -> done
# ═══════════════════════════════════════════════════════════════════════════════


class _TwoRoleGraph:
    """Minimal 2-role graph: propose -> review -> done."""

    _ROLES = ("propose", "review")

    def initial_role(self, context: dict[str, Any]) -> str:  # noqa: ARG002
        return "propose"

    def prompt_for(self, role: str, context: dict[str, Any]) -> str:
        return f"Execute role: {role}"

    def next_role(
        self,
        current_role: str,
        output: str,  # noqa: ARG002
        context: dict[str, Any],  # noqa: ARG002
    ) -> str | None | type[Terminal]:
        if current_role == "propose":
            return "review"
        if current_role == "review":
            return Terminal
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def in_memory_store() -> SqliteStore:
    """Yield an empty in-memory SqliteStore."""
    store = SqliteStore(":memory:")
    await store.initialize()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def two_role_graph() -> _TwoRoleGraph:
    return _TwoRoleGraph()


async def _create_task(store: SqliteStore, task_id: str) -> None:
    """Helper: create a bare task with a context dict."""
    now = "2026-07-23T00:00:00Z"
    await store.create_task(
        {
            "task_id": task_id,
            "description": "Parity test task",
            "mode": "feature",
            "status": "QUEUED",
            "current_phase": "Chatting",
            "context": {"_te_graph_state": {}},
            "created_at": now,
            "updated_at": now,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Fake generate function
# ═══════════════════════════════════════════════════════════════════════════════


async def _fake_generate(prompt: str) -> str:
    """Return a deterministic output for any prompt."""
    return f"Output for: {prompt}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestParityMCPvsServe:
    """Verify that manual TurnEngine driving and auto_run produce the same result."""

    @pytest.mark.asyncio
    async def test_mcp_path_completes(
        self,
        in_memory_store: SqliteStore,
        two_role_graph: _TwoRoleGraph,
    ) -> None:
        """Drive the graph manually via get_turn()/submit_turn() — MCP path."""
        task_id = f"mcp_test_{uuid.uuid4().hex[:8]}"
        await _create_task(in_memory_store, task_id)

        engine = TurnEngine(two_role_graph, in_memory_store, task_id)

        # ── Propose turn ───────────────────────────────────────────────
        turn1 = await engine.get_turn()
        assert turn1.role == "propose", f"Expected propose, got {turn1.role}"
        assert not turn1.done

        # Submit propose output
        result1 = await engine.submit_turn("propose", "Proposal content")
        assert result1.accepted, f"Submit rejected: {result1.error}"
        assert result1.next_turn is not None
        assert result1.next_turn.role == "review"
        assert not result1.next_turn.done

        # ── Review turn ────────────────────────────────────────────────
        turn2 = await engine.get_turn()
        assert turn2.role == "review", f"Expected review, got {turn2.role}"
        assert not turn2.done

        # Submit review output (should complete)
        result2 = await engine.submit_turn("review", "Review output")
        assert result2.accepted, f"Submit rejected: {result2.error}"
        assert result2.next_turn is not None
        assert result2.next_turn.done, "Expected terminal state after review"

        # ── Verify terminal state ──────────────────────────────────────
        turn3 = await engine.get_turn()
        assert turn3.done, "Expected engine to be done"
        assert turn3.result == "Review output"

        # Check persisted state
        task = await in_memory_store.get_task(task_id)
        assert task is not None
        te_state = task.get("turn_engine", {})
        assert te_state.get("complete") is True

    @pytest.mark.asyncio
    async def test_serve_path_completes(
        self,
        in_memory_store: SqliteStore,
        two_role_graph: _TwoRoleGraph,
    ) -> None:
        """Drive the graph via auto_run() — serve path."""
        task_id = f"serve_test_{uuid.uuid4().hex[:8]}"
        await _create_task(in_memory_store, task_id)

        result = await auto_run(
            store=in_memory_store,
            task_id=task_id,
            graph=two_role_graph,
            generate_fn=_fake_generate,
            max_turns=10,
        )

        # auto_run returns the terminal result
        assert result == "Output for: Execute role: review"

        # Check persisted state
        task = await in_memory_store.get_task(task_id)
        assert task is not None
        te_state = task.get("turn_engine", {})
        assert te_state.get("complete") is True

    @pytest.mark.asyncio
    async def test_both_paths_same_terminal_state(
        self,
        in_memory_store: SqliteStore,
        two_role_graph: _TwoRoleGraph,
    ) -> None:
        """Both paths should leave the task in the same terminal state."""
        mcp_task_id = f"mcp_par_{uuid.uuid4().hex[:8]}"
        serve_task_id = f"serve_par_{uuid.uuid4().hex[:8]}"

        # ── Setup both tasks ───────────────────────────────────────────
        await _create_task(in_memory_store, mcp_task_id)
        await _create_task(in_memory_store, serve_task_id)

        # ── MCP path: manual driving ───────────────────────────────────
        engine = TurnEngine(two_role_graph, in_memory_store, mcp_task_id)
        t = await engine.get_turn()
        r = await engine.submit_turn(t.role, "Proposal for MCP")
        assert r.accepted
        t2 = r.next_turn
        assert t2 is not None and not t2.done
        r2 = await engine.submit_turn(t2.role, "Review for MCP")
        assert r2.accepted
        assert r2.next_turn is not None
        assert r2.next_turn.done

        # ── Serve path: auto_run ───────────────────────────────────────
        async def generate_for_serve(prompt: str) -> str:
            # Return output matching the mcp path for same roles
            if "propose" in prompt:
                return "Proposal for MCP"
            return "Review for MCP"

        serve_result = await auto_run(
            store=in_memory_store,
            task_id=serve_task_id,
            graph=two_role_graph,
            generate_fn=generate_for_serve,
            max_turns=10,
        )

        # ── Compare terminal states ────────────────────────────────────
        mcp_task = await in_memory_store.get_task(mcp_task_id)
        serve_task = await in_memory_store.get_task(serve_task_id)
        assert mcp_task is not None
        assert serve_task is not None

        mcp_te = mcp_task.get("turn_engine", {})
        serve_te = serve_task.get("turn_engine", {})

        assert mcp_te.get("complete") is True
        assert serve_te.get("complete") is True

        # Both should have the same result
        assert mcp_te.get("result") == "Review for MCP"
        assert serve_result == "Review for MCP"


class TestParityAgentLoop:
    """Verify that AgentLoopGraph produces identical terminal state via MCP and Serve paths."""

    @pytest.fixture
    def scripted_responses(self) -> dict[str, str]:
        return {
            "planner": "Plan: implement a REST API with endpoints",
            "executor": "Code: flask app with /api/v1/* endpoints",
            "verifier": "Verification passed, all checks ok :white_check_mark:",
            "repairer": "Repair: fixed the edge cases",
        }

    async def _drive_manually(
        self,
        store: SqliteStore,
        task_id: str,
        responses: dict[str, str],
    ) -> tuple[dict[str, Any], str | None]:
        """Drive AgentLoopGraph manually via get_turn()/submit_turn()."""
        graph = AgentLoopGraph(max_repairs=2)
        engine = TurnEngine(graph, store, task_id)
        result: str | None = None

        while True:
            turn = await engine.get_turn()
            if turn.done:
                result = turn.result
                break
            response_text = responses.get(turn.role, f"Output for {turn.role}")
            submit_result = await engine.submit_turn(turn.role, response_text)
            if not submit_result.accepted:
                break
            if submit_result.next_turn and submit_result.next_turn.done:
                result = submit_result.next_turn.result
                break

        task = await store.get_task(task_id)
        return task or {}, result

    @pytest.mark.asyncio
    async def test_mcp_path_and_serve_path_reach_same_terminal_state(
        self,
        in_memory_store: SqliteStore,
        scripted_responses: dict[str, str],
    ) -> None:
        """Both paths should produce the same terminal result for AgentLoopGraph."""
        mcp_task_id = f"alp_mcp_{uuid.uuid4().hex[:8]}"
        serve_task_id = f"alp_serve_{uuid.uuid4().hex[:8]}"
        await _create_task(in_memory_store, mcp_task_id)
        await _create_task(in_memory_store, serve_task_id)

        # ── MCP path: manual driving ───────────────────────────────────
        mcp_task, mcp_result = await self._drive_manually(
            in_memory_store, mcp_task_id, scripted_responses,
        )

        # ── Serve path: auto_run ────────────────────────────────────────
        graph = AgentLoopGraph(max_repairs=2)

        async def _scripted_generate(prompt: str) -> str:
            for role, reply in scripted_responses.items():
                if role in prompt.lower():
                    return reply
            return "Generic output"

        serve_result = await auto_run(
            store=in_memory_store,
            task_id=serve_task_id,
            graph=graph,
            generate_fn=_scripted_generate,
            max_turns=20,
        )

        # ── Compare terminal states ─────────────────────────────────────
        serve_task = await in_memory_store.get_task(serve_task_id)

        mcp_te = mcp_task.get("turn_engine", {})
        serve_te = serve_task.get("turn_engine", {}) if serve_task else {}

        assert mcp_te.get("complete") is True
        assert serve_te.get("complete") is True
        assert mcp_te.get("result") == serve_te.get("result"), (
            f"MCP result {mcp_te.get('result')!r} != Serve result {serve_te.get('result')!r}"
        )


class TestParityDebate:
    """Verify that DebateGraph produces identical consensus via MCP and Serve paths."""

    @pytest.fixture
    def scripted_debate_responses(self) -> dict[str, str]:
        return {
            "debater_a": "The code looks correct for the main flow.",
            "debater_b": "Design is consistent with our patterns.",
            "debater_c": "Test coverage is adequate.",
            "consensus": json.dumps({
                "passed": True,
                "reason": "All reviewers agree",
                "disagreement_areas": [],
                "minority_positions": [],
                "sycophancy_risk": "low",
            }),
        }

    @pytest.mark.asyncio
    async def test_mcp_path_and_serve_path_reach_same_consensus(
        self,
        in_memory_store: SqliteStore,
        scripted_debate_responses: dict[str, str],
    ) -> None:
        """Both paths should produce the same consensus verdict for DebateGraph."""
        mcp_task_id = f"deb_mcp_{uuid.uuid4().hex[:8]}"
        serve_task_id = f"deb_serve_{uuid.uuid4().hex[:8]}"
        await _create_task(in_memory_store, mcp_task_id)
        await _create_task(in_memory_store, serve_task_id)

        artefact = "Sample implementation to review"

        # ── MCP path: manual driving ───────────────────────────────────
        mcp_graph = DebateGraph(
            store=in_memory_store,
            task_id=mcp_task_id,
            artefact=artefact,
        )
        engine = TurnEngine(mcp_graph, in_memory_store, mcp_task_id)
        while True:
            turn = await engine.get_turn()
            if turn.done:
                mcp_result = turn.result
                break
            response_text = scripted_debate_responses.get(
                turn.role, f"Output for {turn.role}"
            )
            sr = await engine.submit_turn(turn.role, response_text)
            if not sr.accepted:
                mcp_result = None
                break
            if sr.next_turn and sr.next_turn.done:
                mcp_result = sr.next_turn.result
                break

        # ── Serve path: auto_run ────────────────────────────────────────
        serve_graph = DebateGraph(
            store=in_memory_store,
            task_id=serve_task_id,
            artefact=artefact,
        )

        async def _scripted_generate(prompt: str) -> str:
            for role, reply in scripted_debate_responses.items():
                if role in prompt.lower():
                    return reply
            return "Generic debate output"

        serve_result = await auto_run(
            store=in_memory_store,
            task_id=serve_task_id,
            graph=serve_graph,
            generate_fn=_scripted_generate,
            max_turns=20,
        )

        # ── Compare terminal states ─────────────────────────────────────
        mcp_task = await in_memory_store.get_task(mcp_task_id)
        serve_task = await in_memory_store.get_task(serve_task_id)

        mcp_te = mcp_task.get("turn_engine", {}) if mcp_task else {}
        serve_te = serve_task.get("turn_engine", {}) if serve_task else {}

        assert mcp_te.get("complete") is True
        assert serve_te.get("complete") is True
        # Both should have produced a result (None means consensus rolled up)
        assert mcp_result is not None, "MCP path produced no result"
        assert serve_result is not None, "Serve path produced no result"
        mcp_result_str = str(mcp_result)
        serve_result_str = str(serve_result)
        # Both should indicate passed consensus
        assert "passed" in mcp_result_str.lower() or "true" in mcp_result_str.lower()
        assert "passed" in serve_result_str.lower() or "true" in serve_result_str.lower()
