"""FastMCP application bootstrap — wires all tools, resources, and lifespan."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mcp.server.fastmcp import Context, FastMCP

from sdlc_mcp.adapters.llm import LLMProvider, ModelRouter, OllamaProvider, OpenAIProvider
from sdlc_mcp.adapters.memory import Acervo, MemoryAdapter
from sdlc_mcp.bootstrap.engine import BootstrapEngine
from sdlc_mcp.bootstrap.workspace import (
    WorkspaceResolution,
    WorkspaceState,
    detect_workspace,
    resolve_workspace,
)
from sdlc_mcp.config import settings
from sdlc_mcp.engine.checkpoint import CheckpointManager
from sdlc_mcp.engine.debate_runtime import DebateRuntime
from sdlc_mcp.engine.execution_policy import ExecutionPolicy
from sdlc_mcp.engine.judge import JudgeEngine
from sdlc_mcp.engine.orchestrator import OrchestratorFSM
from sdlc_mcp.engine.phase_graph import PhaseGraph
from sdlc_mcp.engine.schema_checks import validate_phase_output
from sdlc_mcp.exceptions import ConfigError
from sdlc_mcp.log import bootstrap_logging, get_logger
from sdlc_mcp.models import Checkpoint, IndexConfig, Task, WriteOp
from sdlc_mcp.runtime.pipelines.default import IndexPipeline
from sdlc_mcp.runtime.store_sqlite import SqliteStore
from sdlc_mcp.runtime.tools import debug as debug_tools
from sdlc_mcp.runtime.tools import phase as phase_tools
from sdlc_mcp.runtime.tools import task as task_tools
from sdlc_mcp.runtime.tracing import Tracer
from sdlc_mcp.runtime.write_queue import WriteHandler, WriteQueue

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sdlc_mcp.runtime.store_backend import StoreBackend


class SDLCAppContext:
    """Shared SDLC server state accessible through the MCP request context."""

    def __init__(  # noqa: PLR0913
        self,
        store: StoreBackend,
        checkpoint_mgr: CheckpointManager,
        orchestrator: OrchestratorFSM,
        policy: ExecutionPolicy,
        write_queue: WriteQueue,
        graph: PhaseGraph,
        model_routing: dict[str, Any],
        config: dict[str, Any],
        judge_engine: JudgeEngine | None = None,
        tracer: Tracer | None = None,
        index_pipeline: IndexPipeline | None = None,
        debate_runtime: DebateRuntime | None = None,
        acervo: Acervo | None = None,
        memory_adapter: MemoryAdapter | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self.store = store
        self.checkpoint_mgr = checkpoint_mgr
        self.orchestrator = orchestrator
        self.policy = policy
        self.write_queue = write_queue
        self.graph = graph
        self.model_routing = model_routing
        self.config = config
        self.judge_engine = judge_engine
        self.tracer = tracer
        self.index_pipeline = index_pipeline
        self.debate_runtime = debate_runtime
        self.acervo = acervo
        self.memory_adapter = memory_adapter
        self.workspace_root = workspace_root


def _make_write_handler(
    store: StoreBackend,
    checkpoint_mgr: CheckpointManager,
    acervo: Acervo | None = None,
) -> WriteHandler:
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


def _validate_model_routing(graph: PhaseGraph, model_routing: dict[str, Any]) -> None:
    phases = model_routing.get("phases")
    if not isinstance(phases, dict):
        msg = "model_routing.yaml must contain a 'phases' mapping"
        raise ConfigError(msg)
    missing = [phase for phase in graph.phases if phase not in phases]
    if missing:
        msg = f"model_routing.yaml missing routes for phases: {missing}"
        raise ConfigError(msg)


def _build_providers(llm_cfg: Any) -> dict[str, LLMProvider]:
    """Build provider instances from LLM config."""
    providers: dict[str, LLMProvider] = {}
    for name, pcfg in llm_cfg.providers.items():
        ptype = getattr(pcfg, "type", "ollama")
        if ptype == "openai":
            providers[name] = OpenAIProvider(
                api_key=getattr(pcfg, "api_key", ""),
                base_url=getattr(pcfg, "base_url", "https://api.openai.com/v1"),
                timeout_s=getattr(pcfg, "timeout_s", 120),
                default_model=getattr(pcfg, "default_model", "gpt-4o"),
            )
        else:
            providers[name] = OllamaProvider(
                base_url=getattr(pcfg, "base_url", "http://localhost:11434"),
                timeout_s=getattr(pcfg, "timeout_s", 120),
                default_model=getattr(pcfg, "default_model", "qwen3:8b"),
            )
    return providers


def _resolve_llm(
    llm_cfg: Any,
    providers: dict[str, LLMProvider],
) -> tuple[LLMProvider, str, ModelRouter]:
    """Resolve the default provider, model, and build the router."""
    default = providers.get(llm_cfg.default_provider)
    if default is None:
        if not providers:
            msg = "LLM providers are enabled but no providers are configured"
            raise ConfigError(msg)
        default = next(iter(providers.values()))
    default_model = llm_cfg.default_model

    routing_config: dict[str, dict[str, str]] = {}
    r = llm_cfg.routing
    if r.judge_provider != "default":
        routing_config["judge"] = {
            "provider": r.judge_provider,
            "model": r.judge_model or default_model,
        }
    if r.debate_agent_provider != "default":
        routing_config["debate_agent"] = {
            "provider": r.debate_agent_provider,
            "model": r.debate_agent_model or default_model,
        }
    if r.debate_consensus_provider != "default":
        routing_config["debate_consensus"] = {
            "provider": r.debate_consensus_provider,
            "model": r.debate_consensus_model or default_model,
        }

    router = ModelRouter.from_config(
        default_provider=default,
        default_model=default_model,
        routing_config=routing_config if routing_config else None,
        provider_pool=providers,
    )
    return default, default_model, router


def _require_context(ctx: Context[Any, Any, Any] | None) -> SDLCAppContext:
    if ctx is None:
        msg = "MCP context is required"
        raise RuntimeError(msg)
    return cast("SDLCAppContext", ctx.request_context.lifespan_context)


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[SDLCAppContext]:
    resolution = resolve_workspace()
    workspace_root = resolution.workspace_root
    BootstrapEngine(workspace_root).ensure_workspace()
    settings.ensure_dirs()
    bootstrap_logging(
        level=settings.logging.level,
        json_format=settings.logging.use_json,
        path=str(settings.resolve_runtime_path(settings.logging.path)),
    )
    logger = get_logger("app")
    for line in (
        f"Execution cwd: {resolution.execution_root}",
        f"Workspace root: {resolution.workspace_root}",
        f"Selection reason: {resolution.reason}",
    ):
        print(f"[foundry] {line}", file=sys.stderr)
        logger.info(line)

    graph = PhaseGraph(settings.load_phase_graph("feature"))
    model_routing = settings.load_model_routing()
    _validate_model_routing(graph, model_routing)

    store = SqliteStore(settings.resolve_runtime_path(settings.db_path))
    await store.initialize()
    policy = ExecutionPolicy()
    orchestrator = OrchestratorFSM(graph, policy)
    checkpoint_mgr = CheckpointManager(settings.resolve_runtime_path(settings.checkpoint_dir))

    acervo: Acervo | None = None
    memory_adapter: MemoryAdapter | None = None
    if settings.memory_enabled:
        acervo = Acervo(store_dir=settings.resolve_runtime_path("memory"))
        await acervo.initialize()
        memory_adapter = MemoryAdapter(acervo=acervo)
        logger.info("Cross-task memory enabled")

    write_queue = WriteQueue(_make_write_handler(store, checkpoint_mgr, acervo))
    await write_queue.start()

    judge_prompts = settings.load_all_judge_prompts()
    llm_cfg = settings.load_llm_config()
    judge_engine: JudgeEngine | None = None
    debate_runtime: DebateRuntime | None = None
    if llm_cfg.enabled:
        providers = _build_providers(llm_cfg)
        _default_provider, default_model, router = _resolve_llm(llm_cfg, providers)
        logger.info(
            "Runtime LLM provider initialized",
            extra={"default_provider": llm_cfg.default_provider, "default_model": default_model},
        )
        judge_provider, judge_model = router.route("judge")
        judge_engine = JudgeEngine(provider=judge_provider, model=judge_model)
    else:
        logger.info(
            "Runtime LLM providers disabled; OpenCode selected model drives all phases",
            extra={"default_model": llm_cfg.default_model},
        )

    tracer = Tracer(trace_dir=str(settings.resolve_runtime_path(settings.trace_dir)))
    tracer.enforce_retention()

    if llm_cfg.enabled:
        debate_agent_provider, debate_agent_model = router.route("debate_agent")
        debate_runtime = DebateRuntime(
            provider=debate_agent_provider,
            model=debate_agent_model,
            tracer=tracer,
        )

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
    index_pipeline = IndexPipeline(
        workspace=workspace_root,
        store_dir=settings.resolve_runtime_path(settings.index_dir),
        config=index_config,
    )
    await index_pipeline.initialize()
    if index_config.enabled and index_config.incremental:
        index_result = await index_pipeline.run_incremental_index()
        logger.info("Initial index complete", extra=index_result)

    logger.info("SDLC server initialized", extra={
        "graph": "feature",
        "runtime_llm_enabled": llm_cfg.enabled,
        "default_llm_provider": llm_cfg.default_provider,
        "default_model": llm_cfg.default_model,
            "trace_dir": settings.trace_dir,
            "workspace_root": str(workspace_root),
    })

    ctx = SDLCAppContext(
        store=store,
        checkpoint_mgr=checkpoint_mgr,
        orchestrator=orchestrator,
        policy=policy,
        write_queue=write_queue,
        graph=graph,
        model_routing=model_routing,
        judge_engine=judge_engine,
        tracer=tracer,
        index_pipeline=index_pipeline,
        debate_runtime=debate_runtime,
        acervo=acervo,
        memory_adapter=memory_adapter,
        workspace_root=str(workspace_root),
        config={
            "max_iterations": settings.max_iterations,
            "mode": "feature",
            "judge_prompts": judge_prompts,
        },
    )
    try:
        yield ctx
    finally:
        await write_queue.stop()
        await store.checkpoint()
        await store.close()
        logger.info("SDLC server shut down")


app = FastMCP("foundry-orchestrator", lifespan=lifespan)


def _workspace_resolution() -> WorkspaceResolution:
    return resolve_workspace()


def _ignored_override_status(
    path: str | None,
    workspace: str | None,
) -> dict[str, str | bool | None]:
    return {
        "path_override_ignored": path is not None,
        "workspace_override_ignored": workspace is not None,
        "ignored_path": path,
        "ignored_workspace": workspace,
    }


def _workspace_status(resolution: WorkspaceResolution) -> dict[str, Any]:
    root = resolution.workspace_root
    state, sdlc_dir = detect_workspace(root)
    expected = {
        "state": sdlc_dir / "state.json",
        "database": sdlc_dir / "workspace.db",
        "traces": sdlc_dir / "traces",
        "checkpoints": sdlc_dir / "checkpoints",
        "logs": sdlc_dir / "logs",
        "config": sdlc_dir / "config",
        "opencode": root / ".opencode",
    }
    missing = [name for name, target in expected.items() if not target.exists()]
    return {
        "execution_root": str(resolution.execution_root),
        "workspace_root": str(root),
        "sdlc_dir": str(sdlc_dir),
        "state": state.value,
        "ready": state == WorkspaceState.READY,
        "missing": missing,
        "detection_reason": resolution.reason,
        "selected_by": resolution.selected_by,
        "markers": list(resolution.markers),
    }


@app.tool()
async def sdlc_detect_workspace(
    path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Detect execution and Foundry workspace roots.

    MCP calls are confined to the selected process workspace. ``path`` and
    ``workspace`` are accepted for backward compatibility but ignored; use the
    CLI ``--workspace`` flag or ``FOUNDRY_WORKSPACE`` environment variable for
    explicit overrides.
    """
    return {
        **_workspace_status(_workspace_resolution()),
        **_ignored_override_status(path, workspace),
    }


