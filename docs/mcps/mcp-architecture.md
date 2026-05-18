# MCP Architecture

> Model Context Protocol server bootstrap, tool registration, lifespan management, request context, and the MCP communication model.

---

## What MCP Is

MCP (Model Context Protocol) is the communication protocol between Foundry (the server) and the host AI agent (the client, e.g., OpenCode). It defines how tools are discovered, invoked, and how results are returned.

Foundry is an **MCP server** — it exposes its functionality as a set of tools that the host agent calls. The host agent handles user interaction, LLM inference for phase execution, and file editing. Foundry handles orchestration, validation, state management, and quality control.

```
┌───────────────────┐     stdio      ┌──────────────────────┐
│ Host Agent        │ ◄────────────► │ Foundry MCP Server   │
│ (OpenCode)        │   MCP tools    │ (sdlc/runtime/app.py)│
│                   │                │                      │
│ - User interface  │                │ - Task management    │
│ - LLM inference   │                │ - Phase orchestration│
│ - File editing    │                │ - Validation gates   │
│ - Shell commands  │                │ - Judge evaluation   │
│ - Git operations  │                │ - Debate protocol    │
└───────────────────┘                │ - State persistence  │
                                     │ - Context retrieval  │
                                     └──────────────────────┘
```

---

## Server Bootstrap (`runtime/app.py`, 661 lines)

### FastMCP Framework

Foundry uses `mcp.server.fastmcp.FastMCP` for server construction:

```python
mcp = FastMCP("sdlc-server")
```

### Lifespan Initialization

The server lifespan initializes all subsystems in dependency order:

```python
@asynccontextmanager
async def lifespan(server):
    # 1. Bootstrap logging
    bootstrap_logging(settings)
    settings.ensure_dirs()
    
    # 2. Persistence layer
    store = SqliteStore(settings.resolve_runtime_path(settings.db_path))
    await store.initialize()
    
    # 3. Phase graph
    graph_data = settings.load_phase_graph("feature")
    graph = PhaseGraph(graph_data)
    
    # 4. Core engine components
    orchestrator = OrchestratorFSM(graph)
    policy = ExecutionPolicy()
    checkpoint_mgr = CheckpointManager(settings.resolve_runtime_path(settings.checkpoint_dir))
    
    # 5. LLM providers
    llm_config = settings.load_llm_config()
    provider = _build_provider(llm_config)
    
    # 6. Quality subsystems
    judge_engine = JudgeEngine(provider=provider, model=llm_config.default_model)
    debate_runtime = DebateRuntime(provider=provider)
    
    # 7. Observability
    tracer = Tracer(settings.resolve_runtime_path(settings.trace_dir))
    
    # 8. Indexing
    index_pipeline = IndexPipeline(workspace, index_dir, IndexConfig(**settings.index.model_dump()))
    await index_pipeline.initialize()
    
    # 9. Memory (optional)
    acervo = None
    if settings.memory_enabled:
        acervo = Acervo(memory_dir)
        await acervo.initialize()
    
    # 10. Write queue
    handler = _make_write_handler(store, checkpoint_mgr, acervo)
    write_queue = WriteQueue(handler=handler)
    
    # 11. Bundle into context
    ctx = SDLCAppContext(store=store, checkpoint_mgr=checkpoint_mgr, ...)
    
    yield {"sdlc": ctx}
    
    # Cleanup
    await write_queue.shutdown()
    await store.close()
```

### SDLCAppContext

All subsystems are bundled into a single context object accessible from every MCP tool handler:

```python
class SDLCAppContext:
    store: StoreBackend
    checkpoint_mgr: CheckpointManager
    orchestrator: OrchestratorFSM
    policy: ExecutionPolicy
    write_queue: WriteQueue
    graph: PhaseGraph
    model_routing: dict[str, Any]
    config: dict[str, Any]
    judge_engine: JudgeEngine | None
    tracer: Tracer | None
    index_pipeline: IndexPipeline | None
    debate_runtime: DebateRuntime | None
    acervo: Acervo | None
    memory_adapter: MemoryAdapter | None
```

---

## MCP Tool Surface

### 14 Registered Tools

