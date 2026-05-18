# Repository and Context Indexing

> IndexPipeline, DependencyGraphEngine, RepositoryIndexer, file parsing, symbol extraction, context retrieval, and impact analysis.

---

## Indexing Architecture

Foundry uses **deterministic structural indexing** — not embeddings, not vector stores. Context is assembled from import edges, dependent files, symbol extraction, and keyword matching.

```
IndexPipeline (orchestration)
    │
    ├── _collect_indexable_files()     → Walk workspace with include/exclude patterns
    ├── _index_file()                  → Parse file → extract symbols + imports
    │       │
    │       └── DependencyGraphEngine  → Maintain file graph with edges
    │               │
    │               ├── parse_file()        → Language detection, AST parsing, SHA256
    │               ├── update_file()       → Update graph edges + dependents
    │               ├── get_relevant_context() → Symbol-aware code chunks
    │               └── persist() / load()  → JSON serialization
    │
    ├── get_context_for_phase()        → Assemble context for agent execution
    └── get_dependency_context()       → Dependency analysis for specific files
            │
            └── RepositoryIndexer (optional higher-level)
                    ├── index()                  → Full repo architecture summary
                    ├── _extract_api_surface()   → Public API endpoint extraction
                    ├── _classify_layers()       → Module layer classification
                    └── get_impact_analysis()    → Change impact assessment
```

---

## IndexPipeline (`runtime/pipelines/default.py`, 415 lines)

### Purpose

The IndexPipeline is the primary interface for workspace indexing. It manages the full lifecycle: file discovery, incremental indexing, context retrieval, and graph persistence.

### Configuration

```python
class IndexConfig(BaseModel):
    enabled: bool = True
    max_files: int = 5000                    # Cap on indexed files
    max_file_size_kb: int = 512              # Skip files larger than this
    include_patterns: list[str] = [          # Glob patterns to include
        "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
        "*.rs", "*.go", "*.java",
        "*.yaml", "*.yml", "*.json", "*.md",
    ]
    exclude_patterns: list[str] = [          # Glob patterns to exclude
        "*.pyc", "__pycache__/*", ".git/*",
        "node_modules/*", ".pixi/*", ".venv/*",
        "data/*", ".opencode/*",
    ]
    incremental: bool = True                 # SHA-based change detection
    chunk_size_lines: int = 50               # Lines per context chunk
    context_file_count: int = 10             # Max files in context
    context_chunk_count: int = 20            # Max chunks in context
```

### Indexing Modes

**Full Index (`run_full_index`):**
```
Walk workspace → parse every matching file → rebuild dependency graph → persist
```
Used on first run or when the graph is missing/corrupt. O(n) where n = number of files.

**Incremental Index (`run_incremental_index`):**
```
Walk workspace → check SHA cache → parse only changed files → update graph → persist
```
Used on subsequent runs. Only re-indexes files whose content SHA256 has changed. O(k) where k = changed files.

**Targeted Index (`index_files`):**
```
Take specific file paths → parse and update → persist
```
Used after file edits to update the graph for specific changed files.

### SHA-Based Change Detection

```python
# SHA cache: {file_path: sha256_hash}
# Stored at: data/index/sha_cache.json

async def _is_changed(self, fp: Path) -> bool:
    if str(fp) not in self._graph_engine.graph.files:
        return True                    # New file
    prev_sha = self._sha_cache.get(str(fp))
    if prev_sha is None:
        return True                    # No cached hash
    current_sha = _compute_sha256(fp.read_bytes())
    return current_sha != prev_sha     # Content changed
```

The SHA cache itself uses atomic writes (`tmp+rename`) to prevent corruption.

---

## DependencyGraphEngine (`engine/dependency_graph.py`, 510 lines)

### Graph Model

```python
class DependencyGraph(BaseModel):
    files: dict[str, FileIndex]           # path → file metadata + symbols + imports
    import_edges: dict[str, list[str]]    # path → [resolved import targets]
    dependents: dict[str, list[str]]      # path → [files that import this file]
    indexed_at: str                       # ISO timestamp
    file_count: int = 0
    symbol_count: int = 0
```

