# Foundry Implementation TODO

> Authoritative execution checklist for the complete Foundry system.
> Phases P0-P4 are MVP (complete). Phases P5-P12 are post-MVP expansion.

Completion rule: do not mark a task done because a file exists. Mark it done
only when the runtime initializes it, the authoritative path calls it, it can
affect accept/reject behavior where relevant, required state persists, and tests
cover success and failure behavior.

Authoritative runtime path:

```text
User Workflow
  -> submit_output
  -> ToolExecutor
  -> ToolGate
  -> validation
  -> checkpoint
  -> SQLite persistence
  -> sdlc_resume_task / recovery
```

## Phase 0: Baseline Enforcement (COMPLETE)

### P0-01: Establish Execution Plan Index

- [x] Confirm `planning/execution/PHASE-0.md` exists and defines baseline enforcement.
- [x] Confirm `planning/execution/PHASE-1.md` exists and defines the single submit pipeline.
- [x] Confirm `planning/execution/PHASE-2.md` exists and defines ToolExecutor/ToolGate enforcement.
- [x] Confirm `planning/execution/PHASE-3.md` exists and defines checkpoint restore and bounded recovery.
- [x] Confirm `planning/execution/PHASE-4.md` exists and defines MVP end-to-end proof.
- [x] Confirm `planning/execution/MVP-COMPLETION.md` exists and defines release evidence.
- [x] Verify every phase task references concrete files/modules.
- [x] Verify every implementation task has runtime integration points.
- [x] Verify no phase depends on rollback, replay, dashboard, advanced memory, or team coordination.
- [x] Verify execution planning points back to `planning/MASTER-ROADMAP.md`.

All planning files verified: `planning/execution/PHASE-0.md` through `PHASE-4.md`,
`MVP-COMPLETION.md`, `MASTER-ROADMAP.md`, `TOOLING-AND-WORKFLOWS-SPEC.md`,
`DEPENDENCY-GRAPH.md`, `QUALITY-AND-VALIDATION.md`, `RUNTIME-SPEC.md`.

### P0-02: Enforce MVP Vocabulary

- [x] Scan `planning/` for "fully implemented", "all implemented", "production ready", and similar overclaims.
- [x] Replace file-existence completion language with runtime integration status.
- [x] Use only: `file exists`, `scaffolded`, `partially wired`, `operationally integrated`, `production-ready`, `deferred`, `non-operational concept`.
- [x] Confirm `planning/MASTER-ROADMAP.md` does not mark ToolExecutor or ToolGate operational until submit path wiring exists.
- [x] Confirm rollback, replay, dashboards, memory, and team coordination are explicitly deferred.
- [x] Confirm production-ready is not used as an MVP status.

Planning docs use runtime integration language. `MASTER-ROADMAP.md` marks ToolExecutor/ToolGate
as deferred until submit path wiring. All deferred systems explicitly documented.

### P0-03: Lock Feature-Only Scope

- [x] Confirm `feature` is the only MVP workflow in `planning/TOOLING-AND-WORKFLOWS-SPEC.md`.
- [x] Confirm Phase 1 includes explicit non-feature mode rejection or unsupported response.
- [x] Confirm no Phase 0-4 task requires bugfix/refactor/research/docs graph execution.
- [x] Confirm workflow-specific budgets are deferred.
- [x] Confirm workflow-specific model routing is deferred.
- [x] Confirm `sdlc/graphs/feature.yaml` remains the only executable MVP graph.

`TOOLING-AND-WORKFLOWS-SPEC.md` confirms `feature` as only MVP workflow.
`app.py:342` enforces `mode != "feature"` rejection. All non-feature workflows deferred.

## Phase 1: Single Submit Pipeline (COMPLETE)

### P1-01: Stage the Submit Pipeline

All items implemented and verified in `sdlc/runtime/tools/phase.py:283-611`.
Pipeline stages in order: load from SQLite → reject missing → reject terminal status →
reject phase mismatch → guard Chatting->Done → budget check → FSM resolution →
schema validation → judge → ToolGate → phase mutation + checkpoint.
Tests: `TestTaskLifecycle` (missing/done/cancelled/stalled rejection, phase mismatch,
invalid target, Chatting->Done guard).

### P1-02: Make Schema Validation Explicit

