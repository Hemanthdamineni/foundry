# Security and Trust Model

This is an MVP trust model for a local deterministic runtime. It does not claim
enterprise sandboxing, distributed governance, or advanced rollback guarantees.

## Trust Boundary

Foundry coordinates local tools through governed runtime paths:

```text
submit_output -> ToolExecutor -> ToolGate -> persistence/checkpoint
```

The main security property for MVP is preventing ungoverned validation and
ungoverned state mutation.

## Required Controls

| Control | MVP requirement |
|---|---|
| Phase mutation | only through `submit_output` |
| Tool execution | only through ToolExecutor for Coding/Testing gates |
| Gate acceptance | only through ToolGate |
| Task authority | SQLite, not JSON state files or checkpoints |
| Recovery | explicit latest-checkpoint resume only |
| Failure handling | no silent pass on missing required adapter |

## Out Of Scope For MVP

- security scanners as mandatory gates;
- network monitoring;
- container sandboxing;
- enterprise policy engines;
- git rollback safety;
- distributed authority or consensus;
- multi-agent governance;
- dashboard/audit UI.

These may be revisited only after the core deterministic loop is operational.

## Minimum Validation

Before MVP signoff:

- a direct ToolGate bypass attempt must fail or be impossible;
- missing Mypy must be explicit unsupported/failed, not a pass;
- rejected Coding/Testing output must not checkpoint accepted state;
- `sdlc_resume_task` must not silently overwrite SQLite/checkpoint mismatches.
