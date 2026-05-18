# Metrics and Telemetry

> Logger categories, structured log schema, performance metrics, health monitoring, and telemetry patterns.

---

## Logging Architecture

### Bootstrap

```python
# sdlc/log.py
def bootstrap_logging(settings):
    handler = RotatingFileHandler(settings.log_path, maxBytes=10*1024*1024, backupCount=5)
    if settings.logging.use_json:
        handler.setFormatter(JSONFormatter())
    root = logging.getLogger("sdlc")
    root.addHandler(handler)
    root.setLevel(settings.logging.level)

def get_logger(name: str) -> Logger:
    return logging.getLogger(f"sdlc.{name}")
```

### Logger Categories

| Logger Name | Module | What It Logs |
|---|---|---|
| `sdlc.orchestrator` | `engine/orchestrator.py` | Phase transitions, FSM state changes |
| `sdlc.judge` | `engine/judge.py` | Verdicts, prompt selection, schema check results |
| `sdlc.judge_hierarchy` | `engine/judge_hierarchy.py` | Multi-judge results, consensus gate |
| `sdlc.debate` | `engine/debate_runtime.py` | Round starts/ends, agent responses |
| `sdlc.consensus` | `engine/consensus.py` | Consensus results, collapse detection |
| `sdlc.confidence` | `engine/confidence_gate.py` | Vote normalization, threshold decisions |
| `sdlc.recovery` | `engine/recovery_engine.py` | Failure classification, escalation levels |
| `sdlc.retry` | `engine/retry_policy.py` | Retry counts, no-progress detection |
| `sdlc.checkpoint` | `engine/checkpoint.py` | Save/restore operations, version chains |
| `sdlc.budget` | `runtime/budget_controller.py` | Token consumption, violations, warnings |
| `sdlc.tracing` | `runtime/tracing.py` | Span lifecycle, retention, summaries |
| `sdlc.index_pipeline` | `runtime/pipelines/default.py` | Indexing progress, file counts, errors |
| `sdlc.dependency_graph` | `engine/dependency_graph.py` | Graph updates, edge changes, persistence |
| `sdlc.repository_indexer` | `engine/repository_indexer.py` | Architecture summaries, API surfaces |
| `sdlc.llm_providers` | `adapters/llm/providers.py` | LLM call attempts, failures, retries |
| `sdlc.memory` | `adapters/memory/acervo.py` | Engram storage, retrieval, lifecycle |
| `sdlc.write_queue` | `runtime/write_queue.py` | Write operations, queue depth |

---

## Structured Log Format

When `use_json=True` (default):

```json
{
    "timestamp": "2026-05-18T21:00:00Z",
    "level": "INFO",
    "logger": "sdlc.orchestrator",
    "message": "Phase transition",
    "extra": {
        "task_id": "abc123",
        "from_phase": "Specs",
        "to_phase": "Planning",
        "verdict": "passed",
        "iteration": 2
    }
}
```

### Key Log Events

| Event | Logger | Level | Extra Fields |
|---|---|---|---|
| Task created | orchestrator | INFO | task_id, mode, description_len |
| Phase transition | orchestrator | INFO | task_id, from_phase, to_phase |
| Judge verdict | judge | INFO | task_id, phase, passed, reason |
| Schema check failure | judge | WARNING | task_id, phase, missing_sections |
| Debate round complete | debate | INFO | round, agents, phase |
| Consensus reached | consensus | INFO | passed, collapse_detected, minority_count |
| Budget warning | budget | WARNING | resource, current, limit |
| Budget critical | budget | ERROR | resource, current, limit |
| Recovery escalation | recovery | WARNING | phase, level, reason |
| Checkpoint saved | checkpoint | INFO | task_id, version, phase |
| Index complete | index_pipeline | INFO | files_indexed, total_symbols |
| LLM call failed | llm_providers | WARNING | provider, attempt, error |

---

## Trace-Based Metrics

The `Tracer` produces metrics derivable from JSONL span data:

### Phase Duration

```python
# From trace spans
duration = span["end_time"] - span["start_time"]
# Tracked per phase, per task
```

### Validation Success Rate

```
success_rate = passed_verdicts / total_verdicts × 100%
```

Tracked per phase to identify which phases consistently fail validation.

### Debate Frequency

```
debate_rate = phases_with_debate / total_phase_transitions × 100%
```

High debate rate indicates the judge is too strict or output quality is consistently low.

### Recovery Escalation Distribution

```
level_0: 65%  (local retry)
level_1: 20%  (local replan)
level_2: 10%  (phase retry)
level_3:  4%  (structural replan)
level_4:  1%  (full recovery)
```

A healthy distribution concentrates at level 0-1. Frequent level 3-4 escalation indicates systemic issues.

---

## Health Monitoring

### Provider Health

```python
# Check all providers at startup
for name, provider in provider_pool.items():
    healthy = await provider.healthcheck()
    logger.info(f"Provider {name}: {'healthy' if healthy else 'UNHEALTHY'}")
```

### Store Health

```python
# SQLite WAL checkpoint
await store.checkpoint()  # PRAGMA wal_checkpoint(RESTART)
# Run every 100 write operations
```

### Index Health

```python
pipeline.stats
# {"indexed_count": 423, "skipped_count": 12, "total_files": 435, "total_symbols": 1847}
```

---

## Performance Considerations

| Component | Bottleneck | Impact | Mitigation |
|---|---|---|---|
| LLM inference | Model latency (5-60s per call) | Dominates total execution time | Fallback to smaller models |
| Full index | File I/O for large repos | 10-30s for 5000 files | Incremental indexing |
| Judge evaluation | LLM call + response parsing | Adds 5-15s per submission | Fail-open on timeout |
| Debate | 3 agents × 3 rounds of LLM calls | Adds 30-90s when triggered | Budget cap, debate optional |
| SQLite writes | BEGIN IMMEDIATE serialization | Negligible (<1ms per write) | WAL mode for concurrent reads |
| Checkpoint creation | JSON serialization + atomic write | Negligible (<10ms) | Only on accepted transitions |

---

## Implementation Status

| Component | Status |
|---|---|
| Structured JSON logging | **Implemented** — JSONFormatter, RotatingFileHandler |
| 17 logger categories | **Implemented** — all modules use get_logger() |
| Trace-based metrics | **Partial** — spans recorded, metric derivation not automated |
| Health monitoring | **Partial** — healthcheck methods exist, not scheduled |
| Performance benchmarking | **Not implemented** — no automated perf tests |
| Metrics export (Prometheus/etc) | **Not implemented** — logs only, no metrics endpoint |
