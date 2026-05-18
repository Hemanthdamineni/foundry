# Retrieval and Context

> Context harvesting, error pattern matching, phase context aggregation, memory-augmented retrieval, and how Foundry builds the information an agent needs.

---

## Context Sources

Every phase execution receives assembled context from multiple sources:

```
get_next_action()
    │
    ├── Task Description (always)
    │
    ├── Previous Phase Outputs (always)
    │   └── History from store.get_history(task_id)
    │
    ├── Code Context (when indexing enabled)
    │   ├── IndexPipeline.get_context_for_phase()
    │   │   ├── Relevant files (keyword match or explicit)
    │   │   ├── Code chunks (symbol-level granularity)
    │   │   └── Graph summary (file/symbol counts)
    │   └── Dependency context (imports/dependents)
    │
    ├── Memory Context (when memory_enabled=True)
    │   ├── Acervo.query() for similar past errors
    │   └── Error patterns from previous tasks
    │
    └── Model Routing (always)
        ├── Model + subagent assignment
        ├── Fallback chain
        └── Phase-specific constraints
```

---

## Context Harvesting (`engine/context_harvester.py`, 393 lines)

### Purpose

The context harvester runs during the pre-specification phase to automatically gather project structure, dependencies, and architecture context before the agent writes specs.

### Harvested Information

```python
class HarvestedContext(BaseModel):
    project_structure: str           # Directory tree
    key_files: list[str]            # Important files (README, config, entry points)
    dependencies: dict[str, str]    # Package dependencies with versions
    architecture_hints: list[str]   # Detected patterns (REST API, CLI, library)
    existing_tests: list[str]       # Test file paths
    language_breakdown: dict[str, int]  # {python: 42, javascript: 12}
```

### Pre-Spec Context Flow

```
Task created → ContextHarvester.harvest()
    │
    ├── Scan project structure
    ├── Identify key files (README, setup.py, pyproject.toml)
    ├── Parse dependency files
    ├── Detect architecture patterns
    ├── Locate existing tests
    ├── Count files by language
    │
    └── Returns HarvestedContext → injected into Specs phase prompt
```

### Spec-Lock Enforcement

After specs are approved, the harvester enforces the spec-lock rule:

```python
# All downstream phases checked for scope drift
for phase_output in downstream_outputs:
    signals = self._detect_expansion(phase_output, locked_spec)
    if signals:
        yield DriftWarning(phase=phase, signals=signals)
```

**No LLM calls** — the harvester is entirely template-based and keyword-based.

---

## Error Pattern Matching

### How It Works

When memory is enabled, the Acervo store maintains a repository of past errors. On failure, the system queries for similar past errors to provide the agent with resolution context.

```python
# In memory store (Acervo)
async def query_similar_errors(self, error_text: str, limit: int = 5):
    keywords = self._extract_keywords(error_text)
    matching = []
    for engram in self._engrams:
        if engram.category == "error" and self._match_score(engram, keywords) > 0.5:
            matching.append(engram)
    return sorted(matching, key=lambda e: e.relevance_score, reverse=True)[:limit]
```

### Keyword Extraction

```python
def _extract_keywords(self, text: str) -> list[str]:
    # Extract significant words (>3 chars, not stopwords)
    words = re.findall(r'\b[a-zA-Z_]\w{3,}\b', text.lower())
    return [w for w in words if w not in STOPWORDS]
```

### Error Resolution Context

When an error matches a past pattern:

```python
# Injected into retry prompt
context = f"""
Similar error encountered in past task {engram.task_id}:
Error: {engram.content}
Resolution: {engram.resolution}
"""
```

This provides the agent with concrete examples of how similar errors were resolved, improving retry success rates.

---

## Phase Context Aggregation

### What Each Phase Receives

