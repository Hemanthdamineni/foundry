# Tooling and Workflows Specification

> Authoritative spec for the MVP tool execution path and the single supported
> feature workflow.

## 1. Tooling Baseline

Current reality:

- ToolAdapter protocol exists.
- ToolExecutor exists as a module with timeout/retry/normalization behavior.
- ToolGate exists as a sequence evaluator.
- Several adapters exist as files.
- The runtime does not yet initialize ToolExecutor/ToolGate as part of the
  authoritative submit path.
- Coding and Testing can currently advance without tool validation.

MVP goal:

```
submit_output(Coding/Testing)
  -> ToolExecutor executes required validation adapters
  -> ToolGate evaluates results in deterministic order
  -> failed gate blocks phase advancement
  -> accepted gate result is persisted with phase output
```

## 2. MVP Tool Boundary

Only these tool capabilities are MVP:

| Capability | Purpose | Required |
|---|---|---|
| lint | Catch syntax/style errors | Yes |
| types | Catch type/interface errors where configured | Yes if registered and healthy; otherwise explicit unsupported/failed result |
| tests | Verify behavioral correctness | Yes |

Deferred from MVP:

- coverage
- security scanning
- benchmarks
- tree-sitter/code graph
- graphify
- GitHub PR operations
- Docker/sandboxed execution
- external MCP routing/fallback beyond local validation tools

## 3. ToolExecutor Contract

ToolExecutor must:

- own all validation command execution;
- enforce timeouts;
- normalize adapter output into a stable result shape;
- classify transient versus terminal execution failures;
- retry only transient execution failures within a hard ceiling;
- expose healthcheck status for required adapters.

MVP adapter payload:

```python
{
    "task_id": task_id,
    "phase": phase,
    "path": workspace_path,
    "timeout_s": 30,
}
```

`path` is the workspace root for MVP. Changed-file targeting is deferred.

ToolExecutor must not:

- decide phase transitions;
- mutate task state directly;
- bypass ToolGate;
- run optional/deferred tools in the MVP path.

## 4. ToolGate Contract

MVP gate order:

```
Coding:  lint -> types -> tests
Testing: lint -> types -> tests
```

All other phases have no tool gate in MVP.

Rules:

- Gate order is deterministic.
- First failing required gate stops the sequence.
- Missing required adapter fails closed unless the phase policy marks it optional.
- Gate output is persisted for accepted and rejected submissions.
- Gate failure keeps the task in the same phase.
- ToolGate receives ToolExecutor results; it does not run tools itself.
- Missing or unhealthy Mypy must be explicit unsupported/failed. It cannot be
  skipped and counted as a passing `types` gate.

Result mapping:

| ToolExecutor result | ToolGate result |
|---|---|
| exit `0` and `passed=True` | pass |
| nonzero exit or `passed=False` | fail |
| timeout/process execution error | transient execution failure |
| missing MVP adapter | fail/unsupported |
| malformed adapter output | terminal adapter contract failure |

## 5. Runtime Wiring Requirements

| Wiring Point | Required Behavior |
|---|---|
| `runtime/app.py` lifespan | Initialize MVP adapters, ToolExecutor, ToolGate |
| `SDLCAppContext` | Carry executor/gate into phase tools |
| `tools/phase.py::submit_output` | Invoke validation before accepted transition for Coding/Testing |
| `WriteQueue` payloads | Persist validation summary and rejected attempts |
| `sdlc_get_status` | Expose current phase, status, and latest failure enough for recovery |
| `sdlc_resume_task` | Explicit latest-checkpoint resume/reconciliation |

## 6. Feature Workflow Only

MVP supports only:

```
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
                         ^                 |
                         +-- Review -> Coding
```

Non-feature workflows are deferred until the feature loop is operational.

The existing `Chatting -> Done` edge is not a normal feature-task shortcut. It
must be disabled or guarded by explicit early-completion policy with persisted
reason and tests.

Until mode-specific graph selection is implemented, `sdlc_create_task` should
either:

- accept only `mode="feature"`, or
- clearly return an unsupported-mode error for other modes.

Accepting non-feature modes while always loading the feature graph is not
allowed for MVP readiness.

## 7. Workflow Acceptance Criteria

A feature workflow is operational only when:

- all phases can be reached through `submit_output`;
- invalid phase submissions are rejected;
- invalid Review branch targets are rejected;
- schema-invalid Specs/Planning/Review/Testing outputs are rejected;
- Coding/Testing cannot advance when lint/type/test validation fails;
- Coding/Testing can advance when validation passes;
- accepted phase output, validation result, and checkpoint are persisted;
- rejected attempts do not advance phase and remain visible;
- process restart can resume from latest accepted state.
- explicit `sdlc_resume_task(task_id)` can reconcile/restore latest checkpoint
  without silently overwriting SQLite/checkpoint mismatches.

## 8. Deferred Workflow Work

Deferred:

- bugfix, refactor, research, docs, feature harvesting workflows;
- workflow-specific budgets;
- workflow-specific model routing;
- workflow-specific gate policies beyond feature;
- context harvesting as a pre-spec phase;
- review debate as a mandatory workflow stage.

These may remain as graph files, but graph existence does not imply workflow
support.