| Tool | Category | Purpose |
|---|---|---|
| `sdlc_create_task` | Task | Create a new SDLC task |
| `sdlc_get_status` | Task | Get full task status with history |
| `sdlc_list_tasks` | Task | List all tasks, optionally filtered |
| `sdlc_cancel_task` | Task | Cancel an active task |
| `sdlc_get_next_action` | Phase | Get next phase prompt, context, constraints |
| `sdlc_submit_output` | Phase | Submit phase output for validation |
| `sdlc_request_approval` | Phase | Human approval for phase transition |
| `sdlc_index_workspace` | Index | Trigger workspace indexing |
| `sdlc_get_index_stats` | Index | Get indexing statistics |
| `sdlc_get_context` | Index | Get code context for a file |
| `sdlc_get_trace` | Debug | Read trace spans |
| `sdlc_list_traces` | Debug | List available traces |
| `sdlc_get_summaries` | Debug | Read trace summaries |
| `sdlc_enforce_retention` | Debug | Trigger trace cleanup |

### Tool Registration Pattern

```python
@mcp.tool()
async def sdlc_create_task(
    description: str,
    mode: str = "feature",
    ctx: Context = None,
) -> dict[str, Any]:
    """Create a new SDLC lifecycle task."""
    sdlc = _get_sdlc(ctx)
    # ... implementation ...
    return {"task_id": task.task_id, "phase": task.current_phase, ...}
```

### Context Access

Every tool handler accesses shared state through the MCP context:

```python
def _get_sdlc(ctx: Context) -> SDLCAppContext:
    return ctx.request_context.lifespan_context["sdlc"]
```

---

## Communication Model

### Transport: stdio

Foundry communicates over stdin/stdout using the MCP stdio transport:

```python
# Server startup
mcp.run(transport="stdio")
```

The host agent spawns Foundry as a subprocess and communicates via stdio. No HTTP, no WebSocket, no network — pure local IPC.

### Request Flow

```
Host Agent                          Foundry MCP Server
    │                                      │
    ├── MCP tool call ──────────────────►  │
    │   {tool: "sdlc_create_task",        │
    │    args: {description: "..."}}       │
    │                                      │
    │                                      ├── Validate args
    │                                      ├── Execute handler
    │                                      ├── Persist state
    │                                      │
    │  ◄─────────────────── MCP result ───┤
    │   {task_id: "abc123",               │
    │    phase: "Chatting", ...}           │
    │                                      │
```

### Stateless Protocol

MCP is stateless between calls. Each tool call is independent. All state lives in:
- SQLite database (tasks, history, checkpoints)
- JSON files (state, traces)
- In-memory context (derived from persistent state at startup)

---

## Write Queue

The write queue decouples tool responses from state persistence:

```python
class WriteQueue:
    _queue: asyncio.Queue[WriteOp]
    _handler: WriteHandler  # async callback
    _task: asyncio.Task     # background consumer
```

### Write Operations

```python
class WriteOp(BaseModel):
    target: str          # "task", "phase", "checkpoint", "memory"
    action: str          # "create", "update", "save"
    payload: dict        # Operation-specific data
    source_span: str     # Trace span ID for correlation
```

### Dispatch

```python
async def handler(op: WriteOp):
    if op.target == "task":
        if op.action == "create":
            await store.create_task(op.payload)
        elif op.action == "update":
            await store.update_task(op.payload["task_id"], op.payload)
    elif op.target == "phase":
        await store.save_phase_output(op.payload["task_id"], ...)
    elif op.target == "checkpoint":
        await checkpoint_mgr.save(op.payload["task_id"], ...)
    elif op.target == "memory" and acervo:
        await acervo.store(content=op.payload.get("content", ""), ...)
```

---

## Implementation Status

| Component | Status |
|---|---|
| FastMCP server | **Implemented** — stdio transport, tool registration |
| SDLCAppContext | **Implemented** — all subsystems bundled |
| Lifespan initialization | **Implemented** — ordered startup/shutdown |
| 14 MCP tools | **Implemented** — task, phase, index, debug categories |
| Write queue | **Implemented** — async FIFO with handler dispatch |
| Transport | **stdio only** — no HTTP/WebSocket |
| Tool discovery | **Implemented** — FastMCP auto-generates tool metadata |
| Authentication | **None** — local-only, trusts the host agent |
