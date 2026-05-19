# Model Routing and Providers

Model routing is secondary to deterministic runtime wiring.

## MVP Requirement

MVP may use the existing provider/router path for optional judge behavior, but
the submit pipeline must remain deterministic around it:

- schema validation runs before judge;
- judge failure policy is explicit;
- judge/model transient failures are bounded if retried;
- judge rejection does not advance phase;
- ToolGate remains authoritative for Coding/Testing.

## Deferred

Advanced model selection, confidence analytics, fallback trees, provider
optimization, cost-aware routing, and workflow-specific routing are post-MVP.

Provider modules may exist, but model routing is not the measure of MVP
readiness. Runtime integration is.