All items implemented. `validate_phase_output` at `phase.py:347` runs after FSM resolution
and before judge evaluation. Schema failure returns early, skipping judge, debate, and gates.
Tests: `TestSchemaValidation` (5 tests including `test_judge_skipped_on_schema_failure`).

### P1-03: Persist Rejected Attempts Consistently

All items implemented. Schema/judge/gate rejections persisted as `PhaseRecord(status=REJECTED)`.
`get_status` exposes history with rejected records. Tests: `test_invalid_specs_visible_after_status`,
`test_rejected_attempt_survives_reload`.

### P1-04: Enforce Feature-Only Mode Truth

All items implemented. `app.py:342-347` enforces `mode != "feature"` rejection.
Tests: `TestModeEnforcement` (feature accepted, bugfix/refactor rejected).

## Phase 2: ToolExecutor and ToolGate Enforcement (COMPLETE)

### P2-01: Initialize MVP ToolExecutor

All items implemented. `app.py:245-248`: ToolExecutor with RuffAdapter, MypyAdapter, PytestAdapter.
Health checks at lines 250-256. Payload standardized at `phase.py:214-219`.
Tests: `TestToolGates` (registration, payload shape, missing mypy).

### P2-02: Initialize MVP ToolGate

All items implemented. `app.py:258-266`: ToolGate with deterministic gate order.
Phase exceptions configured. `_requires_tool_gate()` at `phase.py:185-186`.
`_map_to_gate_result` at `phase.py:189-203`. Tests: `TestToolGates` (gate order, result mapping).

### P2-03: Execute Validation Before Coding/Testing Advancement

All items implemented. Gate execution at `phase.py:430-512` runs after schema/judge,
before phase mutation. Fail-fast on first failure. Gate summary in response.
Tests: `TestToolGates` (failing lint/types/tests block, passing validation advances).

### P2-04: Persist Validation Results

All items implemented. Gate summary shape in response. Rejected/accepted summaries persisted.
`get_status` exposes validation results. Tests: `test_validation_failure_visible_after_reload`,
`test_validation_pass_summary_visible_after_accepted`.

## Phase 3: Checkpoint Restore and Bounded Recovery (COMPLETE)

### P3-01: Define Latest Checkpoint Resume Path

All items implemented. `resume_task()` at `task.py:113-199`. `sdlc_resume_task` MCP handler.
Tests: `TestResumeTask` (5 tests: consistent state, missing checkpoint, missing task restore,
corrupt checkpoint, phase mismatch).

### P3-02: Persist Minimal Retry State

All items implemented. `retry_count`, `last_failure_reason`, `last_failure_type` on Task model.
Transient/timeout → increment; permanent/not_found → no increment. Accepted transitions reset.
Tests: `test_task_retry_metadata_defaults`, `test_task_retry_metadata_roundtrip`.

### P3-03: Implement Bounded Transient Retry

All items implemented. Retry loop at `phase.py:433-512`. `MAX_GATE_RETRY_CEILING=3`.
Exponential backoff. Ceiling exhaustion → STALLED. Tests: `TestBoundedTransientRetry`,
`TestRecoveryRetryE2E`.

### P3-04: Restart/Resume Integration Test

All items implemented. `TestRestartResume` (2 tests) with isolated runtime paths.
No live LLM dependency. Tests: `test_restart_resume_preserves_phase_and_history`,
`test_restart_resume_checkpoint_sqlite_consistency`.

## Phase 4: MVP End-to-End Feature Workflow (COMPLETE)

### P4-01: Build Deterministic Feature Workflow E2E Test

All items implemented. `TestFeatureWorkflowE2E.test_feature_workflow_reaches_done`.
Full 6-phase workflow. Verifies checkpoints, gate summaries, final status=done.

### P4-02: Validate ToolGate Failure Path End-to-End

All items implemented. `TestGateFailureE2E` (2 tests). Coding and Testing gate failures
preserve phase, persist rejection, no checkpoint written, retry_count=0.

### P4-03: Validate Recovery and Retry End-to-End

All items implemented. `TestRecoveryRetryE2E` (3 tests). Transient recovery, exhaustion,
restart persistence. `SDLC_TOOL_EXECUTOR_MAX_RETRIES` and `SDLC_INJECT_TRANSIENT_TOOL_FAILURES`
env vars for test determinism.

