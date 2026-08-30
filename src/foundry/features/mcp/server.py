"""FastMCP server — LLM-free SDLC orchestration, debate, agent-loop, memory, and indexing.

This module MUST NOT import any LLM provider or model gateway:

    NOT allowed:  OllamaProvider, OpenAIProvider, LLMProvider, ModelGateway,
                  generate(), openai, ollama, JudgeEngine, DebateRuntime

Only ``foundry.core`` modules are imported — all LLM-dependent functionality
(judge, debate runtime, tool execution via model) is configured at the
application layer through optional dependencies that the lifespan context
may (or may not) wire up via plugin loading.

Tools
-----
Phase orchestration:
    sdlc_create_task, sdlc_get_next_action, sdlc_submit_output,
    sdlc_request_approval

Task management:
    sdlc_get_status, sdlc_list_tasks, sdlc_cancel_task, sdlc_resume_task

Observability / debug:
    sdlc_get_trace, sdlc_list_traces, sdlc_get_summaries,
    sdlc_enforce_retention

Indexing:
    sdlc_index_repository, sdlc_index_files, sdlc_get_dependency_context,
    sdlc_get_index_stats

Debate (turn-engine based):
    sdlc_debate_get_turn, sdlc_debate_submit_turn

Agent-loop (turn-engine based):
    sdlc_agent_get_turn, sdlc_agent_submit_turn

Memory:
    sdlc_memory_store, sdlc_memory_query, sdlc_memory_stats

Context / spec drift:
    sdlc_harvest_context, sdlc_check_spec_drift

Deterministic checks:
    sdlc_schema_check

Resources
---------
    sdlc://phase-graph
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, cast

from mcp.server.fastmcp import Context, FastMCP

# ── Core imports ONLY — no LLM providers, no model gateways ──────────────
from foundry.core.checkpoint.manager import CheckpointManager
from foundry.core.config import Settings
from foundry.core.index.pipeline import IndexConfig, IndexPipeline
from foundry.core.logging import bootstrap_logging, get_logger
from foundry.core.memory.acervo import Acervo
from foundry.core.models import Checkpoint, Engram, Task, WriteOp
from foundry.core.orchestrator.fsm import OrchestratorFSM
from foundry.core.orchestrator.phase_graph import PhaseGraph
from foundry.core.orchestrator.policy import ExecutionPolicy
from foundry.core.permission_governor import FilePermissionGovernor
from foundry.core.store import SqliteStore
from foundry.core.tool_executor import ToolExecutor
from foundry.core.tool_gate import ToolGate
from foundry.core.tools import debug as debug_tools
from foundry.core.tools import phase as phase_tools
from foundry.core.tools import task as task_tools
from foundry.core.tracing import Tracer
from foundry.core.turn_engine import TurnEngine, TurnPrompt, TurnResult
from foundry.core.turn_engine.agent_loop_graph import AgentLoopGraph
from foundry.core.turn_engine.debate_graph import DebateGraph
from foundry.core.turn_engine.phase_graph import PhaseRoleGraph
from foundry.core.write_queue import WriteHandler, WriteQueue

# ── Deterministic schema checks (no LLM) ────────────────────────────────
from foundry.core.judge.schema_checks import validate_phase_output

if TYPE_CHECKING:
    from foundry.core.store import StoreBackend


# ═══════════════════════════════════════════════════════════════════════════
#  Context
# ═══════════════════════════════════════════════════════════════════════════


class MCPContext:
    """Shared server state accessible through the MCP request context.

    All fields are optional — the server is designed to degrade gracefully
    when optional subsystems (indexing, memory, tracing) are not configured.
    """

    def __init__(  # noqa: PLR0913
        self,
        store: StoreBackend,
        checkpoint_mgr: CheckpointManager,
        orchestrator: OrchestratorFSM,
        policy: ExecutionPolicy,
        write_queue: WriteQueue,
        graph: PhaseGraph,
        config: dict[str, Any],
        tracer: Tracer | None = None,
        index_pipeline: IndexPipeline | None = None,
        acervo: Acervo | None = None,
        tool_executor: ToolExecutor | None = None,
        tool_gate: ToolGate | None = None,
        context_graph: Any | None = None,
        judge_engine: Any | None = None,
        debate_runtime: Any | None = None,
    ) -> None:
        self.store = store
        self.checkpoint_mgr = checkpoint_mgr
        self.orchestrator = orchestrator
        self.policy = policy
        self.write_queue = write_queue
        self.graph = graph
        self.config = config
        self.tracer = tracer
        self.index_pipeline = index_pipeline
        self.acervo = acervo
        self.tool_executor = tool_executor
        self.tool_gate = tool_gate
        self.context_graph = context_graph
        self.judge_engine = judge_engine
        self.debate_runtime = debate_runtime


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _require_context(ctx: Context | None) -> MCPContext:
    """Unwrap the lifespan context or raise ``RuntimeError``."""
    if ctx is None:
        msg = "MCP context is required"
        raise RuntimeError(msg)
    return cast("MCPContext", ctx.request_context.lifespan_context)


def _make_write_handler(
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    acervo: Acervo | None = None,
) -> WriteHandler:
    """Build a ``WriteHandler`` that dispatches ``WriteOp`` to the right backend."""

    async def handler(op: WriteOp) -> None:
        if op.target == "task":
            if op.action == "create":
                await store.create_task(op.payload)
            elif op.action == "update":
                await store.update_task(str(op.payload["task_id"]), op.payload)
        elif op.target == "checkpoint":
            checkpoint = Checkpoint(**op.payload)
            checkpoint_mgr.save(checkpoint)
            await store.save_checkpoint(str(op.payload["task_id"]), op.payload)
        elif op.target == "phase_output":
            await store.save_phase_output(
                str(op.payload["task_id"]),
                str(op.payload["phase"]),
                op.payload,
            )
        elif op.target == "memory" and acervo is not None:
            await acervo.store(
                content=str(op.payload.get("content", "")),
                task_id=str(op.payload.get("task_id", "")),
                phase=str(op.payload.get("phase", "")),
                tags=op.payload.get("tags", []),
                source=str(op.payload.get("source", "unknown")),
                importance=float(op.payload.get("importance", 0.5)),
            )

    return handler


def _load_graphs(settings: Settings) -> dict[str, PhaseGraph]:
    """Load phase graphs for all supported modes."""
    return {
        "feature": PhaseGraph(settings.load_phase_graph("feature")),
        "bugfix": PhaseGraph(settings.load_phase_graph("bugfix")),
        "refactor": PhaseGraph(settings.load_phase_graph("refactor")),
        "research": PhaseGraph(settings.load_phase_graph("research")),
        "docs": PhaseGraph(settings.load_phase_graph("docs")),
    }


def _build_orchestrators(
    graphs: dict[str, PhaseGraph],
    policy: ExecutionPolicy,
) -> dict[str, OrchestratorFSM]:
    """Build one ``OrchestratorFSM`` per phase-graph mode."""
    return {
        mode: OrchestratorFSM(graph, policy)
        for mode, graph in graphs.items()
    }


# ── TurnEngine namespace keys ───────────────────────────────────────────
# To allow multiple independent TurnEngine instances to operate on the same
# task, each protocol (phase, debate, agent-loop) stores its state under a
# different key inside the task's JSON blob.  The TurnEngine class uses a
# hard-coded ``turn_engine`` key, so we wrap it with a thin adapter.


class _NamespacedTurnEngine(TurnEngine):
    """TurnEngine that stores state under *namespace* instead of ``turn_engine``.

    This allows independent protocols (phase execution, multi-agent debate,
    agent-loop) to co-exist on the same task without conflicting state keys.
    """

    _TE_KEY: str = "turn_engine"

    def __init__(  # noqa: PLR0913
        self,
        graph: Any,
        store: StoreBackend,
        task_id: str,
        namespace: str = "turn_engine",
    ) -> None:
        super().__init__(graph, store, task_id)
        self._namespace = namespace

    async def get_turn(self) -> TurnPrompt:
        task = await self._require_task()
        te_state = task.get(self._namespace, {})
        context = task.get("context", {})

        self._inject_graph_state(te_state, context)

        if te_state.get("complete"):
            return TurnPrompt(
                role="",
                prompt="",
                done=True,
                result=te_state.get("result"),
            )

        current_role: str
        stored_role = te_state.get("current_role")
        if stored_role is not None:
            current_role = stored_role
        else:
            current_role = self.graph.initial_role(context)

        prompt_text = self.graph.prompt_for(current_role, context)

        return TurnPrompt(
            role=current_role,
            prompt=prompt_text,
            context=context,
            done=False,
        )

    async def submit_turn(self, role: str, output: str) -> TurnResult:
        task = await self._require_task()
        te_state = task.get(self._namespace, {})
        context = task.get("context", {})

        self._inject_graph_state(te_state, context)

        expected_role: str
        stored_role = te_state.get("current_role")
        if stored_role is not None:
            expected_role = stored_role
        else:
            expected_role = self.graph.initial_role(context)

        if role != expected_role:
            return TurnResult(
                accepted=False,
                error=(
                    f"Role mismatch: submitted '{role}' but the engine "
                    f"expects '{expected_role}' for task {self.task_id}"
                ),
            )

        await self.store.save_phase_output(
            self.task_id,
            f"turn_engine/{role}",
            {
                "role": role,
                "output": output,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        next_val = self.graph.next_role(expected_role, output, context)

        from foundry.core.turn_engine.graph import Terminal

        graph_state = context.pop("_te_graph_state", None)

        if next_val is None or next_val is Terminal:
            new_te: dict[str, Any] = {
                "complete": True,
                "result": output,
                "current_role": None,
            }
            if graph_state is not None:
                new_te["_graph_state"] = graph_state
            await self.store.update_task(self.task_id, {self._namespace: new_te})
            return TurnResult(
                accepted=True,
                next_turn=TurnPrompt(
                    role="",
                    prompt="",
                    done=True,
                    result=output,
                ),
            )

        next_role_val: str = next_val

        new_te = {
            "complete": False,
            "current_role": next_role_val,
        }
        if graph_state is not None:
            new_te["_graph_state"] = graph_state
        await self.store.update_task(self.task_id, {self._namespace: new_te})

        prompt_text = self.graph.prompt_for(next_role_val, context)
        next_turn = TurnPrompt(
            role=next_role_val,
            prompt=prompt_text,
            context=context,
            done=False,
        )

        return TurnResult(accepted=True, next_turn=next_turn)

    @staticmethod
    def _inject_graph_state(
        te_state: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        gs = te_state.get("_graph_state")
        if gs is not None:
            context["_te_graph_state"] = gs


# ═══════════════════════════════════════════════════════════════════════════
#  Lifespan
# ═══════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[MCPContext]:  # noqa: ARG001
    """Initialize all non-LLM services and yield the shared context.

    No provider, no judge, no debate runtime — those are wired at the
    application layer through optional plugins.
    """
    settings = Settings.from_yaml_first()
    settings.ensure_dirs()
    bootstrap_logging(
        level=settings.logging_cfg.level,
        json_format=settings.logging_cfg.use_json,
        path=str(settings.resolve_runtime_path(settings.logging_cfg.path)),
    )
    logger = get_logger("mcp")

    # ── Phase graphs and orchestrators ────────────────────────────────
    graphs = _load_graphs(settings)
    graph = graphs["feature"]
    policy = ExecutionPolicy()
    orchestrator = OrchestratorFSM(graph, policy)
    orchestrators = _build_orchestrators(graphs, policy)

    # ── Store ─────────────────────────────────────────────────────────
    store = SqliteStore(settings.resolve_runtime_path(settings.db_path))
    await store.initialize()

    checkpoint_mgr = CheckpointManager(
        settings.resolve_runtime_path(settings.checkpoint_dir),
    )

    # ── Memory (Acervo) ───────────────────────────────────────────────
    acervo: Acervo | None = None
    if settings.memory_enabled:
        acervo = Acervo(store_dir=settings.resolve_runtime_path(settings.memory_dir))
        await acervo.initialize()
        logger.info("Cross-task memory (Acervo) enabled")

    # ── Optional LLM stack (judge + debate) ───────────────────────────
    from foundry.features.mcp.plugins import build_llm_stack

    llm_stack = await build_llm_stack(settings)

    # ── Write queue ───────────────────────────────────────────────────
    write_queue = WriteQueue(_make_write_handler(store, checkpoint_mgr, acervo))
    await write_queue.start()

    # ── Tracing ───────────────────────────────────────────────────────
    tracer = Tracer(trace_dir=str(settings.resolve_runtime_path(settings.trace_dir)))
    tracer.enforce_retention()

    # ── Tool executor (no adapters registered by default) ─────────────
    tool_executor = ToolExecutor(
        default_timeout_s=30.0,
        max_retries=1,
    )
    tool_executor.configure_sandbox(
        enabled=settings.sandbox.enabled,
        denied_paths=list(settings.sandbox.denied_paths),
        readonly_paths=list(settings.sandbox.readonly_paths),
        writable_paths=list(settings.sandbox.writable_paths),
    )
    sandbox_config_path = settings.resolve_config_path("sandbox.yaml")
    if sandbox_config_path.exists():
        tool_executor.load_sandbox_config(str(sandbox_config_path))

    permission_governor = FilePermissionGovernor(default_deny=False)
    tool_executor.set_permission_governor(permission_governor)

    health = await tool_executor.healthcheck_all()
    for name, ok in health.items():
        if not ok:
            logger.warning(
                "Tool adapter health check failed",
                extra={"tool": name, "healthy": ok},
            )

    tool_gate = ToolGate()
    logger.info(
        "ToolExecutor and ToolGate initialized",
        extra={
            "registered_tools": list(tool_executor._adapters.keys()),
            "healthy_tools": [n for n, h in health.items() if h],
        },
    )

    # ── Index pipeline ────────────────────────────────────────────────
    index_config = IndexConfig(
        enabled=settings.index.enabled,
        max_files=settings.index.max_files,
        max_file_size_kb=settings.index.max_file_size_kb,
        include_patterns=list(settings.index.include_patterns),
        exclude_patterns=list(settings.index.exclude_patterns),
        incremental=settings.index.incremental,
        chunk_size_lines=settings.index.chunk_size_lines,
        context_file_count=settings.index.context_file_count,
        context_chunk_count=settings.index.context_chunk_count,
    )

    workspace = settings.resolve_workspace_path()
    if not workspace.is_dir():
        logger.warning(
            "Workspace path does not exist — indexing disabled",
            extra={"workspace": str(workspace)},
        )
        workspace = None

    index_pipeline = None
    if workspace is not None:
        index_pipeline = IndexPipeline(
            workspace=workspace,
            store_dir=settings.resolve_runtime_path(settings.index_dir),
            config=index_config,
        )
        await index_pipeline.initialize()
        if index_config.enabled and index_config.incremental:
            index_result = await index_pipeline.run_incremental_index()
            logger.info("Initial index complete", extra=index_result)

    # ── ContextGraph (symbol-level repo understanding) ────────────────
    from foundry.core.context_graph import ContextGraph

    context_graph: ContextGraph | None = None
    if workspace is not None:
        try:
            context_graph = ContextGraph()
            indexed = 0
            max_bytes = settings.index.max_file_size_kb * 1024
            for path in sorted(workspace.rglob("*")):
                if indexed >= settings.index.max_files:
                    break
                if not path.is_file() or any(
                    part.startswith(".") for part in path.relative_to(workspace).parts
                ):
                    continue
                if path.stat().st_size > max_bytes:
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                context_graph.add_file(str(path.relative_to(workspace)), content)
                indexed += 1
            logger.info(
                "ContextGraph built",
                extra={"files": indexed, **context_graph.stats},
            )
        except Exception as exc:  # noqa: BLE001 — degrade, never crash lifespan
            context_graph = None
            logger.warning("ContextGraph build failed: %s", exc)

    logger.info("MCP server initialized", extra={
        "graph_mode": "feature",
        "trace_dir": str(settings.trace_dir),
        "workspace": str(workspace) if workspace else None,
        "judge_wired": llm_stack["judge_engine"] is not None,
        "debate_wired": llm_stack["debate_runtime"] is not None,
    })

    ctx = MCPContext(
        store=store,
        checkpoint_mgr=checkpoint_mgr,
        orchestrator=orchestrator,
        policy=policy,
        write_queue=write_queue,
        graph=graph,
        config={
            "max_iterations": settings.max_iterations,
            "mode": "feature",
            "workspace_path": str(workspace) if workspace else str(Path.cwd()),
            "graphs": graphs,
            "orchestrators": orchestrators,
        },
        tracer=tracer,
        index_pipeline=index_pipeline,
        acervo=acervo,
        tool_executor=tool_executor,
        tool_gate=tool_gate,
        context_graph=context_graph,
        judge_engine=llm_stack["judge_engine"],
        debate_runtime=llm_stack["debate_runtime"],
    )

    try:
        yield ctx
    finally:
        await write_queue.stop()
        await store.checkpoint()
        await store.close()
        logger.info("MCP server shut down")


# ═══════════════════════════════════════════════════════════════════════════
#  App
# ═══════════════════════════════════════════════════════════════════════════

app = FastMCP("foundry-mcp", lifespan=lifespan)


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_create_task
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_create_task(
    description: str,
    mode: str = "feature",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a new SDLC task and enqueue its creation.

    Parameters
    ----------
    description:
        Free-text description of the task.
    mode:
        Workflow mode — ``"feature"``, ``"bugfix"``, ``"refactor"``,
        ``"research"``, or ``"docs"``.
    """
    if mode not in ("feature", "bugfix", "refactor", "research", "docs"):
        msg = (
            f"Unsupported mode: '{mode}'. Only 'feature', 'bugfix', "
            "'refactor', 'research', and 'docs' are supported."
        )
        raise ValueError(msg)
    sdlc_ctx = _require_context(ctx)
    tracer = sdlc_ctx.tracer
    trace_id = tracer.create_trace_id() if tracer else None
    return await task_tools.create_task(
        sdlc_ctx.write_queue,
        description,
        mode,
        trace_id=trace_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_get_next_action
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_get_next_action(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return the next recommended phase action for a task.

    Uses the ``TurnEngine`` (backed by ``PhaseRoleGraph``) to determine the
    current role and prompt.  Idempotent — safe to call repeatedly.

    Parameters
    ----------
    task_id:
        The ID of the task to advance.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    orchestrators: dict = sdlc_ctx.config.get("orchestrators", {})
    orchestrator = orchestrators.get(task.mode, sdlc_ctx.orchestrator)

    return await phase_tools.get_next_action(
        sdlc_ctx.store,
        sdlc_ctx.checkpoint_mgr,
        orchestrator,
        task_id,
        {},
        tracer=sdlc_ctx.tracer,
        index_pipeline=sdlc_ctx.index_pipeline,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_submit_output
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_submit_output(
    task_id: str,
    phase: str,
    output: str,
    next_phase: str | None = None,
    all_files: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Submit phase output for evaluation and advance the task state.

    When an LLM provider is reachable, the output is evaluated by the
    judge engine (and debated on Review transitions).  Otherwise the
    output is persisted and the task advances via the orchestrator FSM.

    Parameters
    ----------
    task_id:
        The task whose phase output is being submitted.
    phase:
        The phase name (e.g. ``"Chatting"``, ``"Specs"``, ``"Coding"``).
    output:
        The raw text output produced during this phase.
    next_phase:
        Optional explicit next phase (bypasses FSM transition logic).
    all_files:
        If True, include all workspace files in context (requires index).
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"accepted": False, "error": f"Task not found: {task_id}"}
    task = Task(**raw)
    orchestrators: dict = sdlc_ctx.config.get("orchestrators", {})
    orchestrator = orchestrators.get(task.mode, sdlc_ctx.orchestrator)

    return await phase_tools.submit_output(
        sdlc_ctx.store,
        sdlc_ctx.checkpoint_mgr,
        orchestrator,
        sdlc_ctx.policy,
        sdlc_ctx.write_queue,
        task_id,
        phase,
        output,
        max_iterations=int(sdlc_ctx.config.get("max_iterations", 8)),
        next_phase=next_phase,
        judge_engine=sdlc_ctx.judge_engine,
        tracer=sdlc_ctx.tracer,
        debate_runtime=sdlc_ctx.debate_runtime,
        tool_executor=sdlc_ctx.tool_executor,
        tool_gate=sdlc_ctx.tool_gate,
        workspace_path=str(sdlc_ctx.config.get("workspace_path", ".")),
        all_files=all_files,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_request_approval
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_request_approval(
    task_id: str,
    phase: str,
    summary: str,
    *,
    approved: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Request or record human approval for a phase transition.

    Parameters
    ----------
    task_id:
        The task requiring approval.
    phase:
        The phase requesting approval.
    summary:
        Human-readable summary of what needs approval.
    approved:
        Pre-approved flag — if True the approval is recorded immediately.
    """
    sdlc_ctx = _require_context(ctx)
    return await phase_tools.request_approval(
        sdlc_ctx.store,
        sdlc_ctx.write_queue,
        task_id,
        phase,
        summary,
        approved=approved,
        tracer=sdlc_ctx.tracer,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_get_status
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_get_status(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return the current status and progress of a task.

    Parameters
    ----------
    task_id:
        The task to query.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    graphs: dict = sdlc_ctx.config.get("graphs", {})
    graph = graphs.get(task.mode, sdlc_ctx.graph)
    return await task_tools.get_status(sdlc_ctx.store, graph, task_id)


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_list_tasks
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_list_tasks(
    status: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """List SDLC tasks, optionally filtered by status.

    Parameters
    ----------
    status:
        Optional status filter (e.g. ``"queued"``, ``"running"``, ``"done"``).
    """
    sdlc_ctx = _require_context(ctx)
    return await task_tools.list_tasks(sdlc_ctx.store, status)


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_cancel_task
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_cancel_task(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Cancel a task — marks it as cancelled and persists.

    Parameters
    ----------
    task_id:
        The task to cancel.
    """
    sdlc_ctx = _require_context(ctx)
    return await task_tools.cancel_task(
        sdlc_ctx.store,
        sdlc_ctx.write_queue,
        task_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_resume_task
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_resume_task(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Resume a task from its latest checkpoint.

    Parameters
    ----------
    task_id:
        The task to resume.
    """
    sdlc_ctx = _require_context(ctx)
    return await task_tools.resume_task(
        sdlc_ctx.store,
        sdlc_ctx.checkpoint_mgr,
        task_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Debug / tracing tools
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_get_trace(
    trace_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve a single trace by ID.

    Parameters
    ----------
    trace_id:
        The unique trace identifier to look up.
    """
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.get_trace(sdlc_ctx.tracer, trace_id)


@app.tool()
async def sdlc_list_traces(
    task_id: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """List available traces, optionally filtered by task ID.

    Parameters
    ----------
    task_id:
        Optional task ID to filter on.
    """
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.list_traces(sdlc_ctx.tracer, task_id=task_id)


@app.tool()
async def sdlc_get_summaries(
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve trace summary statistics from the summaries JSONL file."""
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.get_summaries(sdlc_ctx.tracer)


@app.tool()
async def sdlc_enforce_retention(
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Enforce retention policy — purge expired traces."""
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.enforce_retention(sdlc_ctx.tracer)


# ═══════════════════════════════════════════════════════════════════════════
#  Indexing tools
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_index_repository(
    mode: str = "incremental",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Index the repository files.

    Parameters
    ----------
    mode:
        Indexing mode — ``"incremental"`` (default) or ``"full"``.
    """
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    if mode not in ("incremental", "full"):
        return {"error": f"Unsupported mode: '{mode}'. Use 'incremental' or 'full'."}
    if mode == "full":
        return await pipeline.run_full_index()
    return await pipeline.run_incremental_index()


@app.tool()
async def sdlc_index_files(
    file_paths: list[str],
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Index specific files by path.

    Parameters
    ----------
    file_paths:
        List of file paths (relative to workspace root) to index.
    """
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return await pipeline.index_files(file_paths)


@app.tool()
async def sdlc_get_dependency_context(
    file_path: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve dependency context for a file.

    Parameters
    ----------
    file_path:
        Path to the file (relative to workspace root).
    """
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return await pipeline.get_dependency_context(file_path)


@app.tool()
async def sdlc_get_index_stats(
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return index pipeline statistics."""
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return pipeline.stats


# ═══════════════════════════════════════════════════════════════════════════
#  ContextGraph tools (symbol-level repository understanding)
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_query_symbols(
    query: str,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Query symbols by text (name, docstring matching).

    Parameters
    ----------
    query:
        Text to search for (e.g. "authentication login").
    limit:
        Maximum number of results.
    """
    sdlc_ctx = _require_context(ctx)
    graph = sdlc_ctx.context_graph
    if graph is None:
        return {"error": "Context graph not initialized"}
    symbols = graph.query(query, limit=limit)
    return {
        "symbols": [s.to_dict() for s in symbols],
        "count": len(symbols),
        "stats": graph.stats,
    }


@app.tool()
async def sdlc_get_callers(
    qualified_name: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get all symbols that call the given symbol.

    Parameters
    ----------
    qualified_name:
        Fully qualified name (e.g. "auth.authenticate_user").
    """
    sdlc_ctx = _require_context(ctx)
    graph = sdlc_ctx.context_graph
    if graph is None:
        return {"error": "Context graph not initialized"}
    callers = graph.get_callers(qualified_name)
    return {
        "callers": [s.to_dict() for s in callers],
        "count": len(callers),
    }


@app.tool()
async def sdlc_get_symbol_context(
    qualified_name: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Get full context for a symbol: definition, callers, callees, imports.

    Parameters
    ----------
    qualified_name:
        Fully qualified name (e.g. "auth.authenticate_user").
    """
    sdlc_ctx = _require_context(ctx)
    graph = sdlc_ctx.context_graph
    if graph is None:
        return {"error": "Context graph not initialized"}

    symbol = graph.get_symbol(qualified_name)
    if symbol is None:
        return {"error": f"Symbol not found: {qualified_name}"}

    return {
        "symbol": symbol.to_dict(),
        "callers": [s.to_dict() for s in graph.get_callers(qualified_name)],
        "callees": [s.to_dict() for s in graph.get_callees(qualified_name)],
        "imports": [s.to_dict() for s in graph.get_imports(qualified_name)],
        "inherits": [s.to_dict() for s in graph.get_inherits(qualified_name)],
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Debate tools (TurnEngine + DebateGraph)
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_debate_get_turn(
    task_id: str,
    phase: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return the current debate turn for a task's phase output.

    Creates or resumes a ``DebateGraph``-backed ``TurnEngine`` that drives
    multi-agent debate (debater_a, debater_b, debater_c, consensus).

    Parameters
    ----------
    task_id:
        The task being debated.
    phase:
        The phase whose output is under debate.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    # Retrieve the artefact (phase output) from task history
    task = Task(**raw)
    artefact = ""
    for record in task.history:
        if record.phase == phase and record.output:
            artefact = record.output
            break

    debate_graph = DebateGraph(
        store=sdlc_ctx.store,
        task_id=task_id,
        artefact=artefact,
    )
    engine = _NamespacedTurnEngine(
        graph=debate_graph,
        store=sdlc_ctx.store,
        task_id=task_id,
        namespace=f"debate_{phase}",
    )
    turn = await engine.get_turn()

    return {
        "task_id": task_id,
        "phase": phase,
        "role": turn.role,
        "prompt": turn.prompt,
        "done": turn.done,
        "result": turn.result,
    }


@app.tool()
async def sdlc_debate_submit_turn(
    task_id: str,
    phase: str,
    persona: str,
    output: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Submit a debate turn for a given persona and advance the debate.

    Parameters
    ----------
    task_id:
        The task being debated.
    phase:
        The phase whose output is under debate.
    persona:
        The debating persona role (``"debater_a"``, ``"debater_b"``,
        ``"debater_c"``, or ``"consensus"``).
    output:
        The persona's evaluation text.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    task = Task(**raw)
    artefact = ""
    for record in task.history:
        if record.phase == phase and record.output:
            artefact = record.output
            break

    debate_graph = DebateGraph(
        store=sdlc_ctx.store,
        task_id=task_id,
        artefact=artefact,
    )
    engine = _NamespacedTurnEngine(
        graph=debate_graph,
        store=sdlc_ctx.store,
        task_id=task_id,
        namespace=f"debate_{phase}",
    )
    result = await engine.submit_turn(persona, output)

    if not result.accepted:
        return {
            "accepted": False,
            "error": result.error,
        }

    next_turn = result.next_turn
    return {
        "accepted": True,
        "task_id": task_id,
        "phase": phase,
        "next_role": next_turn.role if next_turn else None,
        "next_prompt": next_turn.prompt if next_turn else None,
        "done": next_turn.done if next_turn else True,
        "result": next_turn.result if next_turn else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Agent-loop tools (TurnEngine + AgentLoopGraph)
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_agent_get_turn(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return the current agent-loop turn for a task.

    Creates or resumes an ``AgentLoopGraph``-backed ``TurnEngine`` that
    drives the planner/executor/verifier/repairer loop.

    Parameters
    ----------
    task_id:
        The task to retrieve a turn for.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    task = Task(**raw)
    agent_graph = AgentLoopGraph()
    engine = _NamespacedTurnEngine(
        graph=agent_graph,
        store=sdlc_ctx.store,
        task_id=task_id,
        namespace="agent_loop",
    )
    turn = await engine.get_turn()

    return {
        "task_id": task_id,
        "role": turn.role,
        "prompt": turn.prompt,
        "done": turn.done,
        "result": turn.result,
    }


@app.tool()
async def sdlc_agent_submit_turn(
    task_id: str,
    role: str,
    output: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Submit an agent-loop turn for a given role and advance the loop.

    Parameters
    ----------
    task_id:
        The task the agent is working on.
    role:
        The agent role (``"planner"``, ``"executor"``, ``"verifier"``,
        or ``"repairer"``).
    output:
        The agent's output text.
    """
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}

    task = Task(**raw)
    agent_graph = AgentLoopGraph()
    engine = _NamespacedTurnEngine(
        graph=agent_graph,
        store=sdlc_ctx.store,
        task_id=task_id,
        namespace="agent_loop",
    )
    result = await engine.submit_turn(role, output)

    if not result.accepted:
        return {
            "accepted": False,
            "error": result.error,
        }

    next_turn = result.next_turn
    return {
        "accepted": True,
        "task_id": task_id,
        "next_role": next_turn.role if next_turn else None,
        "next_prompt": next_turn.prompt if next_turn else None,
        "done": next_turn.done if next_turn else True,
        "result": next_turn.result if next_turn else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Memory tools (Acervo)
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_memory_store(
    content: str,
    task_id: str = "",
    phase: str = "",
    tags: list[str] | None = None,
    source: str = "unknown",
    importance: float = 0.5,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Store a memory engram in cross-task memory (Acervo).

    Parameters
    ----------
    content:
        The memory content to store.
    task_id:
        Optional task ID to associate.
    phase:
        Optional phase name to associate.
    tags:
        Optional list of tags for retrieval.
    source:
        Source identifier.
    importance:
        Importance score (0.0 – 1.0).
    """
    sdlc_ctx = _require_context(ctx)
    if sdlc_ctx.acervo is None:
        return {"error": "Cross-task memory not enabled"}
    engram = await sdlc_ctx.acervo.store(
        content=content,
        task_id=task_id,
        phase=phase,
        tags=tags or [],
        source=source,
        importance=importance,
    )
    return {"status": "ok", "engram_id": engram.engram_id}


@app.tool()
async def sdlc_memory_query(
    phase: str | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    source: str | None = None,
    min_importance: float = 0.3,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Query cross-task memory for relevant engrams.

    Parameters
    ----------
    phase:
        Filter by phase name.
    tags:
        Filter by tags (any match).
    keywords:
        Filter by keyword(s) in content.
    source:
        Filter by source identifier.
    min_importance:
        Minimum importance threshold (0.0 – 1.0).
    limit:
        Maximum number of results.
    """
    sdlc_ctx = _require_context(ctx)
    if sdlc_ctx.acervo is None:
        return {"error": "Cross-task memory not enabled"}
    results = await sdlc_ctx.acervo.query(
        phase=phase,
        tags=tags,
        keywords=keywords,
        source=source,
        min_importance=min_importance,
        limit=limit,
    )
    return {
        "status": "ok",
        "count": len(results),
        "engrams": [e.model_dump(mode="json") for e in results],
    }


@app.tool()
async def sdlc_memory_stats(
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Return cross-task memory statistics."""
    sdlc_ctx = _require_context(ctx)
    if sdlc_ctx.acervo is None:
        return {"error": "Cross-task memory not enabled"}
    return {"status": "ok", **sdlc_ctx.acervo.stats}


# ═══════════════════════════════════════════════════════════════════════════
#  Context / spec drift tools
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_harvest_context(
    task_id: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Run pre-spec context harvesting -- generates questions across 10 categories.

    Uses the ``ContextHarvester`` from the index pipeline to analyse the
    task description and identify knowledge gaps.

    Parameters
    ----------
    task_id:
        The task to harvest context for.
    """
    from foundry.core.index.context_harvester import (
        ContextHarvester,
    )

    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    harvester = ContextHarvester(index_pipeline=sdlc_ctx.index_pipeline)
    bundle = await harvester.harvest(task.description)
    ready, blocking = harvester.is_ready_for_spec(bundle)
    return {
        "task_id": task_id,
        "total_questions": len(bundle.questions),
        "critical_unresolved": len(bundle.critical_unresolved),
        "ready_for_spec": ready,
        "blocking_reasons": blocking,
        "categories": list({q.category for q in bundle.questions}),
        "context_text": harvester.to_spec_context(bundle),
    }


@app.tool()
async def sdlc_check_spec_drift(
    task_id: str,
    output: str,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Check if a post-spec output drifts from the locked spec.

    Parameters
    ----------
    task_id:
        The task whose spec to check against.
    output:
        The output content to check for drift.
    """
    from foundry.core.index.context_harvester import (
        check_spec_drift,
    )

    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    spec_output = ""
    for record in task.history:
        if record.phase == "Specs" and record.output:
            spec_output = record.output
            break
    if not spec_output:
        return {"status": "no_spec", "message": "No approved spec found in task history"}
    violations = check_spec_drift(spec_output, output)
    return {
        "task_id": task_id,
        "violations": [v.model_dump() for v in violations],
        "drift_detected": len(violations) > 0,
        "violation_count": len(violations),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Tool: sdlc_schema_check (deterministic only — no LLM)
# ═══════════════════════════════════════════════════════════════════════════


@app.tool()
async def sdlc_schema_check(
    phase: str,
    output: str,
    ctx: Context | None = None,  # noqa: ARG001
) -> dict[str, Any]:
    """Run deterministic structural validation on a phase output.

    Checks that the output contains required sections (e.g. ``## Requirements``
    for Specs).  No LLM is called — purely regex-based section detection.

    Parameters
    ----------
    phase:
        The phase name to validate against (e.g. ``"Specs"``, ``"Coding"``).
    output:
        The raw phase output text to validate.
    """
    violations = validate_phase_output(phase, output)
    return {
        "phase": phase,
        "valid": len(violations) == 0,
        "violations": [
            {
                "section": v.section,
                "message": str(v),
                "details": v.details,
            }
            for v in violations
        ],
        "violation_count": len(violations),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Resource: sdlc://phase-graph
# ═══════════════════════════════════════════════════════════════════════════


@app.resource("sdlc://phase-graph")
async def phase_graph_resource() -> str:
    """Render the default (feature) phase graph as human-readable text."""
    settings = Settings.from_yaml_first()
    graph = PhaseGraph(settings.load_phase_graph("feature"))
    phases = "\n".join(f"  - {phase}" for phase in graph.phases)
    transitions = "\n".join(
        f"  {transition['from']} -> {transition['to']}"
        for transition in graph.transitions
    )
    return f"Phase Graph (feature.yaml):\n{phases}\n\nTransitions:\n{transitions}"