| Phase | Task Description | Previous Outputs | Code Context | Memory | Constraints |
|---|---|---|---|---|---|
| Chatting | ✓ | ✗ | ✗ | ✗ | "No file editing" |
| Specs | ✓ | Chatting output | ✓ Harvested context | ✗ | "No file editing" |
| Planning | ✓ | Specs output | ✓ Full index | ✗ | "No file editing" |
| Coding | ✓ | Specs + Planning | ✓ Full index + deps | ✓ Past errors | Shell patterns |
| Testing | ✓ | Specs + Planning + Coding | ✓ Full index + deps | ✓ Past errors | Shell patterns |
| Review | ✓ | All previous | ✓ Full index | ✗ | "No file editing" |

### Context Assembly in get_next_action

```python
# 1. Build base context
context = {
    "task_description": task.description,
    "previous_outputs": [r.output or "" for r in task.history],
}

# 2. Add code context (if indexing enabled)
if pipeline:
    code_ctx = await pipeline.get_context_for_phase(
        phase=task.current_phase,
        target_files=task.affected_files,
        description=task.description,
    )
    context.update(code_ctx)

# 3. Add memory context (if memory enabled)
if acervo and task.last_error:
    similar = await acervo.query_similar_errors(task.last_error)
    context["error_context"] = [e.to_dict() for e in similar]

# 4. Add constraints
context["constraints"] = _build_constraints(task.current_phase, route)
```

---

## Retrieval Strategies

### Keyword-Based File Matching

For finding relevant files when no explicit target list is provided:

```python
keywords = [w.lower() for w in description.split() if len(w) > 3]
related_files = [fp for fp in all_files if any(kw in fp.lower() for kw in keywords)]
```

Simple but effective for code-heavy tasks where file names reflect functionality.

### Dependency-Based Expansion

Given a set of target files, expand to include their dependencies and dependents:

```python
async def get_dependency_context(self, file_path):
    deps = await engine.get_dependencies(file_path)       # What this file imports
    dependents = await engine.get_dependents(file_path)   # What imports this file
    symbols = engine.graph.files.get(file_path).symbols   # Symbols in this file
    return {"dependencies": deps, "dependents": dependents, "symbols": symbols}
```

### Symbol-Level Chunking

Rather than sending entire files, send individual symbols (classes, functions):

```python
for sym in file_index.symbols:
    chunk = ContextChunk(
        content=lines[sym.start_line:sym.end_line],
        symbol_name=sym.name,
        symbol_kind=sym.kind.value,
        relevance_score=1.0,  # Higher than arbitrary line chunks
    )
```

This provides focused, relevant context rather than overwhelming the agent with entire file contents.

---

## Context Size Management

| Parameter | Default | Purpose |
|---|---|---|
| `context_file_count` | 10 | Max files included in context |
| `context_chunk_count` | 20 | Max code chunks included |
| `chunk_size_lines` | 50 | Lines per chunk |
| `max_file_size_kb` | 512 | Skip files larger than this |

### Context Token Budget

Rough estimation of context token cost:
```
10 files × 20 chunks × 50 lines × ~10 tokens/line = ~100,000 tokens
```

This exceeds most model context windows. In practice:
- Most files produce 2-5 chunks (symbols, not line ranges)
- Keyword matching selects only the most relevant files
- The context_file_count and context_chunk_count caps prevent overflow

---

## Implementation Status

| Component | Status |
|---|---|
| ContextHarvester | **Implemented** — pre-spec context gathering |
| Spec-lock enforcement | **Implemented** — keyword-based drift detection |
| IndexPipeline context retrieval | **Implemented** — keyword + symbol-based |
| Dependency-based expansion | **Implemented** — import edges + dependents |
| Symbol-level chunking | **Implemented** — AST-based for Python |
| Error pattern matching | **Partial** — Acervo query exists, integration with retry prompts partial |
| Memory-augmented retrieval | **Partial** — Acervo stores engrams, query available, not auto-injected |
| Embedding-based retrieval | **Not implemented** — intentionally excluded |