### P4-04: Final MVP Runtime Audit

All items verified. 421 tests pass. All 15 completion gates passed.
All 11 runtime invariants verified. `planning/execution/MVP-COMPLETION.md` updated.

## Phase 5: Post-MVP Hardening

Goal: production readiness for the feature workflow.

### P5-01: Stage-Level Tracing

- [ ] Add trace spans for all 9 submit pipeline stages.
- [ ] Emit trace ID with every submit response.
- [ ] Add trace viewer CLI (`python -m sdlc.cli.trace`).
- [ ] Persist traces to `data/traces/` as JSONL.
- [ ] Add trace correlation across tool executions.
- [ ] Add trace-based debugging for stuck tasks.
- [ ] Add integration test: trace emitted on accepted transition.
- [ ] Add integration test: trace emitted on rejected transition.
- [ ] Add integration test: trace emitted on retry attempt.
- [ ] Add integration test: trace emitted on recovery/resume.

### P5-02: Adapter Healthcheck Hardening

- [ ] Add periodic healthcheck polling for registered adapters.
- [ ] Expose adapter health via `sdlc_get_status` response.
- [ ] Add `sdlc_healthcheck` MCP tool for adapter health.
- [ ] Add healthcheck-based gate skipping for unhealthy optional adapters.
- [ ] Add healthcheck-based fail-closed for required adapters.
- [ ] Add integration test: healthy adapter passes gate.
- [ ] Add integration test: unhealthy required adapter fails gate.
- [ ] Add integration test: unhealthy optional adapter skipped.
- [ ] Add integration test: healthcheck recovers after adapter restart.

### P5-03: Judge Fail-Open/Fail-Closed Policy

- [ ] Add `judge_fail_policy` config: `open` (default) or `closed`.
- [ ] When `closed`: judge rejection blocks phase advancement, same as ToolGate failure.
- [ ] When `open`: judge rejection logs warning but allows advancement.
- [ ] Persist judge verdict in PhaseRecord regardless of policy.
- [ ] Add `SDLC_JUDGE_FAIL_POLICY` env var.
- [ ] Add integration test: judge rejection blocks with fail-closed.
- [ ] Add integration test: judge rejection allows with fail-open.
- [ ] Add integration test: judge verdict persisted in both policies.

### P5-04: SQLite Backup and Compaction

- [ ] Add automatic SQLite backup on task completion.
- [ ] Add `sdlc_backup` CLI command for manual backup.
- [ ] Add SQLite VACUUM compaction on configurable schedule.
- [ ] Add backup rotation (keep last N backups).
- [ ] Add backup restore CLI (`python -m sdlc.cli.restore`).
- [ ] Add integration test: backup created on task done.
- [ ] Add integration test: restore recovers from backup.
- [ ] Add integration test: compaction reduces database size.

### P5-05: Additional Workflow Templates

- [ ] Wire `bugfix` workflow: Triage -> Diagnosis -> Fix -> Verify -> Done.
- [ ] Wire `refactor` workflow: Analysis -> Plan -> Refactor -> Verify -> Done.
- [ ] Wire `research` workflow: Question -> Explore -> Synthesize -> Report -> Done.
- [ ] Wire `docs` workflow: Audit -> Plan -> Write -> Review -> Done.
- [ ] Add workflow-specific phase schemas.
- [ ] Add workflow-specific gate policies.
- [ ] Add workflow-specific model routing.
- [ ] Add integration test: bugfix workflow reaches Done.
- [ ] Add integration test: refactor workflow reaches Done.
- [ ] Add integration test: research workflow reaches Done.
- [ ] Add integration test: docs workflow reaches Done.
- [ ] Add integration test: non-feature mode accepted for wired workflows.

### P5-06: Changed-File Targeting

- [ ] Add file change detection to ToolExecutor payload.
- [ ] Run lint/types/tests only on changed files for Coding phase.
- [ ] Run tests only on affected modules for Testing phase.
- [ ] Add `--all-files` flag to override changed-file targeting.
- [ ] Add integration test: changed-file lint passes.
- [ ] Add integration test: changed-file types passes.
- [ ] Add integration test: changed-file tests pass.
- [ ] Add integration test: `--all-files` runs full suite.

