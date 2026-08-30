"""MultiAgentSpawner — dynamic agent creation for parallel task execution.

Allows the TaskScheduler to spawn independent agent instances that each
run their own TurnEngine loop with isolated memory and context.

Architecture reference:
    L6 Coordination — "Multi-agent spawning"
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from foundry.core.logging import get_logger
from foundry.core.session.manager import SessionManager, SessionMessage, SessionState, SessionStatus

log = get_logger("foundry.multi_agent")


# --------------------------------------------------------------------------- #
#  Agent instance
# --------------------------------------------------------------------------- #


class AgentStatus:
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentInstance:
    """A spawned agent instance with its own session and context."""

    agent_id: str
    role: str  # "planner", "executor", "verifier", "debater", etc.
    session_id: str | None = None
    workspace_id: str | None = None
    status: str = AgentStatus.IDLE
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


# --------------------------------------------------------------------------- #
#  MultiAgentSpawner
# --------------------------------------------------------------------------- #


class MultiAgentSpawner:
    """Spawns and manages independent agent instances.

    Usage::

        spawner = MultiAgentSpawner(
            session_manager=session_mgr,
            generate_fn=my_llm_generate,
        )

        # Spawn a planner agent
        planner = await spawner.spawn("planner", prompt="Plan the auth system")

        # Spawn executor agents in parallel
        executors = await spawner.spawn_group(
            role="executor",
            prompts=["Implement login", "Implement signup", "Implement logout"],
        )

        # Wait for all to complete
        results = await spawner.wait_all([planner] + executors)
    """

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        generate_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._generate_fn = generate_fn
        self._agents: dict[str, AgentInstance] = {}
        self._running: dict[str, asyncio.Task[None]] = {}

    async def spawn(
        self,
        role: str,
        prompt: str,
        *,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInstance:
        """Spawn a single agent instance."""
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        # Create a session for this agent
        session_id = None
        if self._session_manager:
            session = await self._session_manager.create(
                workspace_id=workspace_id,
                metadata={"agent_id": agent_id, "role": role},
            )
            session_id = session.session_id

            # Add the initial prompt as a user message
            await self._session_manager.add_message(
                session_id,
                SessionMessage(role="user", content=prompt),
            )

        agent = AgentInstance(
            agent_id=agent_id,
            role=role,
            session_id=session_id,
            workspace_id=workspace_id,
            metadata={**(metadata or {}), "prompt": prompt},
        )

        self._agents[agent_id] = agent
        log.info("agent spawned: %s (role=%s)", agent_id, role)

        return agent

    async def spawn_group(
        self,
        role: str,
        prompts: list[str],
        *,
        workspace_id: str | None = None,
    ) -> list[AgentInstance]:
        """Spawn multiple agents with the same role."""
        agents = []
        for prompt in prompts:
            agent = await self.spawn(role, prompt, workspace_id=workspace_id)
            agents.append(agent)
        return agents

    async def run(self, agent_id: str) -> str | None:
        """Run an agent to completion.

        Executes the agent's prompt through the generate function
        and stores the result.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        agent.status = AgentStatus.RUNNING
        agent.started_at = time.time()

        try:
            if self._generate_fn is None:
                result = f"Agent {agent_id} completed (no generate_fn)"
            else:
                # Get the initial prompt from session
                prompt = agent.metadata.get("prompt", f"Execute role: {agent.role}")
                if self._session_manager and agent.session_id:
                    session = await self._session_manager.get(agent.session_id)
                    if session and session.messages:
                        prompt = session.messages[-1].content

                result = await self._generate_fn(prompt)

            agent.result = result
            agent.status = AgentStatus.COMPLETED
            agent.completed_at = time.time()

            # Store result in session
            if self._session_manager and agent.session_id:
                await self._session_manager.add_message(
                    agent.session_id,
                    SessionMessage(role="assistant", content=result),
                )

            log.info(
                "agent completed: %s (duration=%.1fs)",
                agent_id,
                agent.duration_s or 0,
            )

            return result

        except Exception as exc:
            agent.error = str(exc)
            agent.status = AgentStatus.FAILED
            agent.completed_at = time.time()
            log.error("agent failed: %s — %s", agent_id, exc)
            return None

    async def run_group(self, agent_ids: list[str]) -> dict[str, str | None]:
        """Run multiple agents in parallel."""
        results: dict[str, str | None] = {}

        async def _run_one(aid: str) -> None:
            try:
                result = await self.run(aid)
                results[aid] = result
            except Exception as exc:
                results[aid] = None
                agent = self._agents.get(aid)
                if agent:
                    agent.error = str(exc)
                    agent.status = AgentStatus.FAILED

        tasks = [asyncio.create_task(_run_one(aid)) for aid in agent_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def wait_all(self, agents: list[AgentInstance]) -> dict[str, str | None]:
        """Wait for a list of agents to complete."""
        return await self.run_group([a.agent_id for a in agents])

    def get_agent(self, agent_id: str) -> AgentInstance | None:
        return self._agents.get(agent_id)

    def list_agents(
        self,
        *,
        role: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AgentInstance]:
        results = list(self._agents.values())
        if role:
            results = [a for a in results if a.role == role]
        if status:
            results = [a for a in results if a.status == status]
        return sorted(results, key=lambda a: a.created_at, reverse=True)[:limit]

    @property
    def stats(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        role_counts: dict[str, int] = {}
        for agent in self._agents.values():
            status_counts[agent.status] = status_counts.get(agent.status, 0) + 1
            role_counts[agent.role] = role_counts.get(agent.role, 0) + 1

        return {
            "total": len(self._agents),
            "by_status": status_counts,
            "by_role": role_counts,
        }
