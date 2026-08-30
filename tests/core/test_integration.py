"""Integration tests — validate component interactions."""

from __future__ import annotations

import asyncio

import pytest

from foundry.core.capability_router import CapabilityRouter, RigorLevel
from foundry.core.context_graph import ContextGraph
from foundry.core.diff_engine import DiffEngine
from foundry.core.governance import GovernanceGate
from foundry.core.memory.manager import MemoryManager, MemoryTier
from foundry.core.scheduler.task_scheduler import TaskScheduler, TaskStatus
from foundry.core.session.manager import SessionManager, SessionMessage, SessionStatus
from foundry.core.terminal.session import TerminalSession
from foundry.core.workspace.manager import WorkspaceBoundaries


class TestGovernanceIntegration:
    """Test GovernanceGate + CapabilityRouter + WorkspaceBoundaries."""

    def test_governance_allows_standard_task(self) -> None:
        gate = GovernanceGate()
        decision = gate.check("Add a comment to the function")
        assert decision.allowed is True
        assert decision.rigor == RigorLevel.MINIMAL

    def test_governance_allows_refactoring(self) -> None:
        gate = GovernanceGate()
        decision = gate.check("Refactor the authentication module")
        assert decision.allowed is True
        assert decision.rigor == RigorLevel.THOROUGH

    def test_governance_blocks_restricted_workspace(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(autonomy_level="restricted")
        decision = gate.check("Implement a feature", boundaries=boundaries)
        assert decision.allowed is True
        assert decision.use_debate is False
        assert decision.max_repairs <= 1

    def test_governance_blocks_budget(self) -> None:
        gate = GovernanceGate()
        boundaries = WorkspaceBoundaries(max_budget=10.0)
        decision = gate.check(
            "Implement something",
            boundaries=boundaries,
            current_budget_spent=15.0,
        )
        assert decision.allowed is False


class TestSessionSchedulerIntegration:
    """Test TaskScheduler + CapabilityRouter + SessionManager."""

    @pytest.mark.asyncio
    async def test_scheduler_with_routing(self) -> None:
        async def mock_generate(prompt: str) -> str:
            return f"Done: {prompt}"

        scheduler = TaskScheduler(generate_fn=mock_generate)

        # Schedule a task
        task = scheduler.schedule("Implement REST API")
        assert task.routing is not None
        assert task.routing.rigor in (RigorLevel.STANDARD, RigorLevel.THOROUGH)

        # Run it
        result = await scheduler.run(task.task_id)
        assert result is not None
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_parallel_tasks(self) -> None:
        async def mock_generate(prompt: str) -> str:
            await asyncio.sleep(0.01)
            return f"Done: {prompt}"

        scheduler = TaskScheduler(max_concurrent=3, generate_fn=mock_generate)
        scheduler.schedule("Add comment")
        scheduler.schedule("Refactor auth module")
        scheduler.schedule("Implement new feature")

        results = await scheduler.run_all()
        assert len(results) == 3


class TestContextGraphIntegration:
    """Test ContextGraph + query + relationships."""

    def test_full_workflow(self) -> None:
        graph = ContextGraph()

        content = '''
class AuthService:
    """Handles authentication."""

    def authenticate(self, username, password):
        """Authenticate a user."""
        return self._validate(username, password)

    def _validate(self, username, password):
        """Validate credentials."""
        return True
'''
        graph.add_file("auth.py", content)

        # Query for symbols
        symbols = graph.query("authentication validate")
        assert len(symbols) > 0

        # Get file symbols
        file_symbols = graph.get_file_symbols("auth.py")
        assert len(file_symbols) == 3  # AuthService, authenticate, _validate

        # Verify symbol kinds
        kinds = [s.kind.value for s in file_symbols]
        assert "class" in kinds
        assert "method" in kinds

        # Stats
        stats = graph.stats
        assert stats["total_symbols"] == 3
        assert stats["files_indexed"] == 1


class TestMemoryIntegration:
    """Test MemoryManager + MemoryTier."""

    @pytest.mark.asyncio
    async def test_full_workflow(self) -> None:
        memory = MemoryManager()

        await memory.store("Auth uses JWT", tier=MemoryTier.HOT, tags=["auth"])
        await memory.store("DB uses PostgreSQL", tier=MemoryTier.WARM, tags=["db"])
        await memory.store("Deploy uses K8s", tier=MemoryTier.COLD, tags=["deploy"])

        # Query by tag
        results = memory.query("auth", tags=["auth"])
        assert len(results) == 1

        # Query by content word
        results = memory.query("PostgreSQL")
        assert len(results) == 1

        # Hot context
        ctx = memory.get_hot_context(max_tokens=500)
        assert "JWT" in ctx

        # Promote
        memory.promote("DB uses PostgreSQL")
        assert len(memory._hot) == 2


class TestTerminalIntegration:
    """Test TerminalSession."""

    @pytest.mark.asyncio
    async def test_run_and_list(self) -> None:
        terminal = TerminalSession()
        result = await terminal.run("echo integration_test")
        assert result.success is True
        assert "integration_test" in result.stdout

        processes = terminal.list_processes()
        assert len(processes) >= 1


class TestDiffEngineIntegration:
    """Test DiffEngine."""

    def test_diff_and_patch(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        (tmp_path / "test.py").write_text("old = 1\n")

        diff = engine.diff_file_on_disk("test.py", "new = 2\n")
        assert diff is not None
        assert diff.has_changes is True

        result = engine.apply_patch("test.py", "new = 2\n")
        assert result.success is True
        assert (tmp_path / "test.py").read_text() == "new = 2\n"

        engine.revert("test.py")
        assert (tmp_path / "test.py").read_text() == "old = 1\n"


class TestCrossComponentIntegration:
    """Test multiple components working together."""

    @pytest.mark.asyncio
    async def test_governance_scheduler_pipeline(self) -> None:
        """Governance checks → Scheduler routing → Task execution."""
        gate = GovernanceGate()

        async def mock_generate(prompt: str) -> str:
            return f"Generated: {prompt}"

        scheduler = TaskScheduler(generate_fn=mock_generate)

        # Governance check
        decision = gate.check("Refactor the auth module")
        assert decision.allowed is True

        # Schedule with routing
        task = scheduler.schedule(
            "Refactor the auth module",
            metadata={"governance_rigor": decision.rigor.value},
        )
        assert task.routing.rigor == RigorLevel.THOROUGH

        # Execute
        result = await scheduler.run(task.task_id)
        assert result is not None
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_memory_session_pipeline(self) -> None:
        """Memory stores → Session context → Query."""
        memory = MemoryManager()

        # Store some memories
        await memory.store("Auth uses JWT tokens", tags=["auth", "jwt"])
        await memory.store("API uses REST endpoints", tags=["api", "rest"])

        # Query
        results = memory.query("authentication tokens")
        assert len(results) >= 1

        # Hot context for prompt
        ctx = memory.get_hot_context(max_tokens=1000)
        assert len(ctx) > 0