### P5-07: Production Security Hardening

- [ ] Add sandbox config for tool execution (restricted paths).
- [ ] Add secret scanning gate (optional, configurable).
- [ ] Add path traversal protection in tool adapters.
- [ ] Add file permission governance for workspace writes.
- [ ] Add binary guard (prevent binary file modifications).
- [ ] Add coverage gate (optional, configurable threshold).
- [ ] Add security scanning gate (bandit/semgrep, optional).
- [ ] Add integration test: sandbox blocks path traversal.
- [ ] Add integration test: secret scanner detects leaked key.
- [ ] Add integration test: binary guard blocks binary write.

## Phase 6: Memory and Context Systems

Goal: persistent knowledge across tasks and sessions.

### P6-01: Repository Indexing

- [ ] Implement `IndexPipeline` for workspace file indexing.
- [ ] Add Tree-sitter symbol extraction for Python/TypeScript.
- [ ] Build dependency graph from import analysis.
- [ ] Add incremental indexing (only changed files).
- [ ] Add `FileIndex` model: path, language, symbols, imports, mtime, sha256.
- [ ] Add `CodeSymbol` model: name, kind, file_path, line range, docstring.
- [ ] Add `ImportInfo` model: source, alias, file_path, line.
- [ ] Add `DependencyGraph` model: files, import_edges, dependents.
- [ ] Add `ContextChunk` model: file_path, content, relevance_score.
- [ ] Add `IndexConfig` settings: enabled, max_files, patterns, incremental.
- [ ] Add `python -m sdlc.cli.index` for manual indexing.
- [ ] Add `sdlc_index` MCP tool for on-demand indexing.
- [ ] Add integration test: index captures file symbols.
- [ ] Add integration test: incremental index detects changes.
- [ ] Add integration test: dependency graph resolves imports.

### P6-02: Context Builder

- [ ] Implement context harvester that selects relevant files for phase.
- [ ] Add relevance scoring based on symbol references and imports.
- [ ] Add context budget (max tokens per phase).
- [ ] Add context injection into phase prompts.
- [ ] Add `ContextBuilder` component in `sdlc/engine/`.
- [ ] Add integration test: context includes referenced files.
- [ ] Add integration test: context respects token budget.
- [ ] Add integration test: context updates after file changes.

### P6-03: Vector Memory (Embedding-Based)

- [ ] Add embedding model integration (local or API).
- [ ] Implement vector store for phase outputs and decisions.
- [ ] Add semantic search across task history.
- [ ] Add cross-task memory retrieval.
- [ ] Add `Engram` model: engram_id, task_id, phase, content, tags, importance.
- [ ] Add memory garbage collector (evict low-importance engrams).
- [ ] Add memory indexer for new engrams.
- [ ] Add memory validator for retrieval quality.
- [ ] Add integration test: vector search finds relevant past decisions.
- [ ] Add integration test: memory retrieval improves phase output.
- [ ] Add integration test: garbage collector evicts old engrams.

### P6-04: Semantic Memory

- [ ] Implement semantic memory for project patterns and conventions.
- [ ] Add pattern extraction from accepted code changes.
- [ ] Add pattern injection into Coding phase prompts.
- [ ] Add pattern validation against project style.
- [ ] Add `PatternMemory` component.
- [ ] Add integration test: pattern extracted from accepted change.
- [ ] Add integration test: pattern injected into coding prompt.
- [ ] Add integration test: pattern validated against style.

### P6-05: Episodic Memory

- [ ] Implement episodic memory for task execution traces.
- [ ] Add episode recording for each phase transition.
- [ ] Add episode replay for debugging and learning.
- [ ] Add episode search by phase, outcome, or error type.
- [ ] Add `EpisodeMemory` component.
- [ ] Add integration test: episode recorded on phase transition.
- [ ] Add integration test: episode search returns relevant traces.
- [ ] Add integration test: episode replay reproduces execution.

### P6-06: Error Memory and Failure Patterns

- [ ] Implement error memory for tracking failure patterns.
- [ ] Add failure pattern extraction from rejected submissions.
- [ ] Add failure pattern avoidance in future submissions.
- [ ] Add `ErrorMemory` component.
- [ ] Add integration test: failure pattern extracted from rejection.
- [ ] Add integration test: failure pattern prevents repeat error.
- [ ] Add integration test: error memory persists across restarts.

