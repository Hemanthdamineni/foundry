# Memory Architecture

> Complete specification of Foundry's memory system: Acervo storage, Engram model, structured retrieval, error memory pattern matching, and memory lifecycle management.

---

## Memory System Overview

Foundry's memory system provides **structured, persistent, cross-task recall** for long-running autonomous execution. It allows the orchestrator and subagents to recall past context (what happened, what failed, what decisions were made) without scanning full execution histories.

### Architecture

```
MemoryStore (structured retrieval API)
    │
    ├── store_phase_summary()     → Record what happened in a phase
    ├── store_error()             → Record failures with resolutions
    ├── store_decision()          → Record why decisions were made
    │
    ├── get_phase_summaries()     → Recall phase history
    ├── get_error_history()       → Recall past failures
    ├── find_similar_error()      → Pattern-match new errors to resolved ones
    ├── get_decisions()           → Recall rationale
    └── get_context_for_phase()   → Aggregate context for phase execution
          │
          └── Acervo (JSONL storage backend)
                │
                ├── store()     → Append engram to JSONL file
                ├── query()     → Filter by phase/tags/keywords/source/importance
                ├── forget()    → Remove engram (triggers file rewrite)
                └── clear()     → Remove all engrams
```

---

## The Engram Model

An **Engram** is the atomic unit of memory — a tagged, scored knowledge item:

```python
class Engram(BaseModel):
    engram_id: str              # 16-char hex UUID
    task_id: str                # Owning task
    phase: str                  # Phase where created
    content: str                # Natural language content
    tags: list[str]             # Retrieval tags (multi-valued)
    source: str                 # Origin type: "phase_summary", "error_memory", "decision_record"
    importance: float = 0.5     # Retrieval priority: 0.0 (trivial) to 1.0 (critical)
    created_at: str             # ISO timestamp
    metadata: dict[str, Any]    # Structured data for deserialization back to typed models
```

### Importance Scoring

| Score | Meaning | Examples |
|---|---|---|
| 0.9 | Critical — affects future executions | Error memories, security findings |
| 0.8 | High — important context for phase execution | Phase summaries, architecture decisions |
| 0.7 | Standard — useful reference | General decisions, rationale records |
| 0.5 | Default — may or may not be useful | Uncategorized observations |
| 0.3 | Low — retrievable but deprioritized | Minor notes, low-confidence observations |

The default importance threshold for queries is `0.3` — engrams scored below this are effectively invisible to standard retrieval.

---

## Memory Types

### Phase Summary

Records what happened in each phase for downstream context:

```python
class PhaseSummary(BaseModel):
    task_id: str
    phase: str
    outcome: str                        # "accepted", "rejected", "skipped"
    key_decisions: list[str]            # What was decided
    files_affected: list[str]           # Which files were touched
    errors_encountered: list[str]       # Errors that occurred
    duration_ms: int = 0                # Execution time
```

**Storage format:** Serialized into `content` field as structured text:
```
Phase: Coding
Outcome: accepted
Decisions: Use FastAPI for routing; Add Pydantic models for validation
Files: api.py, models.py, tests/test_api.py
```

**Tags:** `["phase_summary", "<phase_name>", "<outcome>"]`  
**Importance:** 0.8  
**Source:** `"phase_summary"`

### Error Memory

Records failures with their resolutions for future pattern matching:

```python
class ErrorMemory(BaseModel):
    error_type: str                    # Failure category
    error_message: str                 # Raw error text
    phase: str = ""                    # Phase where error occurred
    task_id: str = ""                  # Originating task
    resolution: str = ""               # How it was resolved
    resolved: bool = False             # Whether a fix was found
    recurrence_count: int = 1          # How many times this error has occurred
```

**Tags:** `["error", "<error_type>", "<phase>"]`  
**Importance:** 0.9  
**Source:** `"error_memory"`

### Decision Record

Records why decisions were made with alternatives considered:

```python
class DecisionRecord(BaseModel):
    decision: str                      # What was decided
    rationale: str                     # Why
    phase: str = ""                    # When
    task_id: str = ""                  # Which task
    alternatives_considered: list[str]  # What else was evaluated
    outcome: str = ""                  # What happened as a result
```

**Tags:** `["decision", "<phase>"]`  
**Importance:** 0.7  
**Source:** `"decision_record"`

---

## Acervo Storage Backend

### Storage Format

Engrams are stored as **append-only JSONL** (one JSON object per line):

```
data/memory/engrams.jsonl
```

Each line is a complete `Engram.model_dump_json()` serialization.

### Write Operations

| Operation | Implementation | Performance |
|---|---|---|
| `store()` | Append single line to JSONL | O(1) — append-only |
| `forget()` | Remove from in-memory list, rewrite entire file | O(n) — full rewrite |
| `clear()` | Clear in-memory list, delete file | O(1) |

### Read Operations

All reads operate on the **in-memory list** (loaded at initialization):

| Operation | Filtering | Complexity |
|---|---|---|
| `query()` | phase → tags → keywords → source → importance → sort → limit | O(n) per filter |
| `get_by_task()` | task_id equality | O(n) |
| `get_by_id()` | engram_id equality | O(n) |

### Initialization

```python
async def initialize(self) -> None:
    self._load()  # Read JSONL line-by-line, parse into Engram objects
    self._loaded = True
```

Invalid lines are silently skipped with a warning log. This makes the system tolerant of partial file corruption.

### Query Pipeline

```python
async def query(
    phase=None,      # Filter: exact phase match
    tags=None,       # Filter: ANY tag in the list matches
    keywords=None,   # Filter: ANY keyword appears in content (case-insensitive)
    source=None,     # Filter: exact source match
    min_importance=0.3,  # Filter: importance >= threshold
    limit=10,        # Cap: return at most N results
) -> list[Engram]:
    # Apply filters in order: phase → tags → keywords → source → importance
    # Sort by importance descending
    # Return first `limit` results
```

