"""Tests for MultiAgentSpawner — dynamic agent creation."""

from __future__ import annotations

import asyncio

import pytest

from foundry.core.multi_agent.spawner import (
    AgentInstance,
    AgentStatus,
    MultiAgentSpawner,
)


class TestAgentInstance:
    def test_duration_not_started(self) -> None:
        agent = AgentInstance(agent_id="a1", role="executor")
        assert agent.duration_s is None

    def test_duration_running(self) -> None:
        agent = AgentInstance(agent_id="a1", role="executor", started_at=100.0)
        assert agent.duration_s is not None
        assert agent.duration_s > 0

    def test_to_dict(self) -> None:
        agent = AgentInstance(
            agent_id="a1",
            role="planner",
            status=AgentStatus.RUNNING,
        )
        d = agent.to_dict()
        assert d["agent_id"] == "a1"
        assert d["role"] == "planner"
        assert d["status"] == "running"


class TestMultiAgentSpawner:
    @pytest.mark.asyncio
    async def test_spawn_agent(self) -> None:
        spawner = MultiAgentSpawner()
        agent = await spawner.spawn("planner", "Plan the auth system")
        assert agent.agent_id.startswith("agent_")
        assert agent.role == "planner"
        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_spawn_group(self) -> None:
        spawner = MultiAgentSpawner()
        agents = await spawner.spawn_group(
            "executor",
            ["Task 1", "Task 2", "Task 3"],
        )
        assert len(agents) == 3
        assert all(a.role == "executor" for a in agents)

    @pytest.mark.asyncio
    async def test_run_agent(self) -> None:
        async def mock_generate(prompt: str) -> str:
            return f"Result for: {prompt}"

        spawner = MultiAgentSpawner(generate_fn=mock_generate)
        agent = await spawner.spawn("executor", "Implement login")
        result = await spawner.run(agent.agent_id)

        assert result == "Result for: Implement login"
        assert agent.status == AgentStatus.COMPLETED
        assert agent.result == result

    @pytest.mark.asyncio
    async def test_run_group_parallel(self) -> None:
        call_count = 0

        async def mock_generate(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return f"Done: {prompt}"

        spawner = MultiAgentSpawner(generate_fn=mock_generate)
        agents = await spawner.spawn_group("executor", ["T1", "T2", "T3"])

        results = await spawner.wait_all(agents)
        assert len(results) == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_list_agents(self) -> None:
        spawner = MultiAgentSpawner()
        await spawner.spawn("planner", "Plan")
        await spawner.spawn("executor", "Execute")
        await spawner.spawn("verifier", "Verify")

        all_agents = spawner.list_agents()
        assert len(all_agents) == 3

        executors = spawner.list_agents(role="executor")
        assert len(executors) == 1

    @pytest.mark.asyncio
    async def test_stats(self) -> None:
        spawner = MultiAgentSpawner()
        await spawner.spawn("planner", "Plan")
        await spawner.spawn("executor", "Exec 1")
        await spawner.spawn("executor", "Exec 2")

        stats = spawner.stats
        assert stats["total"] == 3
        assert stats["by_role"]["planner"] == 1
        assert stats["by_role"]["executor"] == 2

    @pytest.mark.asyncio
    async def test_no_generate_fn(self) -> None:
        spawner = MultiAgentSpawner()
        agent = await spawner.spawn("executor", "Test")
        result = await spawner.run(agent.agent_id)
        assert "no generate_fn" in result
        assert agent.status == AgentStatus.COMPLETED