### P6-07: Working Memory

- [ ] Implement working memory for active task context.
- [ ] Add working memory injection into phase prompts.
- [ ] Add working memory update on phase transitions.
- [ ] Add working memory cleanup on task completion.
- [ ] Add `WorkingMemory` component.
- [ ] Add integration test: working memory contains active context.
- [ ] Add integration test: working memory updates on transition.
- [ ] Add integration test: working memory cleaned on completion.

### P6-08: Project Memory

- [ ] Implement project-level memory shared across tasks.
- [ ] Add project memory for architecture decisions.
- [ ] Add project memory for API contracts.
- [ ] Add project memory for database schemas.
- [ ] Add `ProjectMemory` component.
- [ ] Add integration test: project memory shared across tasks.
- [ ] Add integration test: project memory persists across restarts.
- [ ] Add integration test: project memory updated on task completion.

### P6-09: Memory Injection into Phase Context

- [ ] Wire all memory systems into phase prompt assembly.
- [ ] Add memory relevance scoring for prompt injection.
- [ ] Add memory budget (max tokens from memory per phase).
- [ ] Add memory injection order: working > project > semantic > episodic > vector.
- [ ] Add integration test: memory injected into phase prompt.
- [ ] Add integration test: memory relevance scoring works.
- [ ] Add integration test: memory budget respected.

## Phase 7: Observability and Telemetry

Goal: full visibility into system behavior.

### P7-01: Metrics Export

- [ ] Add Prometheus metrics endpoint.
- [ ] Export task creation/completion rates.
- [ ] Export phase transition latencies.
- [ ] Export ToolExecutor execution times.
- [ ] Export ToolGate pass/fail rates.
- [ ] Export retry counts and exhaustion rates.
- [ ] Export memory usage and GC stats.
- [ ] Export SQLite query latencies.
- [ ] Add integration test: metrics endpoint returns data.
- [ ] Add integration test: task metrics increment correctly.

### P7-02: Dashboard

- [ ] Build web dashboard for task monitoring.
- [ ] Add task list with status and phase.
- [ ] Add task detail view with phase history.
- [ ] Add phase transition timeline.
- [ ] Add ToolGate result visualization.
- [ ] Add retry and failure visualization.
- [ ] Add memory usage and performance charts.
- [ ] Add real-time updates via WebSocket.
- [ ] Add integration test: dashboard loads task list.
- [ ] Add integration test: dashboard shows task details.

### P7-03: Analytics

- [ ] Add confidence analytics for judge verdicts.
- [ ] Add phase duration analytics.
- [ ] Add retry pattern analytics.
- [ ] Add failure root cause analytics.
- [ ] Add cross-run comparison analytics.
- [ ] Add replay analytics for historical runs.
- [ ] Add `AnalyticsEngine` component.
- [ ] Add integration test: analytics computed correctly.
- [ ] Add integration test: cross-run comparison works.

### P7-04: Distributed Tracing

- [ ] Add OpenTelemetry integration.
- [ ] Add trace context propagation across tool calls.
- [ ] Add trace export to Jaeger/Zipkin.
- [ ] Add trace-based performance profiling.
- [ ] Add trace-based error investigation.
- [ ] Add integration test: trace spans emitted.
- [ ] Add integration test: trace context propagates.
- [ ] Add integration test: trace exported to backend.

### P7-05: Alerting

- [ ] Add alerting for task failures.
- [ ] Add alerting for retry exhaustion.
- [ ] Add alerting for adapter health failures.
- [ ] Add alerting for SQLite errors.
- [ ] Add alerting for memory pressure.
- [ ] Add alerting for budget exhaustion.
- [ ] Add `AlertingEngine` component.
- [ ] Add integration test: alert triggered on failure.
- [ ] Add integration test: alert triggered on exhaustion.

## Phase 8: Orchestration and Coordination

Goal: multi-agent debate and consensus.

### P8-01: Debate Engine

