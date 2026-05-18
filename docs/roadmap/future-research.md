# Future Research

> Distributed runtime concepts, advanced retrieval, multi-model evaluation, scaling strategies, and experimental ideas that may shape Foundry's long-term evolution.

---

## Distributed Runtime

### Concept

Extend Foundry from a single-machine MCP server to a distributed execution runtime where:
- Multiple agents execute different phases concurrently
- State is replicated across nodes
- Checkpoints are shared via distributed storage
- Task dependencies span machines

### Architecture Sketch

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Node A       │  │ Node B       │  │ Node C       │
│ (Specs agent)│  │ (Code agent) │  │ (Test agent) │
│              │  │              │  │              │
│ Local Ollama │  │ Local GPU    │  │ CI runner    │
│ qwen3:8b     │  │ codellama    │  │ pytest       │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                 ┌───────┴───────┐
                 │ Coordinator   │
                 │ (state sync)  │
                 │ PostgreSQL    │
                 │ S3 checkpoints│
                 └───────────────┘
```

### Requirements

- Replace SQLite with PostgreSQL for multi-writer support
- Replace file-based checkpoints with S3/GCS for shared access
- Add distributed locking for phase transitions (prevent concurrent advancement)
- Add heartbeat/health monitoring for node failure detection
- Maintain all 10 invariants across distributed boundaries

### Why Deferred

Single-machine execution is sufficient for individual developer workflows. Distributed adds infrastructure complexity that isn't justified until team-scale adoption exists.

---

## Advanced Retrieval

### Hybrid Retrieval (Structural + Semantic)

Combine current structural indexing with semantic understanding:

```
Structural: import edges + file paths + symbol names
    +
Semantic: code embeddings + natural language queries
    =
Hybrid: high-precision structural results + high-recall semantic results
```

### Code-Specific Embedding Models

| Model | Training Data | Strength |
|---|---|---|
| CodeBERT | Code + documentation | Cross-lingual code understanding |
| StarCoder embeddings | 80+ languages | Multi-language code similarity |
| UniXcoder | Code + comments | Function-level similarity |

### Relevance Learning

Track which context chunks the agent actually used (by detecting referenced file names in output). Over time, learn which retrieval strategies produce context the agent finds useful:

```
Phase output references auth.py lines 45-80
    → context chunk for AuthService.validate() was relevant
    → increase relevance score for symbol-level chunks
    → decrease relevance score for line-range chunks that weren't referenced
```

### Why Deferred

Structural indexing works well enough for current use cases. Embedding infrastructure adds GPU dependency and maintenance burden. Worth revisiting when project sizes consistently exceed structural indexing effectiveness.

---

## Multi-Model Evaluation

### Cross-Model Judge Panels

Instead of one model judging, use a panel:

```
Judge Panel:
    GPT-4o:   "This code has a race condition in the auth flow"
    Claude:   "The error handling doesn't cover network timeouts"
    Qwen:     "Test coverage for edge cases is insufficient"
    
Consensus: 3/3 identify issues → high confidence rejection
```

### Model Disagreement Analysis

When models disagree, the disagreement itself is informative:

```
GPT-4o:   PASS (confidence: 0.8)
Claude:   FAIL (confidence: 0.9) — "Missing error handling"
Qwen:     PASS (confidence: 0.6)

Analysis: Claude identified a specific concern with high confidence
    → route the concern to the agent for explicit resolution
    → don't simply majority-vote it away
```

### Why Deferred

Requires multiple LLM providers with API keys. Increases evaluation cost 3×. Current single-model + debate provides sufficient quality control for the development stage.

---

## Scaling Strategies

### Task Parallelism

Execute independent tasks concurrently:

```
Task A (feature/auth):   Specs → Planning → Coding → Testing → Review
Task B (feature/search): Specs → Planning → Coding → Testing → Review

Both execute simultaneously if they touch different files.
Conflict detection via impact analysis (get_impact_analysis).
```

### Phase Parallelism (Within Task)

For tasks with independent subtasks:

```
Planning identifies 3 independent modules:
    Module A: auth refactor (files: auth.py, auth_test.py)
    Module B: search feature (files: search.py, search_test.py)
    Module C: config update (files: config.py)

Coding phase executes Module A, B, C in parallel.
Testing phase runs all tests sequentially (conflict avoidance).
```

### Incremental Validation

Instead of validating the complete output, validate incrementally:

```
Agent produces function 1 → validate syntax + lint → proceed
Agent produces function 2 → validate syntax + lint → proceed
Agent produces function 3 → validate syntax + lint → proceed
Full integration validation after all functions complete
```

Reduces wasted tokens on fundamentally wrong approaches.

---

## Experimental Ideas

### Prompt Evolution

Track prompt effectiveness over time and evolve prompts:

```
judge_specs v1: 60% first-pass acceptance rate
judge_specs v2: 72% first-pass acceptance rate (better section guidance)
judge_specs v3: 85% first-pass acceptance rate (added examples)
```

Use A/B testing to compare prompt versions across similar tasks.

### Execution Fingerprinting

Create unique fingerprints for execution patterns:

```
Fingerprint: {graph_hash}:{prompt_hashes}:{model_versions}:{tool_versions}
```

Two executions with the same fingerprint should produce comparable results. Fingerprint changes indicate configuration drift.

### Adaptive Budget Allocation

Instead of fixed budgets, allocate based on task complexity:

```
Simple task (1-2 files): 30K tokens, 15 min, 4 retries
Medium task (3-5 files): 80K tokens, 30 min, 8 retries
Complex task (5+ files): 150K tokens, 60 min, 12 retries

Complexity estimated from: file count, symbol count, dependency depth
```

### Memory-Augmented Debate

Feed past debate transcripts to current debate agents:

```
"In a previous debate about similar code, Agent Review noted that
error handling in async functions was consistently insufficient.
Consider this pattern when evaluating."
```

This would require cross-task memory and debate transcript indexing.

---

## Research Priority

| Research Area | Impact | Effort | Priority |
|---|---|---|---|
| ToolGate integration | High (immediate quality improvement) | Medium | **P0** |
| Bugfix/review graphs | Medium (workflow completeness) | Low | **P1** |
| Budget stats API | Low (observability) | Low | **P1** |
| Multi-model debate | Medium (evaluation quality) | Medium | **P2** |
| Hybrid retrieval | Medium (context quality) | High | **P2** |
| Distributed runtime | High (team scaling) | Very High | **P3** |
| Prompt evolution | Medium (quality improvement) | High | **P3** |
| Adaptive budgets | Low (resource optimization) | Medium | **P3** |
