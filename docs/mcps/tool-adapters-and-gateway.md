# Tool Adapters and Gateway

This document defines the MVP ToolExecutor and ToolGate contract. It replaces
module-existence claims with runtime-integration requirements.

## Runtime Role

```text
submit_output
  -> ToolExecutor executes configured adapter commands
  -> ToolGate evaluates normalized results
  -> submit_output accepts/rejects phase transition
```

ToolExecutor executes. ToolGate decides gate pass/fail. Neither component
mutates task phase directly.

## MVP Adapters

Only these adapters are required for MVP:

| Gate | Adapter | Required for |
|---|---|---|
| `lint` | `RuffAdapter` | Coding, Testing |
| `types` | `MypyAdapter` | Coding, Testing |
| `tests` | `PytestAdapter` | Coding, Testing |

Security scanners, coverage, benchmarks, tree-sitter, graph tools, memory
adapters, and external workflow integrations are deferred. Existing files do not
make those systems operational.

## ToolExecutor Payload

Every MVP adapter receives the same payload shape:

```python
{
    "task_id": task_id,
    "phase": phase,
    "path": workspace_path,
    "timeout_s": 30,
}
```

`path` is the workspace root for MVP. Per-file targeting and changed-file
optimization are post-MVP.

## ToolGate Order

Coding and Testing use deterministic fail-fast ordering:

```text
lint -> types -> tests
```

Non-code phases do not run ToolGate in MVP.

## Health Policy

Adapter healthchecks are useful for diagnostics, but they must not create silent
passes.

- Healthy registered adapter: execute normally.
- Missing/unhealthy optional post-MVP adapter: ignored because it is not in MVP.
- Missing/unhealthy MVP adapter: return explicit unsupported/failed gate result.

Mypy is required if registered and healthy. If unavailable in a local test/dev
environment, the runtime must surface explicit unsupported/failed result. It
must not skip `types` and mark the gate successful.

## Result Mapping

ToolExecutor adapter results normalize into ToolGate results:

| ToolExecutor result | ToolGate result |
|---|---|
| process exit `0` and adapter `passed=True` | gate passed |
| nonzero exit or `passed=False` | gate failed |
| timeout/process execution error | transient ToolExecutor failure |
| missing required adapter | gate failed/unsupported |
| malformed adapter output | terminal adapter contract failure |

ToolGate failure blocks Coding/Testing advancement and may persist rejection
history. It must not write an accepted checkpoint.

## Implementation Status Language

Use these terms consistently:

| Term | Meaning |
|---|---|
| file exists | Module is present only |
| scaffolded | API/code exists but is not in submit path |
| partially wired | Runtime initializes or calls part of it |
| operationally integrated | Submit path depends on it and tests cover it |
| production-ready | Operational plus failure-tested, observable, and bounded |

Current MVP status: ToolExecutor and ToolGate are scaffolded until initialized by
app lifespan, passed into `submit_output`, and proven by integration tests.
