"""SDLC MCP server — exposes SDLC task orchestration as MCP tools.

Four tools are provided:

- ``sdlc_create_task`` — create a new SDLC task
- ``sdlc_get_next_action`` — get the next phase action for a task
- ``sdlc_submit_output`` — submit phase output for judge/debate evaluation
- ``sdlc_list_tasks`` — list tasks by status
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from sdlc_judge.base import LLMProvider
from sdlc_judge.engine import JudgeEngine
from sdlc_models.phases import (
    BudgetPolicy,
    Phase,
    Task,
    TaskStatus,
    normalize_phase,
)
from sdlc_phases.graph import PhaseGraph
from sdlc_phases.orchestrator import OrchestratorFSM
from sdlc_store.sqlite import SqliteStore

# ---------------------------------------------------------------------------
#  Embedded phase graph (matches foundry feature.yaml)
# ---------------------------------------------------------------------------

_FEATURE_GRAPH: dict[str, Any] = {
    "phases": [
        "Chatting",
        "Specs",
        "Planning",
        "Coding",
        "Review",
        "Testing",
        "Done",
    ],
    "transitions": [
        {"from": "Chatting", "to": "Specs"},
        {"from": "Chatting", "to": "Done"},
        {"from": "Specs", "to": "Planning"},
        {"from": "Planning", "to": "Coding"},
        {"from": "Coding", "to": "Review"},
        {"from": "Review", "to": "Coding"},
        {"from": "Review", "to": "Testing"},
        {"from": "Testing", "to": "Done"},
    ],
}

# ---------------------------------------------------------------------------
#  Concrete LLM provider (Ollama)
# ---------------------------------------------------------------------------


class _OllamaProvider(LLMProvider):
    """Minimal Ollama provider wrapping the /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        default_model: str = "qwen3:8b",
        timeout_s: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout_s = timeout_s

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens
        if response_format is not None:
            body["format"] = response_format

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=body)
            resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        message = data.get("message", {})
        return str(message.get("content", ""))

    async def healthcheck(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
#  Server
# ---------------------------------------------------------------------------


class SDLCMCPServer:
    """Canonical SDLC MCP server.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database.
    ollama_url:
        Base URL of a running Ollama instance.
    ollama_model:
        Default model identifier for debate agents.
    judge_model:
        Model used for judge evaluation (defaults to *ollama_model*).
    """

    def __init__(
        self,
        db_path: str,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3:8b",
        judge_model: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._ollama_url = ollama_url
        self._ollama_model = ollama_model
        self._judge_model = judge_model or ollama_model

        # Lazy-init resources
        self._store: SqliteStore | None = None
        self._provider: _OllamaProvider | None = None
        self._judge: JudgeEngine | None = None
        self._fsm: OrchestratorFSM | None = None

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        """Boot resources on first use."""
        if self._store is not None:
            return

        self._graph = PhaseGraph(_FEATURE_GRAPH)
        self._fsm = OrchestratorFSM(self._graph)

        self._store = SqliteStore(self._db_path)
        await self._store.initialize()

        self._provider = _OllamaProvider(
            base_url=self._ollama_url,
            default_model=self._ollama_model,
        )
        self._judge = JudgeEngine(
            provider=self._provider,
            model=self._judge_model,
        )

    async def _ensure_store(self) -> SqliteStore:
        """Return the initialized store (aliased for brevity)."""
        await self._ensure_initialized()
        assert self._store is not None
        return self._store

    # ------------------------------------------------------------------
    #  MCP tool handlers
    # ------------------------------------------------------------------

    async def handle_create_task(
        self,
        description: str,
        mode: str = "feature",
        priority: str = "normal",
    ) -> str:
        """Create a new SDLC task and return its JSON representation."""
        store = await self._ensure_store()
        task_id = f"task_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        data: dict[str, Any] = {
            "task_id": task_id,
            "description": description,
            "mode": mode,
            "priority": priority,
            "status": TaskStatus.QUEUED.value,
            "current_phase": Phase.CHATTING.value,
            "created_at": now,
            "updated_at": now,
        }
        await store.create_task(data)
        return json.dumps(data, indent=2)

    async def handle_get_next_action(self, task_id: str) -> str:
        """Determine the next phase for a task."""
        store = await self._ensure_store()
        raw = await store.get_task(task_id)
        if raw is None:
            return json.dumps({"error": f"Task not found: {task_id}"})

        current = normalize_phase(raw.get("current_phase", "Chatting")).value

        if self._fsm is None or self._fsm.is_terminal(current):
            return json.dumps({
                "task_id": task_id,
                "current_phase": current,
                "next_phase": None,
                "terminal": True,
            })

        possible = self._graph.possible_next(current)
        # Remove "Done" from suggested actions unless it's the only option
        suggestions = [p for p in possible if p != "Done"]
        if not suggestions:
            suggestions = possible

        next_phase = suggestions[0]
        return json.dumps({
            "task_id": task_id,
            "current_phase": current,
            "next_phase": next_phase,
            "terminal": False,
            "possible_transitions": possible,
        })

    async def handle_submit_output(
        self,
        task_id: str,
        phase: str,
        output: str,
    ) -> str:
        """Submit phase output for judge evaluation (and optionally debate)."""
        await self._ensure_initialized()
        store = self._store
        assert store is not None

        raw = await store.get_task(task_id)
        if raw is None:
            return json.dumps({"error": f"Task not found: {task_id}"})

        # Build a Task model for the shared APIs.
        task = Task(
            task_id=raw["task_id"],
            description=raw.get("description", raw.get("prompt", "")),
            mode=raw.get("mode", "feature"),
            status=TaskStatus(raw.get("status", TaskStatus.ACTIVE.value)),
            current_phase=raw.get("current_phase", "Chatting"),
        )

        # Normalize the phase to determine the transition.
        from_phase = normalize_phase(phase)
        if from_phase is None:
            return json.dumps({"error": f"Unknown phase: {phase}"})

        # Get the natural next phase from the FSM.
        try:
            to_phase = self._fsm.submit(from_phase.value) if self._fsm else ""
        except Exception as exc:
            to_phase = ""

        # Run judge evaluation.
        assert self._judge is not None
        verdict = await self._judge.evaluate(
            task=task,
            from_phase=from_phase.value,
            to_phase=to_phase,
            output=output,
        )

        # Persist the phase output.
        await store.save_phase_output(
            task_id=task_id,
            phase=from_phase.value,
            output={"output": output, "verdict": verdict.model_dump()},
        )

        result: dict[str, Any] = {
            "task_id": task_id,
            "phase": from_phase.value,
            "next_phase": to_phase,
            "judge_verdict": verdict.model_dump(),
        }

        # If judge passed, optionally run debate for deeper validation.
        if verdict.passed and to_phase:
            result["debate"] = await self._run_debate(task, from_phase.value, output)

        return json.dumps(result, indent=2, default=str)

    async def handle_list_tasks(self, status: str | None = None) -> str:
        """List tasks, optionally filtered by status."""
        store = await self._ensure_store()
        tasks = await store.list_tasks(status=status)
        return json.dumps(tasks, indent=2, default=str)

    # ------------------------------------------------------------------
    #  Debate
    # ------------------------------------------------------------------

    async def _run_debate(
        self,
        task: Task,
        phase: str,
        output: str,
    ) -> dict[str, Any]:
        """Run the multi-agent debate protocol on phase output.

        Uses a lightweight runtime with consensus evaluation.
        Returns a summary dict (not the full transcript) to keep
        responses manageable over MCP.
        """
        try:
            from sdlc_debate.runtime import DebateRuntime

            assert self._provider is not None
            runtime = DebateRuntime(
                provider=self._provider,
                model=self._ollama_model,
                max_tokens=1024,
            )

            transcript = await runtime.run_debate(
                task=task,
                phase=phase,
                output=output,
                budget=BudgetPolicy(max_debate_rounds=3),
            )

            consensus = transcript.consensus
            return {
                "debate_used": True,
                "consensus_reached": consensus.reached if consensus else False,
                "consensus_passed": consensus.passed if consensus else False,
                "reason": consensus.reason if consensus else "No consensus",
                "rounds": len(transcript.rounds),
                "collapse_detected": consensus.collapse_signal.detected
                if consensus and consensus.collapse_signal
                else False,
                "minority_reports": [
                    {"agent": mr.agent_role, "severity": mr.severity}
                    for mr in (consensus.minority_reports if consensus else [])
                ],
            }
        except ImportError:
            return {"debate_used": False, "reason": "Debate module not available"}
        except Exception as exc:
            return {"debate_used": False, "reason": f"Debate failed: {exc}"}

    # ------------------------------------------------------------------
    #  Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the MCP server over stdio transport.

        This method is synchronous and blocks until the server exits.
        """
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async body of :meth:`run`."""
        from mcp.server.fastmcp import FastMCP

        await self._ensure_initialized()

        mcp = FastMCP(
            "sdlc-mcp",
            instructions="SDLC task orchestration server — manage tasks, evaluate outputs via judge and debate.",
            dependencies=[],
        )

        # ------------------------------------------------------------------
        #  Tool: sdlc_create_task
        # ------------------------------------------------------------------

        @mcp.tool(
            name="sdlc_create_task",
            description="Create a new SDLC task",
        )
        async def sdlc_create_task(
            description: str,
            mode: str = "feature",
            priority: str = "normal",
        ) -> str:
            """Create a new SDLC task and return its details as JSON.

            Args:
                description: Human-readable task description / prompt.
                mode: Task mode (feature, bugfix, refactor, etc.).
                priority: Task priority (normal, high, low).

            Returns:
                JSON string with the created task fields.
            """
            return await self.handle_create_task(
                description=description,
                mode=mode,
                priority=priority,
            )

        # ------------------------------------------------------------------
        #  Tool: sdlc_get_next_action
        # ------------------------------------------------------------------

        @mcp.tool(
            name="sdlc_get_next_action",
            description="Get the next recommended phase action for a task",
        )
        async def sdlc_get_next_action(task_id: str) -> str:
            """Determine the next SDLC phase a task should transition to.

            Args:
                task_id: The ID of the task.

            Returns:
                JSON string with current phase, next suggested phase, and
                possible transitions.
            """
            return await self.handle_get_next_action(task_id=task_id)

        # ------------------------------------------------------------------
        #  Tool: sdlc_submit_output
        # ------------------------------------------------------------------

        @mcp.tool(
            name="sdlc_submit_output",
            description="Submit phase output for judge evaluation and optional debate",
        )
        async def sdlc_submit_output(task_id: str, phase: str, output: str) -> str:
            """Submit the output of a completed SDLC phase for evaluation.

            The output is run through the JudgeEngine for deterministic
            and LLM-based quality checks, then optionally through a
            multi-agent debate protocol for deeper validation.

            Args:
                task_id: The ID of the task this output belongs to.
                phase: The phase name (Chatting, Specs, Planning, Coding, Review, Testing).
                output: The raw text output produced during this phase.

            Returns:
                JSON string with the judge verdict and optional debate result.
            """
            return await self.handle_submit_output(
                task_id=task_id,
                phase=phase,
                output=output,
            )

        # ------------------------------------------------------------------
        #  Tool: sdlc_list_tasks
        # ------------------------------------------------------------------

        @mcp.tool(
            name="sdlc_list_tasks",
            description="List SDLC tasks, optionally filtered by status",
        )
        async def sdlc_list_tasks(status: str | None = None) -> str:
            """List all SDLC tasks, optionally filtered by status value.

            Args:
                status: Optional status filter (e.g. "queued", "running", "done").

            Returns:
                JSON string containing the list of task objects.
            """
            return await self.handle_list_tasks(status=status)

        # Run the server over stdio.
        mcp.run(transport="stdio")