@app.tool()
async def sdlc_bootstrap_workspace(
    path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Idempotently create or repair the current workspace's .sdlc infrastructure."""
    resolution = _workspace_resolution()
    root = resolution.workspace_root
    changed = BootstrapEngine(root).ensure_workspace()
    status = _workspace_status(resolution)
    return {"changed": changed, **status, **_ignored_override_status(path, workspace)}


@app.tool()
async def sdlc_upgrade_workspace(
    path: str | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Upgrade workspace schema and generated integration files to the latest version."""
    resolution = _workspace_resolution()
    root = resolution.workspace_root
    changed = BootstrapEngine(root).upgrade()
    status = _workspace_status(resolution)
    return {"changed": changed, **status, **_ignored_override_status(path, workspace)}


@app.tool()
async def sdlc_create_task(
    description: str,
    mode: str = "feature",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, str]:
    if mode != "feature":
        msg = f"Unsupported Phase 1 graph template: {mode}"
        raise ValueError(msg)
    sdlc_ctx = _require_context(ctx)
    judge_prompts = sdlc_ctx.config.get("judge_prompts", {})
    locked = dict(judge_prompts) if isinstance(judge_prompts, dict) else {}
    tracer = sdlc_ctx.tracer
    trace_id = tracer.create_trace_id() if tracer else None
    return await task_tools.create_task(
        sdlc_ctx.write_queue,
        description,
        mode,
        judge_prompts=locked,
        trace_id=trace_id,
    )


@app.tool()
async def sdlc_get_next_action(
    task_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    return await phase_tools.get_next_action(
        sdlc_ctx.store,
        sdlc_ctx.checkpoint_mgr,
        sdlc_ctx.orchestrator,
        task_id,
        sdlc_ctx.model_routing,
        tracer=sdlc_ctx.tracer,
        index_pipeline=sdlc_ctx.index_pipeline,
    )


@app.tool()
async def sdlc_submit_output(
    task_id: str,
    phase: str,
    output: str,
    next_phase: str | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    return await phase_tools.submit_output(
        sdlc_ctx.store,
        sdlc_ctx.checkpoint_mgr,
        sdlc_ctx.orchestrator,
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
    )


@app.tool()
async def sdlc_validate_phase(
    task_id: str,
    phase: str,
    output: str,
    next_phase: str | None = None,
    include_llm: bool = False,
    include_debate: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Validate a phase output without mutating task state."""
    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"accepted": False, "error": f"Task not found: {task_id}"}
    task = Task(**raw)
    if task.current_phase != phase:
        return {
            "accepted": False,
            "stage": "phase",
            "error": f"Phase mismatch: expected '{task.current_phase}', got '{phase}'",
        }

    try:
        resolved = sdlc_ctx.orchestrator.submit(phase, target=next_phase)
    except Exception as exc:  # noqa: BLE001 - MCP tool returns structured errors.
        return {"accepted": False, "stage": "transition", "error": str(exc)}

    schema_violations = validate_phase_output(phase, output)
    if schema_violations:
        return {
            "accepted": False,
            "stage": "deterministic",
            "next_phase": resolved,
            "issues": [str(v) for v in schema_violations],
        }

    verdict = None
    debate = None
    if include_llm and sdlc_ctx.judge_engine is not None and phase != "Chatting":
        verdict = await sdlc_ctx.judge_engine.evaluate(task, phase, resolved, output)
        if include_debate and not verdict.passed and sdlc_ctx.debate_runtime is not None:
            transcript = await sdlc_ctx.debate_runtime.run_debate(
                task=task,
                phase=phase,
                output=output,
                budget=task.budget,
            )
            debate = transcript.model_dump(mode="json")

    return {
        "accepted": verdict.passed if verdict else True,
        "stage": "llm" if verdict else "deterministic",
        "next_phase": resolved,
        "deterministic": {"passed": True, "issues": []},
        "judge_verdict": verdict.model_dump(mode="json") if verdict else None,
        "debate": debate,
    }


@app.tool()
async def sdlc_resume_task(
    task_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Restore a task from its latest checkpoint and return resumable phase state."""
    sdlc_ctx = _require_context(ctx)
    checkpoint = await sdlc_ctx.store.restore_checkpoint(task_id)
    raw = await sdlc_ctx.store.get_task(task_id)
    if checkpoint is None and raw is None:
        return {"resumed": False, "error": f"Task not found: {task_id}"}

    if checkpoint is not None and raw is not None:
        task = Task(**raw)
        task.current_phase = str(checkpoint.get("phase", task.current_phase))
        task.iteration_count = int(checkpoint.get("iteration_count", task.iteration_count))
        await sdlc_ctx.write_queue.enqueue(
            WriteOp(target="task", action="update", payload=task.model_dump(mode="json")),
        )
        await sdlc_ctx.write_queue.flush()
        raw = task.model_dump(mode="json")

    phase = checkpoint.get("phase") if checkpoint else raw.get("current_phase")
    return {
        "resumed": True,
        "task_id": task_id,
        "phase": phase,
        "checkpoint": checkpoint,
        "task": raw,
    }


@app.tool()
async def sdlc_request_approval(
    task_id: str,
    phase: str,
    summary: str,
    *,
    approved: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
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


@app.tool()
async def sdlc_get_status(
    task_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    return await task_tools.get_status(sdlc_ctx.store, sdlc_ctx.graph, task_id)


@app.tool()
async def sdlc_list_tasks(
    status: str | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    return await task_tools.list_tasks(sdlc_ctx.store, status)


@app.tool()
async def sdlc_cancel_task(
    task_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    return await task_tools.cancel_task(sdlc_ctx.store, sdlc_ctx.write_queue, task_id)


@app.tool()
async def sdlc_get_trace(
    trace_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.get_trace(sdlc_ctx.tracer, trace_id)


@app.tool()
async def sdlc_list_traces(
    task_id: str | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.list_traces(sdlc_ctx.tracer, task_id=task_id)


@app.tool()
async def sdlc_get_summaries(
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.get_summaries(sdlc_ctx.tracer)


@app.tool()
async def sdlc_enforce_retention(
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    if not sdlc_ctx.tracer:
        return {"error": "Tracing not available"}
    return await debug_tools.enforce_retention(sdlc_ctx.tracer)


@app.tool()
async def sdlc_index_repository(
    mode: str = "incremental",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    if mode == "full":
        return await pipeline.run_full_index()
    return await pipeline.run_incremental_index()


@app.tool()
async def sdlc_index_files(
    file_paths: list[str],
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return await pipeline.index_files(file_paths)


@app.tool()
async def sdlc_get_dependency_context(
    file_path: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return await pipeline.get_dependency_context(file_path)


@app.tool()
async def sdlc_get_index_stats(
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    pipeline = sdlc_ctx.index_pipeline
    if pipeline is None:
        return {"error": "Index pipeline not initialized"}
    return pipeline.stats


@app.tool()
async def sdlc_debate_output(
    task_id: str,
    phase: str,
    output: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    runtime = sdlc_ctx.debate_runtime
    if runtime is None:
        return {"error": "Debate runtime not initialized"}
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    transcript = await runtime.run_debate(
        task=task,
        phase=phase,
        output=output,
        budget=task.budget,
    )
    return {
        "task_id": task_id,
        "phase": phase,
        "rounds": len(transcript.rounds),
        "consensus": transcript.consensus.model_dump(mode="json") if transcript.consensus else None,
        "transcript": transcript.model_dump(mode="json"),
    }


@app.tool()
async def sdlc_memory_store(  # noqa: PLR0913 - MCP tool mirrors memory fields.
    content: str,
    task_id: str = "",
    phase: str = "",
    tags: list[str] | None = None,
    source: str = "unknown",
    importance: float = 0.5,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
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
async def sdlc_memory_query(  # noqa: PLR0913 - MCP tool mirrors query filters.
    phase: str | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    source: str | None = None,
    min_importance: float = 0.3,
    limit: int = 10,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
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
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    sdlc_ctx = _require_context(ctx)
    if sdlc_ctx.acervo is None:
        return {"error": "Cross-task memory not enabled"}
    return {"status": "ok", **sdlc_ctx.acervo.stats}


@app.resource("sdlc://phase-graph")
async def phase_graph_resource() -> str:
    graph = PhaseGraph(settings.load_phase_graph("feature"))
    phases = "\n".join(f"  - {phase}" for phase in graph.phases)
    transitions = "\n".join(
        f"  {transition['from']} -> {transition['to']}"
        for transition in graph.transitions
    )
    return f"Phase Graph (feature.yaml):\n{phases}\n\nTransitions:\n{transitions}"
