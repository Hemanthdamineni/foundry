# Design Philosophy

Foundry's implementation philosophy is now deliberately narrow:

> Build one deterministic, recoverable feature workflow before investing in any
> wider autonomy.

## Principles

1. Runtime wiring beats module inventory.
2. SQLite is the MVP task authority.
3. `submit_output` is the only accepted phase-mutation path.
4. Validation happens before phase advancement.
5. Tool execution is governed through ToolExecutor and ToolGate.
6. Checkpoints are recovery inputs, not a second state authority.
7. Deferred systems must not become hidden MVP dependencies.

## Deliberate Non-Goals

MVP does not include:

- multi-agent swarms or team coordination;
- distributed execution;
- vector memory;
- advanced replay;
- git rollback;
- dashboards and analytics;
- enterprise integrations;
- autonomous controller modes.

Existing files for these ideas are treated as scaffolded, conceptual, or
deferred until they are initialized by runtime, called by the authoritative path,
and covered by integration tests.

## Architecture Constraint

The runtime shape remains:

```text
User Workflows
  -> Orchestration Runtime
  -> Execution Runtime
  -> Tool Gateway
  -> MCP Ecosystem
```

Do not split this into additional orchestration layers before MVP completion.
