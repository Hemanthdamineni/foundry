# Related Systems

This reference is non-authoritative for MVP implementation.

Foundry's current implementation target is narrower than most autonomous-agent
research systems:

- single-process runtime;
- centralized orchestration;
- one feature workflow;
- deterministic submit pipeline;
- ToolExecutor/ToolGate governed validation;
- SQLite authority;
- latest-checkpoint resume.

Research ideas such as multi-agent coordination, distributed execution,
advanced replay, rollback, semantic memory, dashboards, and autonomous
self-improvement remain deferred until the core loop is operational.