- [ ] Implement multi-agent debate for phase review.
- [ ] Add debate agents: proposer, critic, architect, consensus.
- [ ] Add debate round management.
- [ ] Add debate transcript recording.
- [ ] Add consensus result computation.
- [ ] Add minority report for dissenting opinions.
- [ ] Add `DebateEngine` component in `sdlc/engine/`.
- [ ] Add `DebateAgentConfig` model.
- [ ] Add `DebateRound` model.
- [ ] Add `DebateTranscript` model.
- [ ] Add `ConsensusResult` model.
- [ ] Add `MinorityReport` model.
- [ ] Add integration test: debate runs for phase review.
- [ ] Add integration test: consensus reached.
- [ ] Add integration test: minority report recorded.

### P8-02: Adaptive Agent Selection

- [ ] Implement agent selection based on phase and context.
- [ ] Add agent capability registry.
- [ ] Add agent performance tracking.
- [ ] Add agent selection optimization.
- [ ] Add `AgentRegistry` component.
- [ ] Add integration test: agent selected for phase.
- [ ] Add integration test: agent performance tracked.

### P8-03: Confidence Analytics

- [ ] Add confidence scoring for agent outputs.
- [ ] Add confidence-based routing decisions.
- [ ] Add confidence threshold configuration.
- [ ] Add confidence analytics dashboard.
- [ ] Add `ConfidenceEngine` component.
- [ ] Add integration test: confidence scored correctly.
- [ ] Add integration test: confidence-based routing works.

### P8-04: Consensus Optimization

- [ ] Implement consensus optimization for debate outcomes.
- [ ] Add consensus quality metrics.
- [ ] Add consensus speed optimization.
- [ ] Add consensus fallback strategies.
- [ ] Add `ConsensusOptimizer` component.
- [ ] Add integration test: consensus optimized.
- [ ] Add integration test: consensus fallback works.

### P8-05: Multi-Agent Team Coordination

- [ ] Implement team coordination for complex tasks.
- [ ] Add task decomposition across agents.
- [ ] Add inter-agent communication.
- [ ] Add task dependency resolution.
- [ ] Add `TeamCoordinator` component.
- [ ] Add integration test: task decomposed across agents.
- [ ] Add integration test: inter-agent communication works.

## Phase 9: Advanced State Management

Goal: versioned state, rollback, and replay.

### P9-01: Versioned Checkpoint Chains

- [ ] Implement `EnhancedCheckpointManager` for versioned checkpoints.
- [ ] Add checkpoint chain for each task.
- [ ] Add named restore points.
- [ ] Add checkpoint diff between versions.
- [ ] Add checkpoint compression for old versions.
- [ ] Add integration test: checkpoint chain created.
- [ ] Add integration test: named restore point works.
- [ ] Add integration test: checkpoint diff computed.

### P9-02: Git Rollback

- [ ] Implement `RollbackManager` for git-based rollback.
- [ ] Add workspace snapshot before coding phase.
- [ ] Add git commit on accepted code changes.
- [ ] Add rollback to any checkpoint.
- [ ] Add rollback diff preview.
- [ ] Add rollback safety checks.
- [ ] Add integration test: workspace snapshot created.
- [ ] Add integration test: git commit on accepted change.
- [ ] Add integration test: rollback to checkpoint works.

### P9-03: Deterministic Replay

- [ ] Implement `ReplayEngine` for deterministic replay.
- [ ] Add replay recording for all tool calls.
- [ ] Add replay playback with same inputs.
- [ ] Add replay comparison with original run.
- [ ] Add replay-based debugging.
- [ ] Add `ReplayEngine` component.
- [ ] Add integration test: replay recorded.
- [ ] Add integration test: replay playback matches original.
- [ ] Add integration test: replay comparison shows differences.

### P9-04: Prompt Registry and Rollback

- [ ] Implement prompt registry with versioning.
- [ ] Add prompt rollback to previous versions.
- [ ] Add prompt compatibility matrices.
- [ ] Add prompt-replay guarantees.
- [ ] Add `PromptRegistry` component.
- [ ] Add integration test: prompt versioned.
- [ ] Add integration test: prompt rollback works.
- [ ] Add integration test: prompt compatibility checked.

### P9-05: Workspace State Replay

- [ ] Implement workspace state replay for historical runs.
- [ ] Add workspace snapshot on phase transitions.
- [ ] Add workspace diff between snapshots.
- [ ] Add workspace replay to any point.
- [ ] Add `WorkspaceReplay` component.
- [ ] Add integration test: workspace snapshot created.
- [ ] Add integration test: workspace replay works.