**Tag matching is OR-based:** If `tags=["error", "Coding"]`, any engram with either tag matches.

**Keyword matching is OR-based and case-insensitive:** If `keywords=["timeout", "retry"]`, any engram containing either word matches.

---

## Structured Retrieval Layer (MemoryStore)

The `MemoryStore` wraps Acervo with typed APIs:

### Store Operations

```python
await memory_store.store_phase_summary(PhaseSummary(...))
await memory_store.store_error(ErrorMemory(...))
await memory_store.store_decision(DecisionRecord(...))
```

Each operation:
1. Serializes the typed model into a human-readable `content` string
2. Passes the full model as `metadata` for later deserialization
3. Sets appropriate tags, source, and importance
4. Calls `acervo.store()`

### Retrieval Operations

```python
# Get summaries for a specific task
summaries = await memory_store.get_phase_summaries(task_id, limit=10)

# Get error history, optionally filtered
errors = await memory_store.get_error_history(error_type="timeout", phase="Coding")

# Find a previously resolved error similar to a new one
match = await memory_store.find_similar_error("ImportError: no module named 'foo'")

# Get decisions for a task/phase
decisions = await memory_store.get_decisions(task_id, phase="Planning")

# Keyword search across all memory
results = await memory_store.search(["timeout", "retry"], phase="Coding")
```

### Phase Context Aggregation

Before executing a phase, the orchestrator can aggregate all relevant context:

```python
context = await memory_store.get_context_for_phase(task_id, "Coding")
```

Returns:
```python
{
    "phase_summaries": [...],      # What happened in prior phases
    "relevant_errors": [...],      # Past errors in this phase type
    "past_decisions": [...],       # Decisions from earlier in the task
    "total_memory_items": 12,
}
```

This is injected into the prompt context for the phase execution, giving the LLM awareness of past history.

---

## Error Memory Pattern Matching

### How It Works

When a new error occurs, the system can search for previously resolved similar errors:

```python
async def find_similar_error(self, error_message: str) -> ErrorMemory | None:
    # 1. Extract keywords: words > 3 chars, lowercase, first 5
    keywords = [w for w in error_message.lower().split() if len(w) > 3][:5]
    
    # 2. Query Acervo with keywords + "error" tag
    engrams = await self._acervo.query(
        tags=["error"],
        keywords=keywords,
        source="error_memory",
        limit=5,
    )
    
    # 3. Return first resolved match
    for e in engrams:
        if e.metadata and e.metadata.get("resolved"):
            return ErrorMemory(**e.metadata)
    
    return None
```

### Use Case

```
New error: "ImportError: cannot import name 'Router' from 'fastapi'"

Keyword extraction: ["importerror:", "cannot", "import", "name", "router"]

Acervo query: tags=["error"], keywords=above, source="error_memory"

Match found: ErrorMemory(
    error_type="import_error",
    error_message="ImportError: cannot import name 'Router' from 'fastapi'",
    resolution="FastAPI renamed 'Router' to 'APIRouter' in v0.100. Use 'from fastapi import APIRouter'.",
    resolved=True,
)
```

The resolution can then be injected into the retry prompt, allowing the LLM to apply the known fix.

### Limitations

- **No semantic similarity** — matching is keyword-based, not embedding-based
- **No confidence scoring** — first resolved match is returned, regardless of match quality
- **No decay** — old errors have the same weight as recent ones
- **No deduplication** — the same error stored multiple times appears multiple times

---

## Memory Adapter (ToolAdapter Interface)

The `MemoryAdapter` wraps Acervo as a `ToolAdapter` for the tool gateway:

```python
class MemoryAdapter(ToolAdapter):
    name = "memory"
    capability = ToolCapability.CODE_GRAPH

    async def execute(self, task: dict) -> dict:
        if "content" in task:
            # Store operation
            engram = await self._acervo.store(content=task["content"], ...)
            return {"passed": True, "summary": f"Stored engram {engram.engram_id}"}
        
        if "query" in task:
            # Query operation
            results = await self._acervo.query(...)
            return {"passed": True, "summary": f"Found {len(results)} engrams", "details": {...}}
```

### Healthcheck

```python
async def healthcheck(self) -> bool:
    return self._acervo is not None
```

---

## Memory Lifecycle

### Creation Flow

```
Phase execution completes
    │
    ├─ Submit output → write_queue
    │
    ├─ WriteHandler dispatches to memory target
    │   └─ memory_store.store_phase_summary(...)
    │       └─ acervo.store(content, tags, importance)
    │           └─ Append to engrams.jsonl
    │
    └─ On error:
        └─ memory_store.store_error(ErrorMemory(...))
            └─ acervo.store(content, tags=["error"], importance=0.9)
```

### Retrieval Flow

```
get_next_action(task_id) called
    │
    ├─ memory_store.get_context_for_phase(task_id, phase)
    │   ├─ get_phase_summaries(task_id)
    │   ├─ get_error_history(phase=phase)
    │   └─ get_decisions(task_id)
    │
    └─ Context injected into prompt for LLM
```

### Cleanup Flow

```
Task completes → no automatic cleanup
                  Memory persists across tasks
                  No TTL or expiration
                  
Manual cleanup: acervo.clear() → deletes engrams.jsonl
Per-engram: acervo.forget(engram_id) → rewrites file without that engram
```

### Configuration

```python
class BudgetPolicy(BaseModel):
    memory_enabled: bool = False  # Memory system is opt-in
```

When `memory_enabled=False`, the memory store is not initialized and no engrams are recorded. The system operates without cross-task memory.