### File Parsing

```python
def parse_file(file_path: str, content: str | None = None) -> FileIndex:
    lang = _detect_language(file_path)     # Extension-based (.py → python)
    sha256 = _compute_sha256(content)      # Content hash (16 char)
    
    if lang == "python":
        symbols = _extract_python_symbols(file_path, content)   # AST-based
        imports = _extract_imports_python(file_path, content)    # Regex-based
    else:
        symbols = _extract_generic_symbols(file_path, content)  # Regex-based
        imports = _extract_imports_js(file_path, content)        # Regex for JS/TS
    
    return FileIndex(path=file_path, language=lang, symbols=symbols, imports=imports, ...)
```

### Python Symbol Extraction (AST-Based)

For Python files, the engine uses `ast.parse()` for accurate symbol extraction:

```python
def _extract_python_symbols(file_path, content):
    tree = ast.parse(content, filename=file_path)
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(CodeSymbol(name=node.name, kind=CLASS, ...))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(CodeSymbol(name=item.name, kind=METHOD, parent=node.name, ...))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(CodeSymbol(name=node.name, kind=FUNCTION, ...))
    return symbols
```

Captures: classes, methods (with parent class), functions, docstrings, line ranges.

### Language Support

| Language | Symbol Extraction | Import Extraction | Quality |
|---|---|---|---|
| Python | AST-based (`ast.parse`) | Regex | High |
| JavaScript/TypeScript | Regex-based | Regex | Medium |
| All others | Regex-based | Regex (JS-style) | Basic |

Supported extensions: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.rs`, `.go`, `.java`, `.rb`, `.swift`, `.kt`, `.c`, `.cpp`, `.cs`, `.php`, `.scala`, `.yaml`, `.json`, `.md`, `.html`, `.css`, `.sql`, `.sh`

### Import Resolution

```python
def resolve_import_to_file(import_info, known_files, search_paths=None):
    # For import "foo", try:
    #   {search_path}/foo.py
    #   {search_path}/foo/__init__.py
    #   {search_path}/foo.js, foo.ts, foo/index.js, foo/index.ts
    #   foo.py, foo/__init__.py (relative)
    
    for candidate in candidates:
        if candidate in known_files:
            return candidate
    return None  # Unresolved (external dependency)
```

### Graph Operations

```python
# Update file and recompute edges
await engine.update_file(file_path, file_index)

# Remove file and clean edges
await engine.remove_file(file_path)

# Query relationships
deps = await engine.get_dependencies(file_path)      # What this file imports
dependents = await engine.get_dependents(file_path)  # What imports this file
symbols = await engine.get_symbol("AuthService")     # Find by name
classes = await engine.get_symbols_by_kind(SymbolKind.CLASS)

# Context retrieval
chunks = await engine.get_relevant_context(
    target_files=["auth.py"],
    max_files=10,
    max_chunks=20,
    chunk_size=50,
)
```

### Context Chunk Generation

Two modes for generating context chunks from a file:

**Symbol-based chunking** (when symbols exist):
```python
for sym in file_index.symbols:
    chunk = ContextChunk(
        content=lines[sym.start_line:sym.end_line],
        symbol_name=sym.name,
        symbol_kind=sym.kind,
        relevance_score=1.0,
    )
```

**Line-based chunking** (fallback for files without symbols):
```python
for i in range(0, len(lines), chunk_size):
    chunk = ContextChunk(
        content=lines[i:i+chunk_size],
        relevance_score=0.5,  # Lower than symbol-based
    )
