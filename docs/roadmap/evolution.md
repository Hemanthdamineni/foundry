# Roadmap Evolution

> MVP-aligned roadmap reference. `ROADMAP.md` and `planning/` are authoritative.

## Current Focus

Build one operational deterministic feature workflow:

```
submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> persistence
  -> recovery
```

## MVP Phases

1. Single authoritative submit pipeline.
2. ToolExecutor and ToolGate enforcement.
3. Latest-checkpoint restore/resume and bounded retry.
4. End-to-end feature workflow proof.

## Deferred

- distributed execution;
- advanced replay;
- advanced rollback;
- dashboards;
- vector memory;
- multi-agent/team coordination;
- autonomous controller;
- enterprise integrations;
- advanced orchestration hierarchies;
- non-feature workflows.

These are not roadmap dependencies for MVP.