### P9-06: Regression Comparison

- [ ] Implement regression comparison between historical runs.
- [ ] Add run comparison by task, phase, or output.
- [ ] Add regression detection.
- [ ] Add regression report generation.
- [ ] Add `RegressionEngine` component.
- [ ] Add integration test: regression comparison works.
- [ ] Add integration test: regression detected.

## Phase 10: Advanced Tooling and MCP Ecosystem

Goal: expand tool capabilities and MCP integrations.

### P10-01: Coverage Gate

- [ ] Add coverage gate for Testing phase.
- [ ] Add coverage threshold configuration.
- [ ] Add coverage report generation.
- [ ] Add coverage trend tracking.
- [ ] Add integration test: coverage gate passes.
- [ ] Add integration test: coverage gate fails below threshold.

### P10-02: Security Scanning Gate

- [ ] Add security scanning gate (bandit/semgrep).
- [ ] Add security scan configuration.
- [ ] Add security scan report generation.
- [ ] Add security trend tracking.
- [ ] Add integration test: security scan passes.
- [ ] Add integration test: security scan detects vulnerability.

### P10-03: Benchmark Gate

- [ ] Add benchmark gate for performance testing.
- [ ] Add benchmark threshold configuration.
- [ ] Add benchmark report generation.
- [ ] Add benchmark trend tracking.
- [ ] Add integration test: benchmark gate passes.
- [ ] Add integration test: benchmark gate fails below threshold.

### P10-04: Code Graph and Tree-sitter

- [ ] Implement code graph from Tree-sitter parsing.
- [ ] Add symbol reference tracking.
- [ ] Add call graph generation.
- [ ] Add impact analysis for code changes.
- [ ] Add `CodeGraph` component.
- [ ] Add integration test: code graph built.
- [ ] Add integration test: symbol references tracked.
- [ ] Add integration test: impact analysis works.

### P10-05: GitHub Integration

- [ ] Add GitHub PR operations MCP tool.
- [ ] Add PR creation from completed tasks.
- [ ] Add PR review from Review phase.
- [ ] Add PR merge from Done phase.
- [ ] Add GitHub issue linking.
- [ ] Add `GitHubMCP` component.
- [ ] Add integration test: PR created from task.
- [ ] Add integration test: PR review from Review phase.

### P10-06: Docker/Sandboxed Execution

- [ ] Add Docker-based tool execution.
- [ ] Add sandbox isolation for tool adapters.
- [ ] Add sandbox configuration per tool.
- [ ] Add sandbox resource limits.
- [ ] Add `SandboxExecutor` component.
- [ ] Add integration test: tool runs in sandbox.
- [ ] Add integration test: sandbox isolation works.

### P10-07: External MCP Routing

- [ ] Add external MCP server routing.
- [ ] Add MCP fallback chain.
- [ ] Add MCP health monitoring.
- [ ] Add MCP capability discovery.
- [ ] Add `MCPRouter` component.
- [ ] Add integration test: external MCP routed.
- [ ] Add integration test: MCP fallback works.

## Phase 11: Budget and Resource Control

Goal: fine-grained resource management.

### P11-01: Token-Accurate Accounting

- [ ] Add token counting for all LLM calls.
- [ ] Add token budget tracking per task.
- [ ] Add token budget tracking per phase.
- [ ] Add token budget alerts.
- [ ] Add `TokenAccountant` component.
- [ ] Add integration test: tokens counted correctly.
- [ ] Add integration test: token budget tracked.

### P11-02: Debate Budgets

- [ ] Add budget control for debate rounds.
- [ ] Add debate token budget.
- [ ] Add debate round budget.
- [ ] Add debate budget exhaustion handling.
- [ ] Add integration test: debate budget enforced.
- [ ] Add integration test: debate budget exhaustion handled.

### P11-03: Workflow-Specific Budgets

- [ ] Add budget configuration per workflow.
- [ ] Add workflow-specific token budgets.
- [ ] Add workflow-specific time budgets.
- [ ] Add workflow-specific retry budgets.
- [ ] Add integration test: workflow budget enforced.
- [ ] Add integration test: workflow budget exhausted.

### P11-04: Cost Optimization

