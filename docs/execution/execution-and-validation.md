# Execution and Validation

> MVP execution and validation contract.

## MCP Runtime

Foundry exposes the runtime through FastMCP tools. The MVP tools that matter for
the execution loop are:

- `sdlc_create_task`
- `sdlc_get_next_action`
- `sdlc_submit_output`
- `sdlc_get_status`
- `sdlc_cancel_task`

Other tools may exist but are not MVP validation authority.

## Submit Output Flow

`sdlc_submit_output` is where runtime authority converges:

```
load task
  -> phase/status guard
  -> budget/retry guard
  -> FSM target resolution
  -> schema validation
  -> optional judge
  -> ToolExecutor for Coding/Testing
  -> ToolGate for Coding/Testing
  -> accepted/rejected persistence
  -> checkpoint on accepted transition
```

## ToolExecutor Payload

MVP validation adapters receive a dict payload:

```python
{
    "task_id": task_id,
    "phase": phase,
    "path": workspace_path,
    "timeout_s": 30,
}
```

`path` is the workspace root for MVP. Changed-file targeting is post-MVP unless
already available without changing runtime boundaries.

## ToolGate Policy

MVP gate order:

```
Coding:  lint -> types -> tests
Testing: lint -> types -> tests
```

Tool mapping:

| Gate | Tool |
|---|---|
| lint | ruff |
| types | mypy |
| tests | pytest |

Mypy policy for MVP: required if registered and healthy; if unavailable in local
test/dev environments, the runtime must return an explicit unsupported/failed
gate result. Silent pass is not allowed.

## Result Mapping

ToolExecutor `ToolResult` maps to ToolGate `GateResult`:

| ToolResult | GateResult |
|---|---|
| `tool` | `tool` |
| configured gate name | `gate` |
| `passed` | `passed` |
| `output` | `output` |
| `errors` | `errors` |
| `duration_ms` | `duration_ms` |

The ToolGate decision, not ToolExecutor alone, controls code-phase acceptance.
