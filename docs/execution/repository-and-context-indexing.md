# Repository and Context Indexing

Repository indexing is not part of the MVP critical path.

## MVP Position

The first operational loop does not require semantic context retrieval,
dependency expansion, tree-sitter indexing, graph visualization, vector search,
or context harvesting.

The submit path may use the workspace root for validation:

```python
{"path": workspace_path}
```

Changed-file targeting and structural context selection are post-MVP
optimizations.

## Deferred

Index pipelines, dependency graph engines, symbol extraction, tree-sitter,
graphify, embedding/vector retrieval, context harvesters, and impact analysis
must not block ToolExecutor, ToolGate, checkpoint, persistence, or recovery work.