```

---

## Context Retrieval for Phase Execution

### get_context_for_phase

This is the primary interface called by `get_next_action`:

```python
async def get_context_for_phase(self, phase, target_files=None, description=""):
    # 1. Determine relevant files
    if target_files:
        related_files = target_files
    elif description:
        # Keyword matching: extract words > 3 chars, match against file paths
        keywords = [w.lower() for w in description.split() if len(w) > 3]
        related_files = [fp for fp in all_files if any(kw in fp.lower() for kw in keywords)]
    else:
        related_files = list(all_files)[:10]  # Fallback: first 10 files
    
    # 2. Get code chunks via dependency graph
    chunks = await self._graph_engine.get_relevant_context(
        target_files=related_files,
        max_files=config.context_file_count,    # 10
        max_chunks=config.context_chunk_count,  # 20
        chunk_size=config.chunk_size_lines,     # 50
    )
    
    # 3. Assemble response
    return {
        "relevant_files": related_files,
        "context_chunks": [c.model_dump() for c in chunks],
        "graph_summary": {"file_count": ..., "symbol_count": ..., "phase": phase},
    }
```

---

## RepositoryIndexer (`engine/repository_indexer.py`, 331 lines)

### Purpose

Higher-level indexer that builds architecture summaries, extracts API surfaces, and classifies modules into layers. Used for repository understanding, not phase execution.

### Architecture Summary

```python
class ArchitectureSummary(BaseModel):
    root: str                                # Workspace path
    total_files: int
    total_symbols: int
    languages: dict[str, int]               # {python: 42, javascript: 15}
    modules: list[ModuleSummary]            # Per-module breakdown
    api_surface: list[APIEndpoint]          # Public API endpoints
    layer_map: dict[str, list[str]]         # {foundation: [...], domain: [...]}
    entry_points: list[str]                 # __main__.py, app.py, cli.py
    test_modules: list[str]                 # test_*.py, tests/
    config_files: list[str]                 # *.yaml, *.toml, *.json
```

### Layer Classification

Modules are classified into architectural layers by keyword matching:

| Layer | Keywords | Examples |
|---|---|---|
| foundation | model, schema, type, exception | `models.py`, `exceptions.py` |
| domain | engine, core, service | `engine/`, `judge.py` |
| infrastructure | adapter, runtime, store | `adapters/`, `store_sqlite.py` |
| presentation | cli, api, web, ui | `cli.py`, `app.py` |
| testing | test, spec, fixture | `tests/`, `conftest.py` |

### Impact Analysis

```python
def get_impact_analysis(self, changed_files: list[str]) -> dict:
    # Direct dependents
    affected = set()
    for fp in changed_files:
        affected.update(graph.dependents.get(fp, []))
    
    # Transitive dependents (1 level)
    transitive = set()
    for fp in affected:
        transitive.update(graph.dependents.get(fp, []))
    
    return {
        "changed_files": changed_files,
        "directly_affected": list(affected),
        "transitively_affected": list(transitive - affected),
        "test_files_affected": [f for f in (affected | transitive) if "test" in f.lower()],
    }
```

---

## Graph Persistence

The dependency graph is persisted as a single JSON file:

```
data/index/dependency_graph.json
```

### Load with Size Guard

```python
async def load(self, max_bytes=1_048_576):
    if self._path.stat().st_size > max_bytes:
        return False  # Skip loading oversized graphs
    data = json.loads(self._path.read_text())
    self._graph = DependencyGraph(**data)
```

### Atomic Persist

```python
async def persist(self):
    data = self._graph.model_dump(mode="json")
    tmp = self._path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.rename(self._path)  # Atomic
```

---

## Implementation Status

| Component | Status |
|---|---|
| IndexPipeline | **Implemented** — full/incremental/targeted indexing |
| DependencyGraphEngine | **Implemented** — graph maintenance, context retrieval |
| Python AST symbol extraction | **Implemented** — classes, methods, functions |
| Generic symbol extraction | **Implemented** — regex-based for non-Python |
| SHA-based incremental indexing | **Implemented** — cache with atomic writes |
| RepositoryIndexer | **Implemented** — architecture summaries, API surface |
| Impact analysis | **Implemented** — direct + transitive dependents |
| TreeSitter adapter | **Implemented** — optional enhanced parsing |
| Graphify adapter | **Implemented** — optional graph visualization |
| Embedding-based retrieval | **Not implemented** — intentionally excluded |
