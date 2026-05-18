# Architecture Patterns

## Layered Architecture
The system has 5 layers — never import upward:
1. **engine/** — Core orchestration (FSM, policy, judge, consensus, debate)
2. **adapters/** — ToolAdapter implementations (lint, typing, testing, graph, memory, sandbox, VCS, LLM)
3. **runtime/** — MCP server facade, tools, resources, pipelines, persistence
4. **validators/** — Deterministic validation runners
5. **config/** — Configuration loading and environment handling

## ToolAdapter Pattern
Every external tool implements the `ToolAdapter` ABC:
```python
class ToolAdapter:
    name: str
    capability: str  # e.g. "lint", "typing", "testing"
    async def validate(self, task): ...
    async def execute(self, task): ...
    async def healthcheck(self): ...
```
The orchestrator talks to capabilities, never tools.

## StoreBackend Abstraction
Persistence is behind `StoreBackend` ABC — never import `aiosqlite` directly.
Two implementations: `SqliteStore` (now) and future `PostgresStore`.

## WriteQueue Pattern
All writes go through `WriteQueue` — single-worker serialized persistence.
Reads bypass the queue (WAL mode handles concurrent reads).

## ExecutionPolicy Separation
- `OrchestratorFSM` answers: "what phase comes next?"
- `ExecutionPolicy` answers: "should we proceed, retry, or abort?"
- FSM → Policy flow, never Policy → FSM

## Plugin Enforcement
- Plugin is enforcement-only — no formatting, tracing, or decisions
- Hard phase gates via `tool.execute.before`
- State sync via `tool.execute.after`
- Anchored compaction via `experimental.session.compacting`
