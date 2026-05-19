# Metrics and Telemetry

Observability is post-core-MVP except for minimal diagnostics required to debug
the authoritative submit path.

## MVP Requirement

The runtime should expose or log enough information to diagnose:

- submit stage reached;
- accept/reject decision;
- ToolExecutor command result;
- ToolGate result;
- checkpoint write result;
- retry count and last failure reason;
- recovery/resume outcome.

## Deferred

Dashboards, Prometheus export, analytics, benchmark reporting, confidence
analytics, and advanced telemetry aggregation are deferred. They must not block
the deterministic feature loop.

## Status Rule

Existing logging modules may be useful, but they are not production observability
until the submit path emits stage-level events and failure-path tests assert the
important records.
