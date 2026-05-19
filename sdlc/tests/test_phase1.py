"""Tests for Phase 1 — Enforcement Spine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdlc.engine.checkpoint import CheckpointManager
from sdlc.engine.execution_policy import ExecutionPolicy
from sdlc.engine.orchestrator import OrchestratorError, OrchestratorFSM
from sdlc.engine.phase_graph import PhaseGraph, PhaseGraphError
from sdlc.models import BudgetPolicy, Checkpoint, FailureType, PhaseRecord, Task

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent
GRAPH_FILE = PROJECT_DIR / "graphs" / "feature.yaml"


class TestPhaseGraph:
    def test_load_feature_graph(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        assert "Chatting" in graph.phases
        assert "Done" in graph.phases
        assert graph.is_valid_transition("Specs", "Planning")
        assert not graph.is_valid_transition("Planning", "Specs")

    def test_review_loop(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        assert graph.is_valid_transition("Coding", "Review")
        assert graph.is_valid_transition("Review", "Coding")
        assert graph.is_valid_transition("Review", "Testing")

    def test_no_outgoing_from_done(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        assert graph.possible_next("Done") == []

    def test_progress_calculation(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        assert graph.progress("Chatting") == pytest.approx(14.28, rel=0.5)
        assert graph.progress("Done") == 100.0

    def test_validate_no_phases(self) -> None:
        with pytest.raises(PhaseGraphError, match="at least one phase"):
            PhaseGraph({"transitions": []})

    def test_validate_no_done(self) -> None:
        with pytest.raises(PhaseGraphError, match="Done"):
            PhaseGraph({"phases": ["A"], "transitions": []})

    def test_unreachable_phases(self) -> None:
        with pytest.raises(PhaseGraphError, match="Unreachable"):
            PhaseGraph({
                "phases": ["Start", "Done", "Orphan"],
                "transitions": [{"from": "Start", "to": "Done"}, {"from": "Orphan", "to": "Done"}],
            })

    def test_done_has_outgoing(self) -> None:
        with pytest.raises(PhaseGraphError, match="must have no outgoing"):
            PhaseGraph({
                "phases": ["Start", "Done"],
                "transitions": [{"from": "Start", "to": "Done"}, {"from": "Done", "to": "Start"}],
            })

    def test_from_dict(self) -> None:
        graph = PhaseGraph({
            "phases": ["A", "B", "Done"],
            "transitions": [{"from": "A", "to": "B"}, {"from": "B", "to": "Done"}],
        })
        assert graph.phases == ["A", "B", "Done"]
        assert graph.next_phase("A") == "B"

    def test_possible_next_multiple(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        assert set(graph.possible_next("Review")) == {"Coding", "Testing"}


class TestOrchestratorFSM:
    def test_submit_simple_transition(self) -> None:
        graph = PhaseGraph({
            "phases": ["A", "B", "Done"],
            "transitions": [{"from": "A", "to": "B"}, {"from": "B", "to": "Done"}],
        })
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        assert fsm.submit("A") == "B"
        assert fsm.submit("B") == "Done"

    def test_submit_review_loop_coding(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        assert fsm.submit("Coding") == "Review"

    def test_submit_review_loop_forward(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        result = fsm.submit("Review", target="Testing")
        assert result == "Testing"
        result = fsm.submit("Review", target="Coding")
        assert result == "Coding"

    def test_can_submit(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        assert fsm.can_submit("Specs")
        assert not fsm.can_submit("Done")

    def test_is_terminal(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        assert fsm.is_terminal("Done")
        assert not fsm.is_terminal("Coding")

    def test_invalid_phase(self) -> None:
        graph = PhaseGraph.from_file(GRAPH_FILE)
        policy = ExecutionPolicy()
        fsm = OrchestratorFSM(graph, policy)
        with pytest.raises(OrchestratorError, match="Unknown phase"):
            fsm.submit("NonExistent")


class TestExecutionPolicy:
    @pytest.mark.asyncio
    async def test_budget_ok(self) -> None:
        policy = ExecutionPolicy()
        task = Task(task_id="t1", description="test", iteration_count=0)
        decision = await policy.check_budget(task)
        assert decision.action.value == "proceed"

    @pytest.mark.asyncio
    async def test_budget_exceeded_iterations(self) -> None:
        policy = ExecutionPolicy()
        budget = BudgetPolicy(max_review_cycles=2)
        task = Task(task_id="t1", description="test", iteration_count=3)
        decision = await policy.check_budget(task, budget)
        assert decision.action.value == "abort"

    @pytest.mark.asyncio
    async def test_budget_exceeded_runtime(self) -> None:
        policy = ExecutionPolicy()
        budget = BudgetPolicy(max_runtime_minutes=0)
        old = datetime.now(UTC).replace(year=2020)
        task = Task(task_id="t1", description="test", created_at=old)
        decision = await policy.check_budget(task, budget)
        assert decision.action.value == "abort"

    @pytest.mark.asyncio
    async def test_classify_model_timeout(self) -> None:
        policy = ExecutionPolicy()
        ft = await policy.classify_failure("Ollama timed out")
        assert ft == FailureType.RETRYABLE_MODEL

    @pytest.mark.asyncio
    async def test_classify_phase_mismatch(self) -> None:
        policy = ExecutionPolicy()
        ft = await policy.classify_failure("Phase mismatch")
        assert ft == FailureType.TERMINAL_PHASE

    @pytest.mark.asyncio
    async def test_classify_sandbox(self) -> None:
        policy = ExecutionPolicy()
        ft = await policy.classify_failure("bwrap: permission denied")
        assert ft == FailureType.TERMINAL_SANDBOX

    @pytest.mark.asyncio
    async def test_retry_attempt_1(self) -> None:
        policy = ExecutionPolicy()
        d = await policy.decide_retry(FailureType.RETRYABLE_MODEL, 0)
        assert d.action.value == "retry"
        assert d.retry_after_s == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted(self) -> None:
        policy = ExecutionPolicy()
        d = await policy.decide_retry(FailureType.RETRYABLE_MODEL, 3)
        assert d.action.value == "abort"

    @pytest.mark.asyncio
    async def test_terminal_no_retry(self) -> None:
        policy = ExecutionPolicy()
        d = await policy.decide_retry(FailureType.TERMINAL_VALIDATION, 0)
        assert d.action.value == "abort"

    @pytest.mark.asyncio
    async def test_escalate(self) -> None:
        policy = ExecutionPolicy()
        task = Task(task_id="t1", description="test")
        assert await policy.should_escalate(task, 3) is True
        assert await policy.should_escalate(task, 1) is False


class TestCheckpoint:
    def test_save_and_restore(self, tmp_path) -> None:
        mgr = CheckpointManager(tmp_path)
        cp = Checkpoint(task_id="t1", phase="Coding", history=[], iteration_count=2)
        mgr.save(cp)
        restored = mgr.restore("t1")
        assert restored is not None
        assert restored.task_id == "t1"
        assert restored.phase == "Coding"
        assert restored.iteration_count == 2

    def test_restore_nonexistent(self, tmp_path) -> None:
        mgr = CheckpointManager(tmp_path)
        assert mgr.restore("nonexistent") is None

    def test_save_with_history(self, tmp_path) -> None:
        mgr = CheckpointManager(tmp_path)
        rec = PhaseRecord(phase="Specs", output="## Requirements")
        cp = Checkpoint(
            task_id="t2", phase="Planning", history=[rec], iteration_count=1
        )
        mgr.save(cp)
        restored = mgr.restore("t2")
        assert restored is not None
        assert len(restored.history) == 1
        assert restored.history[0].phase == "Specs"

    def test_delete(self, tmp_path) -> None:
        mgr = CheckpointManager(tmp_path)
        cp = Checkpoint(task_id="t3", phase="Done", history=[], iteration_count=0)
        mgr.save(cp)
        mgr.delete("t3")
        assert mgr.restore("t3") is None

    def test_list_task_ids(self, tmp_path) -> None:
        mgr = CheckpointManager(tmp_path)
        for tid in ["a", "b", "c"]:
            mgr.save(Checkpoint(task_id=tid, phase="X", history=[], iteration_count=0))
        ids = mgr.list_task_ids()
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids


class TestAdapterBase:
    def test_capability_enum(self) -> None:
        from sdlc.adapters.base import ToolCapability
        assert ToolCapability.LINT == "lint"
        assert ToolCapability.TESTING == "testing"
        assert ToolCapability.CODE_GRAPH == "code_graph"
