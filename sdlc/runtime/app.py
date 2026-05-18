"""FastMCP application bootstrap — wires all tools, resources, and lifespan."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from mcp.server.fastmcp import Context, FastMCP

from sdlc.adapters.llm import LLMProvider, ModelRouter, OllamaProvider, OpenAIProvider
from sdlc.adapters.memory import Acervo, MemoryAdapter
from sdlc.config import PACKAGE_ROOT, Settings, settings
from sdlc.engine.checkpoint import CheckpointManager
from sdlc.engine.debate_runtime import DebateRuntime
from sdlc.engine.execution_policy import ExecutionPolicy
from sdlc.engine.judge import JudgeEngine
from sdlc.engine.orchestrator import OrchestratorFSM
from sdlc.engine.phase_graph import PhaseGraph
from sdlc.exceptions import ConfigError
from sdlc.log import bootstrap_logging, get_logger
from sdlc.models import Checkpoint, IndexConfig, Task, WriteOp
from sdlc.runtime.pipelines.default import IndexPipeline
from sdlc.runtime.store_sqlite import SqliteStore
from sdlc.runtime.tools import debug as debug_tools
from sdlc.runtime.tools import phase as phase_tools
from sdlc.runtime.tools import task as task_tools
from sdlc.runtime.tracing import Tracer
from sdlc.runtime.write_queue import WriteHandler, WriteQueue

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sdlc.runtime.store_backend import StoreBackend


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
    settings.ensure_dirs()
    bootstrap_logging(
        level=settings.logging.level,
        json_format=settings.logging.use_json,
        path=str(settings.resolve_runtime_path(settings.logging.path)),
    )
    logger = get_logger("app")

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
        acervo = Acervo(store_dir=settings.resolve_runtime_path("data/memory"))
        await acervo.initialize()
        memory_adapter = MemoryAdapter(acervo=acervo)
        logger.info("Cross-task memory enabled")

    write_queue = WriteQueue(_make_write_handler(store, checkpoint_mgr, acervo))
    await write_queue.start()

    llm_cfg = settings.load_llm_config()
    providers = _build_providers(llm_cfg)
    default_provider, default_model, router = _resolve_llm(llm_cfg, providers)
    logger.info(
        "LLM provider initialized",
        extra={"default_provider": llm_cfg.default_provider, "default_model": default_model},
    )

    judge_provider, judge_model = router.route("judge")
    judge_prompts = settings.load_all_judge_prompts()
    judge_engine = JudgeEngine(provider=judge_provider, model=judge_model)

    tracer = Tracer(trace_dir=str(settings.resolve_runtime_path(settings.trace_dir)))
    tracer.enforce_retention()

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
        workspace=PACKAGE_ROOT,
        store_dir=settings.resolve_runtime_path(settings.index_dir),
        config=index_config,
    )
    await index_pipeline.initialize()
    if index_config.enabled and index_config.incremental:
        index_result = await index_pipeline.run_incremental_index()
        logger.info("Initial index complete", extra=index_result)

    logger.info("SDLC server initialized", extra={
        "graph": "feature",
        "default_llm_provider": settings.llm.default_provider,
        "default_model": settings.llm.default_model,
        "trace_dir": settings.trace_dir,
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


app = FastMCP("sdlc-orchestrator", lifespan=lifespan)


@app.tool()
async def sdlc_create_task(
    description: str,
    mode: str = "feature",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, str]:
    supported_modes = {"feature", "bugfix", "refactor", "research", "docs"}
    if mode not in supported_modes:
        msg = f"Unsupported graph template: {mode}. Supported: {supported_modes}"
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


@app.tool()
async def sdlc_harvest_context(
    task_id: str,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Run pre-spec context harvesting — generates questions across 10 categories."""
    from sdlc.engine.context_harvester import ContextHarvester

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
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Check if a post-spec output drifts from the locked spec."""
    from sdlc.engine.context_harvester import check_spec_drift

    sdlc_ctx = _require_context(ctx)
    raw = await sdlc_ctx.store.get_task(task_id)
    if raw is None:
        return {"error": f"Task not found: {task_id}"}
    task = Task(**raw)
    # Find the locked spec from history
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