- [ ] Add cost tracking for all LLM calls.
- [ ] Add cost optimization recommendations.
- [ ] Add cost-based model routing.
- [ ] Add cost budget alerts.
- [ ] Add `CostOptimizer` component.
- [ ] Add integration test: cost tracked correctly.
- [ ] Add integration test: cost optimization works.

### P11-05: Provider-Aware Routing

- [ ] Add provider-aware model routing.
- [ ] Add provider fallback chain.
- [ ] Add provider health monitoring.
- [ ] Add provider capability matching.
- [ ] Add `ProviderRouter` component.
- [ ] Add integration test: provider routing works.
- [ ] Add integration test: provider fallback works.

### P11-06: BudgetController on Submit Path

- [ ] Add budget check to submit pipeline.
- [ ] Add budget exhaustion handling.
- [ ] Add budget warning on approach.
- [ ] Add budget override for emergency.
- [ ] Add integration test: budget checked on submit.
- [ ] Add integration test: budget exhaustion handled.

## Phase 12: Deployment and Infrastructure

Goal: production deployment and scaling.

### P12-01: Docker Support

- [ ] Create production Dockerfile.
- [ ] Add docker-compose for full stack.
- [ ] Add Docker health checks.
- [ ] Add Docker volume mounts for data.
- [ ] Add integration test: Docker build succeeds.
- [ ] Add integration test: Docker container starts.

### P12-02: Authentication and Authorization

- [ ] Add MCP transport authentication.
- [ ] Add role-based access control.
- [ ] Add API key management.
- [ ] Add OAuth integration.
- [ ] Add `AuthMiddleware` component.
- [ ] Add integration test: authentication required.
- [ ] Add integration test: authorization enforced.

### P12-03: Kubernetes Deployment

- [ ] Add Kubernetes manifests.
- [ ] Add Helm chart.
- [ ] Add Kubernetes health checks.
- [ ] Add Kubernetes scaling configuration.
- [ ] Add integration test: Kubernetes deployment works.
- [ ] Add integration test: Kubernetes scaling works.

### P12-04: CI/CD Pipeline

- [ ] Add GitHub Actions workflow.
- [ ] Add automated testing on PR.
- [ ] Add automated linting on PR.
- [ ] Add automated type checking on PR.
- [ ] Add automated Docker build on merge.
- [ ] Add integration test: CI pipeline runs.
- [ ] Add integration test: CD pipeline deploys.

### P12-05: Monitoring and Alerting

- [ ] Add Prometheus monitoring.
- [ ] Add Grafana dashboards.
- [ ] Add alerting rules.
- [ ] Add incident response procedures.
- [ ] Add integration test: monitoring works.
- [ ] Add integration test: alerting triggers.

### P12-06: Database Backup and Recovery

- [ ] Add automated SQLite backup.
- [ ] Add backup rotation.
- [ ] Add backup restore procedures.
- [ ] Add disaster recovery plan.
- [ ] Add integration test: backup created.
- [ ] Add integration test: backup restored.

## MVP Completion Evidence

- [x] Feature-only workflow enforced.
- [x] Submit pipeline staged.
- [x] Schema validation explicit.
- [x] ToolExecutor wired.
- [x] ToolExecutor payload stable.
- [x] ToolGate wired.
- [x] ToolGate mapping stable.
- [x] Mypy policy explicit.
- [x] `Chatting -> Done` shortcut governed.
- [x] Rejected attempts persisted.
- [x] Checkpoint write correct.
- [x] `sdlc_resume_task` works.
- [x] Retry bounded.
- [x] SQLite authority preserved.
- [x] Deferred systems absent from MVP path.

MVP is complete. 421 tests pass. All 15 completion gates passed.
All 11 runtime invariants verified.
`planning/execution/MVP-COMPLETION.md` has full evidence.

## Post-MVP Priority Order

1. **P5: Hardening** — Production readiness for feature workflow
2. **P6: Memory** — Persistent knowledge across tasks
3. **P7: Observability** — Full system visibility
4. **P8: Orchestration** — Multi-agent debate and consensus
5. **P9: State** — Versioned state, rollback, replay
6. **P10: Tooling** — Expanded tool capabilities
7. **P11: Budget** — Fine-grained resource control
8. **P12: Deployment** — Production deployment and scaling
