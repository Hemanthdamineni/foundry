# 1. Public Capabilities (User-Facing)

These are the workflows users directly invoke.

Users should see:

* workflows
* goals
* engineering outcomes

Users should NOT see:

* orchestration internals
* validators
* retries
* debate systems
* memory routing
* runtime governance

---

# Engineering & Build Capabilities

| Capability  | Responsibility                       | Inputs                               | Outputs                         | Internally Uses                       | Critical Guarantees             |
| ----------- | ------------------------------------ | ------------------------------------ | ------------------------------- | ------------------------------------- | ------------------------------- |
| `build`     | End-to-end autonomous implementation | user requirements, repo, constraints | production-ready implementation | sdlc, planner, coder, validator       | validated + resumable execution |
| `debug`     | Diagnose and repair failures         | logs, failing tests, runtime traces  | repaired implementation         | diagnostics, bug-fixer, replay-memory | targeted fixes only             |
| `review`    | Deep engineering/code review         | source code, PRs, architecture       | review reports                  | debate, reviewer, architect-review    | adversarial critique included   |
| `refactor`  | Improve maintainability safely       | existing implementation              | cleaner/refactored code         | refactorer, complexity-gate           | no behavior changes             |
| `architect` | Design scalable systems              | requirements, constraints            | architecture plans              | planner, architect-review             | explicit boundaries             |
| `test`      | Generate/improve testing             | code, specs, runtime behavior        | test suites                     | test-design, test-writer              | regression protection           |
| `document`  | Generate docs/tutorials              | source code, APIs, specs             | documentation                   | docs-writer, api-docs                 | synchronized documentation      |
| `optimize`  | Improve runtime performance          | benchmarks, runtime metrics          | optimized implementation        | performance-review, benchmark-gate    | measurable improvements only    |
| `secure`    | Security auditing/hardening          | code, dependencies, configs          | hardened implementation         | security-review, security-gate        | security-first validation       |
| `migrate`   | Safe schema/code migrations          | schemas, legacy code                 | migration artifacts             | migration-writer, validator           | rollback-safe execution         |

---

# Research & Analysis Capabilities

| Capability | Responsibility                | Inputs                    | Outputs               | Internally Uses            | Critical Guarantees                 |
| ---------- | ----------------------------- | ------------------------- | --------------------- | -------------------------- | ----------------------------------- |
| `research` | Deep technical investigation  | problem/domain/context    | research report       | summarizer, memory-manager | evidence-backed analysis            |
| `analyze`  | Deep system/codebase analysis | repository/system         | analysis reports      | diagnostics, reviewer      | structured findings                 |
| `explain`  | Explain architecture/code     | source code, architecture | explanations          | architecture-docs          | implementation-aligned explanations |
| `compare`  | Compare approaches/designs    | multiple implementations  | comparative analysis  | debate, reviewer           | tradeoff visibility                 |
| `estimate` | Complexity/risk estimation    | specs/tasks               | effort/risk estimates | complexity-estimator       | bounded estimation                  |
| `audit`    | Full engineering audit        | repository/runtime        | audit reports         | validator, diagnostics     | deterministic validation            |

---

# Operational Capabilities

| Capability      | Responsibility                     | Inputs               | Outputs             | Internally Uses              | Critical Guarantees      |
| --------------- | ---------------------------------- | -------------------- | ------------------- | ---------------------------- | ------------------------ |
| `run-overnight` | Long autonomous execution          | project/tasks        | completed execution | watchdog, checkpoint-manager | crash-safe autonomy      |
| `resume`        | Resume interrupted execution       | checkpoints/state    | resumed execution   | state-manager                | deterministic recovery   |
| `health-check`  | Validate repository/runtime health | repository/runtime   | health reports      | validator, health-monitor    | comprehensive validation |
| `recover`       | Recover failed/corrupted execution | failed runtime state | restored execution  | rollback-manager, replanner  | last-known-good recovery |

---

# Meta Capabilities

| Capability             | Responsibility                     | Inputs            | Outputs               | Internally Uses          | Critical Guarantees   |
| ---------------------- | ---------------------------------- | ----------------- | --------------------- | ------------------------ | --------------------- |
| `propose-improvements` | Suggest optimizations/improvements | execution history | improvement proposals | self-improvement         | proposal-only         |
| `generate-report`      | Produce execution summaries        | runtime artifacts | reports               | completion-report        | traceable execution   |
| `summarize-run`        | Explain autonomous execution       | logs/state        | summarized execution  | audit-logger, summarizer | transparent execution |

---

# Recommended Final Public Surface

```text id="x9x9lk"
build
debug
review
architect
test
document
optimize
secure
research
```

---

# 2. Internal Runtime Skills (Hidden Infrastructure)

These are hidden implementation mechanisms.

Users should never directly invoke these.

---

# Core Orchestration Skills

These control execution flow.

| Skill                   | Responsibility                        | Inputs                  | Outputs                | Invokes                   | Critical Rules                   |
| ----------------------- | ------------------------------------- | ----------------------- | ---------------------- | ------------------------- | -------------------------------- |
| `sdlc`                  | Main workflow orchestrator            | SPEC, state, task queue | phase transitions      | almost everything         | never edits code directly        |
| `task-queue`            | Persistent task scheduling            | plan.json               | runnable task order    | dependency-analyzer       | single-writer enforcement        |
| `phase-manager`         | FSM transition enforcement            | current phase           | next legal phase       | validator, orchestrator   | illegal transitions forbidden    |
| `replanner`             | Structural recovery                   | failures, stagnation    | regenerated plan       | planner, architect-review | preserves spec, resets tasks     |
| `watchdog`              | Stall/loop detection                  | metrics, timers         | retries/escalations    | replanner                 | bounded retries only             |
| `budget-manager`        | Runtime/token governance              | counters, budgets       | budget decisions       | model-router              | hard ceilings enforced           |
| `checkpoint-manager`    | Crash-safe persistence                | state snapshots         | checkpoints            | git-safety                | atomic writes only               |
| `run-controller`        | Global run lifecycle                  | mode, queue, budgets    | RUNNING/FAILED/DONE    | watchdog                  | no orphan states                 |
| `state-manager`         | Canonical state authority             | runtime state           | persisted state        | checkpoint-manager        | disk is truth                    |
| `termination-manager`   | Final exit control                    | validators, budgets     | DONE/FAILED state      | completion-report         | no silent exits                  |
| `execution-coordinator` | Cross-phase execution synchronization | tasks/phases            | synchronized execution | scheduler                 | deterministic execution ordering |
| `retry-controller`      | Retry policy management               | failures                | retry strategy         | replanner                 | bounded retry depth              |
| `queue-monitor`         | Queue-state analysis                  | task queues             | queue diagnostics      | scheduler                 | deadlocks forbidden              |
| `orchestrator-health`   | Orchestrator stability monitoring     | orchestration metrics   | health reports         | watchdog                  | unstable orchestrators halted    |
| `workflow-engine`       | Runtime workflow execution            | plans/tasks             | execution graph        | phase-manager             | workflow invariants enforced     |
| `execution-gateway`     | Runtime execution mediation           | execution requests      | approved execution     | policy-engine             | policy-first execution           |
| `scheduler`             | Task execution ordering               | queue/tasks             | execution schedule     | parallelism-manager       | deterministic scheduling         |
| `parallelism-manager`   | Safe parallel execution               | dependency graph        | parallel schedule      | lock-manager              | no path conflicts                |
| `dependency-resolver`   | Resolve runtime dependencies          | task graph              | dependency order       | planner                   | cyclic dependencies forbidden    |
| `runtime-coordinator`   | Coordinate runtime subsystems         | subsystem state         | synchronized runtime   | event-bus                 | runtime consistency required     |
# Consensus & Reasoning Skills

These implement structured multi-agent reasoning and controlled decision-making.

| Skill                      | Responsibility                       | Inputs                | Outputs                   | Invokes            | Critical Rules                           |
| -------------------------- | ------------------------------------ | --------------------- | ------------------------- | ------------------ | ---------------------------------------- |
| `debate`                   | Universal consensus protocol         | artifact + reviewers  | consensus result          | secretary          | no free-form convergence                 |
| `secretary`                | Debate summarization + synthesis     | debate transcripts    | round memory              | summarizer         | no opinion authority                     |
| `devils-advocate`          | Adversarial challenge                | current proposal      | objections                | debate             | must challenge initially                 |
| `architect-review`         | Structural sanity validation         | plans/code            | architecture verdict      | debate             | checks boundaries/cycles                 |
| `security-review`          | Threat modeling                      | code/spec             | security risks            | validator          | security always escalates                |
| `performance-review`       | Runtime scaling analysis             | benchmarks/code       | performance critique      | benchmark-gate     | regressions flagged                      |
| `test-design`              | Edge-case strategy                   | specs/code            | test scenarios            | test-writer        | mandatory adversarial tests              |
| `spec-review`              | Spec consistency checking            | SPEC.json             | contradictions/gaps       | spec-validator     | spec drift forbidden                     |
| `reviewer`                 | Human-style engineering review       | code/reports          | APPROVED/REJECTED         | debate             | cannot override tools                    |
| `consensus-analyzer`       | Confidence aggregation               | debate outputs        | convergence metrics       | watchdog           | variance thresholds enforced             |
| `risk-evaluator`           | Risk classification                  | unresolved objections | LOW/MEDIUM/HIGH           | orchestrator       | HIGH → human required                    |
| `forced-synthesis`         | Controlled convergence               | stalled debates       | synthesized artifact      | secretary          | max bounded usage                        |
| `reflection-engine`        | Self-critique generation             | generated outputs     | reflective critique       | debate             | critique mandatory for high-risk outputs |
| `reasoning-controller`     | Manage reasoning depth               | tasks/budgets         | reasoning strategy        | budget-manager     | bounded reasoning depth                  |
| `consistency-checker`      | Cross-output consistency validation  | multiple outputs      | consistency verdict       | validator          | contradictions escalated                 |
| `hallucination-detector`   | Detect fabricated information        | model outputs         | hallucination report      | validator          | unverifiable claims flagged              |
| `argument-analyzer`        | Analyze debate quality               | debate transcripts    | argument strength metrics | consensus-analyzer | unsupported claims penalized             |
| `counterexample-generator` | Generate adversarial counterexamples | solutions/plans       | counterexamples           | devils-advocate    | must stress weak assumptions             |
| `decision-engine`          | Final structured decision synthesis  | debate results        | final decisions           | risk-evaluator     | evidence-weighted decisions only         |
| `trust-calibrator`         | Confidence/trust calibration         | validator outputs     | trust scores              | consensus-analyzer | low-confidence outputs escalated         |

---

# Planning Skills

These generate executable work structures and implementation graphs.

| Skill                     | Responsibility                           | Inputs                      | Outputs                     | Invokes              | Critical Rules                   |
| ------------------------- | ---------------------------------------- | --------------------------- | --------------------------- | -------------------- | -------------------------------- |
| `spec-writer`             | Generate machine-readable specifications | user requirements           | SPEC.json                   | debate               | no implementation details        |
| `feasibility-validator`   | Validate technical feasibility           | SPEC.json                   | feasible/infeasible verdict | validator            | impossible specs rejected        |
| `planner`                 | Build execution strategy                 | SPEC                        | plan.json                   | task-decomposer      | dependency ordered               |
| `dependency-analyzer`     | DAG validation                           | tasks                       | dependency graph            | planner              | cycles forbidden                 |
| `task-decomposer`         | Atomic task splitting                    | plan goals                  | executable tasks            | complexity-estimator | tasks must be testable           |
| `complexity-estimator`    | Estimate implementation difficulty       | tasks                       | LOW/MEDIUM/HIGH complexity  | budget-manager       | controls retries                 |
| `architecture-planner`    | High-level architecture planning         | specs                       | architecture map            | architect-review     | explicit module boundaries       |
| `acceptance-planner`      | Acceptance test mapping                  | SPEC                        | acceptance suite            | acceptance-validator | every goal mapped                |
| `constraint-manager`      | Constraint propagation                   | architectural constraints   | enforced constraints        | validator            | immutable after approval         |
| `risk-planner`            | Risk-aware planning                      | architecture                | mitigation plan             | security-review      | unresolved risks tracked         |
| `milestone-planner`       | Milestone generation                     | execution plans             | milestones                  | scheduler            | milestones must be measurable    |
| `timeline-estimator`      | Runtime/time estimation                  | plans/tasks                 | estimated timelines         | budget-manager       | bounded estimates only           |
| `resource-planner`        | Resource allocation planning             | workloads                   | resource plans              | resource-monitor     | resource ceilings enforced       |
| `parallelization-planner` | Parallel execution planning              | dependency graph            | parallel execution graph    | parallelism-manager  | unsafe parallelism forbidden     |
| `rollback-planner`        | Recovery-path planning                   | execution plans             | rollback strategy           | rollback-manager     | rollback always available        |
| `workflow-planner`        | Workflow graph generation                | tasks/specs                 | workflow DAG                | workflow-engine      | deterministic workflows          |
| `checkpoint-planner`      | Checkpoint placement strategy            | workflows                   | checkpoint map              | checkpoint-manager   | recovery-safe placement          |
| `verification-planner`    | Validation sequencing                    | plans/code                  | verification flow           | validator            | verification before completion   |
| `integration-planner`     | Cross-module integration planning        | architecture                | integration sequence        | integration-coder    | compatibility-first planning     |
| `deployment-planner`      | Deployment/runtime planning              | infrastructure requirements | deployment plan             | deployment-docs      | reproducible deployment required |

---

# Coding Skills

These execute implementation and code generation.

| Skill                    | Responsibility                      | Inputs                          | Outputs                   | Invokes           | Critical Rules                    |
| ------------------------ | ----------------------------------- | ------------------------------- | ------------------------- | ----------------- | --------------------------------- |
| `coder`                  | General implementation              | tasks                           | patches                   | patch-manager     | no spec modification              |
| `backend-coder`          | Backend/services/business logic     | backend tasks                   | backend code              | tests             | optional specialization           |
| `frontend-coder`         | UI/client implementation            | UI tasks                        | frontend code             | validator         | optional specialization           |
| `refactorer`             | Maintainability improvements        | approved code                   | cleaner code              | complexity-gate   | no behavior changes               |
| `test-writer`            | Unit/integration test generation    | code/specs                      | tests                     | pytest            | mandatory coverage                |
| `bug-fixer`              | Focused repair workflow             | failure reports                 | fixes                     | validator         | targeted diffs only               |
| `merge-agent`            | Deterministic branch merge          | parallel outputs                | merged code               | diff-manager      | no creative synthesis             |
| `patch-generator`        | Minimal patch creation              | tasks/context                   | structured diffs          | coder             | bounded patch size                |
| `migration-writer`       | DB/schema migrations                | schema changes                  | migration scripts         | validator         | rollback-safe only                |
| `api-implementer`        | Endpoint implementation             | API specs                       | handlers/routes           | tests             | contract-first                    |
| `cli-implementer`        | CLI/tooling support                 | CLI specs                       | commands                  | validator         | deterministic UX                  |
| `integration-coder`      | Cross-module integration            | multiple modules                | integrated implementation | merge-agent       | compatibility validated           |
| `boilerplate-generator`  | Generate reusable scaffolding       | architecture/specs              | boilerplate code          | planner           | no dead scaffolding               |
| `config-generator`       | Runtime/config generation           | deployment/runtime requirements | configs                   | validator         | deterministic configuration       |
| `schema-generator`       | Data/schema generation              | data models                     | schemas/migrations        | migration-writer  | schema consistency enforced       |
| `adapter-generator`      | Compatibility adapter generation    | incompatible interfaces         | adapters                  | integration-coder | adapters must preserve semantics  |
| `optimization-coder`     | Performance-oriented implementation | performance constraints         | optimized code            | benchmark-gate    | benchmarks mandatory              |
| `security-hardener`      | Secure-code transformations         | source code                     | hardened code             | security-review   | unsafe patterns removed           |
| `code-modernizer`        | Legacy-code modernization           | legacy source                   | modernized implementation | validator         | backwards compatibility preserved |
| `generator-orchestrator` | Coordinate code generators          | generation tasks                | generated artifacts       | patch-generator   | generator outputs validated       |
# Validation Skills

These define objective correctness and quality enforcement.

| Skill                       | Responsibility                        | Inputs               | Outputs                 | Invokes              | Critical Rules                      |
| --------------------------- | ------------------------------------- | -------------------- | ----------------------- | -------------------- | ----------------------------------- |
| `validator`                 | Validation orchestrator               | code/spec            | PASS/FAIL               | all gates            | no subjective approval              |
| `tool-gate`                 | Deterministic tool execution          | repository           | tool results            | pytest/mypy/etc      | tools are law                       |
| `coverage-gate`             | Coverage enforcement                  | test results         | coverage verdict        | pytest-cov           | thresholds mandatory                |
| `complexity-gate`           | Complexity enforcement                | source code          | complexity metrics      | radon/xenon          | rejects excessive complexity        |
| `security-gate`             | Security enforcement                  | source/dependencies  | security verdict        | bandit/semgrep       | cannot be bypassed                  |
| `benchmark-gate`            | Performance regression checks         | benchmarks           | performance report      | benchmark runner     | compares baselines                  |
| `spec-validator`            | Spec compliance validation            | SPEC + output        | semantic verdict        | acceptance-validator | contract is authoritative           |
| `acceptance-validator`      | Acceptance-test execution             | acceptance suite     | acceptance status       | tests                | every requirement checked           |
| `regression-validator`      | Regression prevention                 | previous state       | regression report       | tests                | historical safety                   |
| `build-validator`           | Build integrity verification          | project              | build pass/fail         | build tools          | build must succeed                  |
| `type-validator`            | Type correctness validation           | source code          | typing report           | mypy/tsc             | strict mode preferred               |
| `lint-validator`            | Style consistency enforcement         | source               | lint report             | ruff/eslint          | deterministic formatting            |
| `integration-validator`     | Cross-module compatibility            | integrated modules   | integration verdict     | tests                | incompatible interfaces rejected    |
| `runtime-validator`         | Runtime sanity verification           | running application  | runtime status          | health-monitor       | runtime crashes block approval      |
| `dependency-validator`      | Dependency safety analysis            | dependency graph     | dependency report       | security-gate        | vulnerable deps rejected            |
| `schema-validator`          | Schema integrity validation           | configs/schemas      | schema verdict          | schema-enforcer      | malformed schemas rejected          |
| `api-contract-validator`    | API contract verification             | API specs + handlers | contract report         | tests                | strict contract adherence           |
| `migration-validator`       | Migration safety verification         | migrations           | migration report        | rollback-manager     | rollback required                   |
| `sandbox-validator`         | Execution isolation validation        | runtime commands     | sandbox verdict         | sandbox              | unsafe execution denied             |
| `artifact-validator`        | Generated-artifact verification       | builds/docs/reports  | artifact status         | validator            | incomplete artifacts rejected       |
| `state-validator`           | Runtime-state validation              | runtime state        | state integrity verdict | invariant-checker    | corrupted states halted             |
| `consistency-validator`     | Multi-artifact consistency validation | outputs/specs        | consistency report      | consistency-checker  | contradictions rejected             |
| `resource-validator`        | Resource-limit validation             | runtime metrics      | resource verdict        | resource-monitor     | exhaustion prevented                |
| `checkpoint-validator`      | Checkpoint integrity validation       | checkpoints          | checkpoint status       | checkpoint-manager   | invalid checkpoints rejected        |
| `orchestration-validator`   | Workflow/orchestration validation     | execution graph      | orchestration verdict   | workflow-engine      | invalid workflows halted            |
| `parallelism-validator`     | Parallel-execution safety validation  | task graph           | parallelism report      | parallelism-manager  | race conditions blocked             |
| `compliance-validator`      | Governance/compliance validation      | runtime state        | compliance report       | compliance-checker   | non-compliance escalated            |
| `trust-validator`           | Trust/confidence verification         | generated outputs    | trust score             | trust-calibrator     | low-trust outputs flagged           |
| `reproducibility-validator` | Deterministic replay validation       | execution logs       | reproducibility verdict | replay-memory        | non-determinism rejected            |
| `deployment-validator`      | Deployment correctness validation     | deployment configs   | deployment report       | deployment-planner   | deployment reproducibility required |

---

# Memory & Persistence Skills

These stabilize long-running autonomy and preserve execution intelligence.

| Skill                      | Responsibility                   | Inputs                | Outputs                   | Invokes             | Critical Rules                   |
| -------------------------- | -------------------------------- | --------------------- | ------------------------- | ------------------- | -------------------------------- |
| `memory-manager`           | Memory routing                   | queries               | relevant memories         | context-builder     | bounded retrieval                |
| `project-memory`           | Stable architectural memory      | validated knowledge   | persistent knowledge      | summarizer          | only stable facts                |
| `error-memory`             | Failure-pattern tracking         | failures              | reusable lessons          | replanner           | no duplicate fixes               |
| `context-builder`          | Prompt-context assembly          | task state            | optimized context         | summarizer          | spec always included             |
| `summarizer`               | Context compression              | transcripts/logs      | summaries                 | secretary           | preserves critical info          |
| `archive-manager`          | Historical archival              | completed runs        | archives                  | retrieval           | append-only                      |
| `replay-memory`            | Deterministic replay support     | logs                  | replay context            | diagnostics         | immutable                        |
| `checkpoint-memory`        | State snapshots                  | runtime state         | recoverable snapshots     | checkpoint-manager  | crash-safe                       |
| `decision-memory`          | Decision-history tracking        | orchestrator outputs  | audit decisions           | audit-logger        | append-only                      |
| `lesson-extractor`         | Long-term improvement extraction | runs/errors           | lessons learned           | project-memory      | only validated lessons           |
| `semantic-memory`          | Semantic knowledge retrieval     | embeddings/queries    | semantic matches          | memory-manager      | relevance-ranked only            |
| `episodic-memory`          | Execution-history recall         | prior runs            | execution episodes        | replay-memory       | immutable history                |
| `working-memory`           | Active-context storage           | current execution     | active runtime context    | context-builder     | bounded context window           |
| `constraint-memory`        | Persistent constraint storage    | architecture rules    | enforced constraints      | validator           | immutable constraints            |
| `tool-memory`              | Tool-execution history           | tool outputs          | reusable tool context     | diagnostics         | tool traces preserved            |
| `conversation-memory`      | User-interaction continuity      | dialogues/prompts     | conversation context      | summarizer          | bounded retention                |
| `knowledge-cache`          | Cached reusable knowledge        | prior computations    | reusable cache            | model-router        | cache invalidation required      |
| `state-journal`            | Append-only execution history    | runtime events        | chronological journal     | audit-logger        | immutable ordering               |
| `artifact-store`           | Artifact persistence             | generated outputs     | retrievable artifacts     | archive-manager     | versioned storage                |
| `memory-garbage-collector` | Memory cleanup/optimization      | stale memory          | optimized memory state    | archive-manager     | preserve critical history        |
| `retrieval-engine`         | Context retrieval optimization   | memory queries        | ranked retrievals         | semantic-memory     | deterministic retrieval ordering |
| `memory-indexer`           | Memory indexing/searchability    | archived artifacts    | searchable indexes        | retrieval-engine    | index consistency required       |
| `memory-validator`         | Memory integrity validation      | stored memory         | integrity reports         | validator           | corrupted memory rejected        |
| `timeline-memory`          | Temporal execution tracking      | runtime events        | timeline graph            | replay-memory       | chronological integrity required |
| `reasoning-memory`         | Reasoning-chain persistence      | debate/reasoning logs | reusable reasoning chains | reflection-engine   | reasoning provenance preserved   |
| `policy-memory`            | Persistent governance rules      | runtime policies      | active policy state       | policy-engine       | immutable governance history     |
| `capability-memory`        | Runtime capability tracking      | skill metadata        | capability graph          | capability-registry | stale capabilities removed       |
| `session-memory`           | Per-run transient storage        | active execution      | session context           | working-memory      | session-scoped only              |
| `vector-memory`            | Embedding/vector storage         | embeddings            | vector indexes            | semantic-memory     | embedding consistency required   |
| `provenance-memory`        | Artifact lineage preservation    | generated artifacts   | provenance graph          | lineage-tracker     | full traceability mandatory      |
# Git & Workspace Skills

These protect repository integrity, filesystem safety, and deterministic modification control.

| Skill                     | Responsibility                   | Inputs              | Outputs               | Invokes              | Critical Rules                     |
| ------------------------- | -------------------------------- | ------------------- | --------------------- | -------------------- | ---------------------------------- |
| `git-safety`              | Rollback/checkpoint safety       | repo state          | safe commits          | checkpoint-manager   | no unsafe mutations                |
| `workspace-guard`         | Filesystem protection            | paths               | access permissions    | sandbox              | project-root only                  |
| `sandbox`                 | Command isolation                | shell requests      | allowed execution     | policy-engine        | allowlist only                     |
| `diff-manager`            | Diff analysis                    | branches/diffs      | structured comparison | merge-agent          | no hidden changes                  |
| `patch-manager`           | Patch application                | diffs               | applied patches       | git-safety           | atomic application                 |
| `branch-manager`          | Branch lifecycle management      | tasks               | isolated branches     | git                  | one branch per task                |
| `rollback-manager`        | Deterministic recovery           | checkpoints         | restored state        | git-safety           | last-green rollback                |
| `lock-manager`            | Path locking                     | affected paths      | locks                 | task-queue           | single writer only                 |
| `workspace-validator`     | Repository integrity validation  | workspace           | integrity status      | validator            | corruption detection mandatory     |
| `command-runner`          | Controlled command execution     | commands            | outputs/logs          | sandbox              | fully logged execution             |
| `repo-analyzer`           | Repository structure analysis    | repository          | repo graph            | planner              | invalid structures flagged         |
| `staging-manager`         | Git staging control              | diffs/files         | staged changes        | git-safety           | selective staging only             |
| `commit-manager`          | Deterministic commit creation    | staged diffs        | commits               | audit-logger         | traceable commits only             |
| `conflict-resolver`       | Merge conflict handling          | conflicting diffs   | resolved state        | merge-agent          | deterministic resolution only      |
| `workspace-snapshotter`   | Full workspace snapshots         | filesystem state    | snapshots             | checkpoint-manager   | snapshot consistency required      |
| `filesystem-monitor`      | Workspace mutation tracking      | file events         | mutation logs         | audit-logger         | hidden mutations forbidden         |
| `secret-scanner`          | Secret/token detection           | repository          | secret report         | security-gate        | secrets block execution            |
| `binary-guard`            | Binary artifact protection       | repo files          | binary status         | validator            | uncontrolled binaries denied       |
| `temp-workspace-manager`  | Temporary isolated workspaces    | tasks               | isolated environments | sandbox              | isolated execution only            |
| `cleanup-manager`         | Workspace cleanup                | temporary artifacts | clean workspace       | workspace-validator  | preserve checkpoints               |
| `artifact-diff-engine`    | Artifact-level diff analysis     | generated artifacts | artifact comparisons  | diff-manager         | semantic diffs preferred           |
| `workspace-indexer`       | Repository indexing/search       | repo contents       | searchable index      | retrieval-engine     | index synchronization required     |
| `submodule-manager`       | Git submodule governance         | submodule configs   | managed submodules    | dependency-validator | pinned versions only               |
| `git-hook-manager`        | Git-hook lifecycle control       | hooks/configs       | validated hooks       | validator            | unsafe hooks rejected              |
| `repo-health-monitor`     | Repository health analysis       | repository state    | health reports        | diagnostics          | corrupted repositories halted      |
| `file-permission-manager` | File permission governance       | filesystem metadata | permission states     | workspace-guard      | unsafe permissions rejected        |
| `snapshot-differ`         | Snapshot comparison engine       | snapshots           | snapshot deltas       | rollback-manager     | deterministic comparisons          |
| `workspace-partitioner`   | Workspace isolation partitioning | execution graph     | isolated partitions   | lock-manager         | partition overlap forbidden        |
| `artifact-publisher`      | Controlled artifact export       | validated artifacts | published outputs     | artifact-validator   | only validated artifacts published |
| `path-resolver`           | Canonical path resolution        | filesystem paths    | normalized paths      | workspace-guard      | traversal attacks blocked          |

---

# Operational Skills

These manage runtime execution behavior, scalability, and execution governance.

| Skill                   | Responsibility                    | Inputs                | Outputs                | Invokes             | Critical Rules                    |
| ----------------------- | --------------------------------- | --------------------- | ---------------------- | ------------------- | --------------------------------- |
| `model-router`          | Model selection                   | task type             | selected model         | fallback-manager    | lowest sufficient tier            |
| `fallback-manager`      | Failure fallback handling         | failures/timeouts     | alternate models       | watchdog            | bounded fallback chains           |
| `parallelism-manager`   | Parallel execution control        | task graph            | parallel schedule      | task-queue          | no path conflicts                 |
| `resource-monitor`      | CPU/RAM/runtime monitoring        | system metrics        | health metrics         | watchdog            | exhaustion prevention             |
| `health-monitor`        | Long-run health analysis          | runtime state         | health reports         | diagnostics         | degradation detection mandatory   |
| `latency-monitor`       | Timeout/latency monitoring        | execution durations   | degraded states        | fallback-manager    | hanging calls prevented           |
| `throughput-manager`    | Throughput optimization           | queue/runtime         | scheduling hints       | orchestrator        | respects resource budgets         |
| `runtime-profiler`      | Bottleneck profiling              | execution traces      | bottleneck reports     | performance-review  | profiling-only access             |
| `mode-manager`          | Runtime-mode control              | configs               | runtime modes          | budget-manager      | modes never weaken safety         |
| `scheduler`             | Task execution ordering           | queues/tasks          | execution order        | parallelism-manager | deterministic scheduling          |
| `executor`              | Runtime task execution            | runnable tasks        | execution results      | command-runner      | isolated execution mandatory      |
| `orchestrator-health`   | Orchestrator stability monitoring | orchestration metrics | health status          | watchdog            | unstable orchestrators halted     |
| `retry-controller`      | Retry strategy governance         | failures              | retry decisions        | replanner           | bounded retry policy              |
| `throttle-manager`      | Runtime throttling                | throughput metrics    | throttled execution    | resource-monitor    | overload prevention               |
| `queue-monitor`         | Queue-state diagnostics           | task queues           | queue analysis         | scheduler           | deadlock detection mandatory      |
| `runtime-synchronizer`  | Multi-process coordination        | parallel state        | synchronized state     | lock-manager        | synchronization mandatory         |
| `event-scheduler`       | Event-driven scheduling           | runtime events        | scheduled actions      | event-bus           | deterministic dispatch            |
| `telemetry-manager`     | Runtime telemetry aggregation     | execution metrics     | telemetry streams      | metrics-engine      | telemetry immutable               |
| `failure-detector`      | Early-failure prediction          | runtime signals       | failure warnings       | diagnostics         | proactive escalation required     |
| `autonomy-controller`   | Autonomous-execution governance   | runtime policies      | autonomy decisions     | policy-engine       | bounded autonomy only             |
| `load-balancer`         | Runtime load balancing            | workloads             | balanced distribution  | throughput-manager  | overload redistribution required  |
| `runtime-regulator`     | Runtime-governance enforcement    | execution state       | governance actions     | policy-engine       | governance precedence enforced    |
| `capacity-planner`      | Runtime-capacity planning         | workloads/resources   | capacity forecasts     | resource-monitor    | resource ceilings preserved       |
| `worker-manager`        | Worker lifecycle management       | workers/tasks         | active workers         | executor            | failed workers recycled           |
| `node-monitor`          | Runtime-node monitoring           | node telemetry        | node status            | health-monitor      | unhealthy nodes isolated          |
| `distributed-scheduler` | Distributed task scheduling       | distributed DAG       | node assignments       | scheduler           | deterministic placement           |
| `state-replicator`      | Distributed state replication     | runtime state         | replicated state       | checkpoint-manager  | replication consistency required  |
| `failover-manager`      | Runtime failover handling         | node failures         | failover execution     | watchdog            | automatic failover                |
| `runtime-adapter`       | Runtime compatibility adaptation  | runtime requirements  | adapted execution      | executor            | compatibility validation required |
| `environment-manager`   | Runtime-environment setup         | configs/dependencies  | configured environment | validator           | reproducible environments         |
| `dependency-installer`  | Dependency installation           | manifests             | installed dependencies | security-gate       | unsafe packages rejected          |
# Documentation Skills

These generate human-readable artifacts, traceability records, and operational documentation.

| Skill                         | Responsibility                        | Inputs                 | Outputs                | Invokes               | Critical Rules                    |
| ----------------------------- | ------------------------------------- | ---------------------- | ---------------------- | --------------------- | --------------------------------- |
| `docs-writer`                 | README/docs generation                | code/spec              | documentation          | summarizer            | user-facing clarity               |
| `docstring-generator`         | Inline documentation                  | source code            | docstrings             | validator             | no hallucinated APIs              |
| `architecture-docs`           | Architecture summarization            | plans/code             | architecture docs      | architect-review      | synchronized with implementation  |
| `completion-report`           | Final execution reporting             | validators/state       | completion_report.json | audit-logger          | mandatory for DONE                |
| `changelog-generator`         | Change-summary generation             | diffs/commits          | changelog              | git logs              | deterministic summaries           |
| `usage-docs`                  | Usage examples/tutorials              | APIs/features          | tutorials/examples     | validator             | examples must run                 |
| `api-docs`                    | API-reference generation              | routes/schemas         | API documentation      | tests                 | contract accuracy required        |
| `decision-report`             | Architectural rationale reporting     | debates                | decision records       | secretary             | traceable reasoning mandatory     |
| `spec-docs`                   | Human-readable specifications         | SPEC.json              | specification docs     | spec-review           | synchronized with spec            |
| `runbook-generator`           | Operational runbook generation        | runtime configs        | runbooks               | health-monitor        | operational accuracy required     |
| `deployment-docs`             | Deployment/setup instructions         | infrastructure configs | deployment docs        | validator             | reproducible deployment required  |
| `troubleshooting-docs`        | Failure-resolution guides             | diagnostics            | troubleshooting docs   | bug-fixer             | evidence-based fixes only         |
| `release-notes-generator`     | Release-summary generation            | commits/diffs          | release notes          | changelog-generator   | version alignment required        |
| `diagram-generator`           | Architecture/workflow diagrams        | plans/modules          | diagrams               | architecture-docs     | architecture consistency required |
| `compliance-report`           | Compliance/audit reporting            | validator outputs      | compliance docs        | compliance-checker    | audit-ready formatting            |
| `traceability-report`         | Requirement traceability mapping      | specs/tests            | traceability matrix    | acceptance-validator  | complete mapping mandatory        |
| `migration-docs`              | Migration instructions/documentation  | migrations             | migration guides       | migration-validator   | rollback steps mandatory          |
| `schema-docs`                 | Schema/data-model documentation       | schemas/models         | schema docs            | schema-validator      | schema synchronization required   |
| `workflow-docs`               | Workflow/process documentation        | orchestration graphs   | workflow docs          | workflow-engine       | workflow accuracy required        |
| `configuration-docs`          | Runtime/configuration documentation   | configs                | config docs            | environment-manager   | environment consistency required  |
| `runtime-docs`                | Runtime-operation documentation       | runtime systems        | runtime manuals        | telemetry-manager     | operational correctness required  |
| `incident-reporter`           | Incident/postmortem reporting         | failures/logs          | incident reports       | diagnostics           | root-cause analysis mandatory     |
| `audit-report-generator`      | Immutable audit reporting             | audit trails           | audit reports          | audit-logger          | append-only evidence              |
| `execution-summary-generator` | High-level execution summaries        | execution logs         | summaries              | summarizer            | concise but complete              |
| `knowledge-docs`              | Knowledge-base generation             | historical artifacts   | knowledge articles     | project-memory        | validated knowledge only          |
| `onboarding-docs`             | Developer onboarding docs             | architecture/repo      | onboarding guides      | architecture-docs     | beginner-safe explanations        |
| `cli-docs`                    | CLI usage/reference docs              | CLI commands           | CLI manuals            | cli-implementer       | executable examples required      |
| `integration-docs`            | Integration/API interoperability docs | integrations           | integration guides     | integration-validator | compatibility accuracy required   |
| `security-docs`               | Security-policy documentation         | security configs       | security docs          | security-review       | no sensitive leakage              |
| `benchmark-reporter`          | Benchmark/performance reporting       | benchmark results      | performance reports    | benchmark-gate        | reproducible measurements only    |

---

# Meta / System Skills

These govern the runtime itself, enforce global invariants, and coordinate system-wide governance.

| Skill                    | Responsibility                          | Inputs                | Outputs                | Invokes             | Critical Rules                      |
| ------------------------ | --------------------------------------- | --------------------- | ---------------------- | ------------------- | ----------------------------------- |
| `policy-engine`          | Global rule enforcement                 | runtime actions       | allow/deny verdicts    | orchestrator        | no implicit behavior                |
| `invariant-checker`      | System invariant validation             | runtime state         | invariant status       | watchdog            | invariant violations halt execution |
| `audit-logger`           | Immutable audit logging                 | all runtime actions   | audit trail            | archive-manager     | append-only logs                    |
| `diagnostics`            | Failure diagnostics                     | failures/logs         | diagnostic reports     | replay-memory       | reproducible evidence required      |
| `self-improvement`       | Proposal generation only                | historical runs       | improvement proposals  | reviewers           | cannot self-apply                   |
| `compliance-checker`     | Policy/spec compliance                  | runtime state         | compliance status      | validator           | governance enforcement mandatory    |
| `metrics-engine`         | Runtime metrics aggregation             | execution metrics     | dashboards/stats       | health-monitor      | quantitative-only reporting         |
| `event-bus`              | Internal event propagation              | runtime events        | routed events          | orchestrator        | deterministic delivery              |
| `schema-enforcer`        | JSON/schema validation                  | artifacts             | schema verdict         | validator           | malformed artifacts rejected        |
| `termination-auditor`    | Clean-shutdown validation               | final runtime state   | termination audit      | completion-report   | improper shutdowns rejected         |
| `capability-registry`    | Runtime capability discovery            | registered skills     | capability graph       | orchestrator        | immutable runtime registry          |
| `plugin-manager`         | Plugin/extension governance             | plugins/extensions    | validated plugins      | policy-engine       | unsigned plugins denied             |
| `runtime-governor`       | Global runtime coordination             | runtime state         | governance decisions   | orchestrator        | governance precedence enforced      |
| `simulation-engine`      | Dry-run/simulation support              | plans/tasks           | simulated outcomes     | planner             | no real mutations allowed           |
| `evolution-manager`      | Runtime evolution coordination          | improvement proposals | approved evolutions    | self-improvement    | human approval mandatory            |
| `trust-manager`          | Trust/risk calibration                  | validator outputs     | trust scores           | risk-evaluator      | low-trust outputs escalated         |
| `lineage-tracker`        | Artifact lineage tracking               | generated artifacts   | lineage graph          | audit-logger        | full provenance mandatory           |
| `reproducibility-engine` | Deterministic reproducibility           | runs/artifacts        | reproducible execution | replay-memory       | deterministic replay required       |
| `safety-controller`      | Global safety governance                | runtime actions       | safety verdicts        | policy-engine       | safety overrides execution          |
| `meta-orchestrator`      | Coordination of orchestrators           | orchestration state   | orchestration control  | sdlc                | prevents orchestration conflicts    |
| `governance-engine`      | Runtime governance policies             | governance configs    | governance actions     | compliance-checker  | policy consistency required         |
| `risk-governor`          | System-wide risk management             | runtime risks         | mitigation actions     | risk-evaluator      | high-risk escalation mandatory      |
| `identity-manager`       | Runtime identity/capability control     | agents/services       | identity states        | permission-manager  | least-privilege enforcement         |
| `permission-manager`     | Runtime permission governance           | access requests       | permission verdicts    | policy-engine       | deny-by-default                     |
| `integrity-checker`      | Artifact/runtime integrity verification | runtime artifacts     | integrity reports      | invariant-checker   | corruption halts runtime            |
| `provenance-engine`      | Artifact provenance management          | outputs/logs          | provenance chains      | lineage-tracker     | full traceability mandatory         |
| `ethics-guard`           | Ethical/policy enforcement              | runtime decisions     | ethical verdicts       | policy-engine       | unsafe behavior blocked             |
| `reliability-engine`     | Runtime reliability governance          | telemetry/history     | reliability reports    | health-monitor      | reliability thresholds enforced     |
| `stability-monitor`      | Long-term runtime stability analysis    | runtime metrics       | stability reports      | diagnostics         | unstable runtimes quarantined       |
| `coordination-engine`    | Cross-subsystem synchronization         | subsystem states      | synchronized runtime   | event-bus           | consistency mandatory               |
| `capability-governor`    | Capability-access governance            | runtime capabilities  | capability permissions | capability-registry | unauthorized capabilities denied    |
# Observability & Telemetry Skills

These provide visibility into runtime behavior, execution analytics, debugging, tracing, and operational monitoring.

| Skill                     | Responsibility                     | Inputs                  | Outputs                | Invokes                     | Critical Rules                         |
| ------------------------- | ---------------------------------- | ----------------------- | ---------------------- | --------------------------- | -------------------------------------- |
| `trace-collector`         | Execution-trace collection         | runtime events          | execution traces       | telemetry-manager           | lossless tracing preferred             |
| `log-manager`             | Structured-log management          | logs/events             | normalized logs        | audit-logger                | append-only logging                    |
| `metrics-collector`       | Runtime-metric collection          | execution metrics       | aggregated metrics     | metrics-engine              | low-overhead collection                |
| `event-recorder`          | Event-stream recording             | runtime events          | recorded events        | event-bus                   | chronological consistency required     |
| `span-tracker`            | Distributed-execution tracking     | task executions         | span graphs            | trace-collector             | parent-child consistency required      |
| `alert-manager`           | Runtime alerting                   | failures/thresholds     | alerts                 | health-monitor              | critical alerts escalate               |
| `dashboard-generator`     | Runtime-dashboard generation       | telemetry               | dashboards             | metrics-engine              | real-time synchronization required     |
| `anomaly-detector`        | Behavioral anomaly detection       | telemetry/history       | anomaly reports        | diagnostics                 | statistically validated anomalies only |
| `timeline-builder`        | Execution-timeline generation      | logs/events             | execution timeline     | replay-memory               | deterministic ordering required        |
| `observability-router`    | Observability-pipeline routing     | telemetry streams       | routed telemetry       | trace-collector             | no telemetry loss                      |
| `signal-processor`        | Runtime signal normalization       | telemetry signals       | normalized signals     | metrics-collector           | signal integrity preserved             |
| `profiling-engine`        | Runtime profiling/analysis         | execution traces        | profiling reports      | runtime-profiler            | non-intrusive profiling only           |
| `runtime-inspector`       | Runtime-state inspection           | live runtime state      | inspection reports     | diagnostics                 | read-only inspection                   |
| `latency-analyzer`        | Execution-latency analysis         | timing metrics          | latency reports        | latency-monitor             | outlier detection mandatory            |
| `throughput-analyzer`     | Throughput-performance analysis    | workload metrics        | throughput reports     | throughput-manager          | bottlenecks highlighted                |
| `health-dashboard`        | Health-visualization generation    | health telemetry        | health dashboards      | health-monitor              | real-time updates required             |
| `event-correlator`        | Multi-event correlation analysis   | event streams           | correlated events      | anomaly-detector            | causal consistency required            |
| `failure-telemetry`       | Failure-specific telemetry capture | failures/errors         | failure telemetry      | diagnostics                 | preserve root-cause signals            |
| `resource-telemetry`      | Resource-usage telemetry           | CPU/RAM/network metrics | resource reports       | resource-monitor            | accurate measurements required         |
| `runtime-reporter`        | Runtime-status reporting           | execution state         | runtime summaries      | execution-summary-generator | state consistency mandatory            |
| `telemetry-archiver`      | Telemetry archival/storage         | telemetry streams       | archived telemetry     | archive-manager             | immutable telemetry storage            |
| `trace-validator`         | Trace-integrity validation         | execution traces        | trace verdicts         | validator                   | corrupted traces rejected              |
| `monitoring-orchestrator` | Monitoring-system coordination     | telemetry subsystems    | coordinated monitoring | telemetry-manager           | synchronized observability             |
| `incident-detector`       | Operational incident detection     | telemetry anomalies     | incident reports       | alert-manager               | proactive escalation mandatory         |
| `visibility-manager`      | Runtime visibility governance      | observability configs   | visibility policies    | policy-engine               | restricted data exposure               |
| `telemetry-compressor`    | Telemetry optimization/compression | telemetry streams       | compressed telemetry   | archive-manager             | preserve critical signals              |
| `execution-analytics`     | Execution-pattern analytics        | historical runs         | analytics reports      | metrics-engine              | evidence-based analytics               |
| `runtime-forensics`       | Post-failure forensic analysis     | logs/traces             | forensic reports       | diagnostics                 | forensic integrity required            |
| `observability-validator` | Observability-system validation    | telemetry systems       | validation reports     | validator                   | monitoring gaps rejected               |
| `status-broadcaster`      | Runtime-status broadcasting        | runtime states          | status streams         | notification-manager        | deterministic status propagation       |

---

# Tooling & Integration Skills

These manage external tools, APIs, runtimes, environments, and system integrations.

| Skill                    | Responsibility                       | Inputs                  | Outputs                 | Invokes              | Critical Rules                       |
| ------------------------ | ------------------------------------ | ----------------------- | ----------------------- | -------------------- | ------------------------------------ |
| `tool-registry`          | Tool capability registry             | registered tools        | tool graph              | orchestrator         | immutable registry                   |
| `tool-selector`          | Optimal-tool selection               | task requirements       | selected tools          | model-router         | deterministic selection              |
| `tool-executor`          | External-tool execution              | tool calls              | tool outputs            | sandbox              | isolated execution                   |
| `tool-validator`         | Tool-output validation               | tool results            | validated outputs       | validator            | malformed outputs rejected           |
| `api-gateway`            | External-API coordination            | API requests            | API responses           | command-runner       | rate limits enforced                 |
| `service-discovery`      | Runtime-service discovery            | runtime topology        | discovered services     | orchestrator         | stale services rejected              |
| `container-manager`      | Container orchestration              | container specs         | running containers      | sandbox              | isolated containers only             |
| `environment-manager`    | Runtime-environment setup            | environment configs     | configured runtime      | validator            | reproducible environments            |
| `dependency-installer`   | Dependency installation              | manifests               | installed dependencies  | security-gate        | unsafe packages rejected             |
| `runtime-adapter`        | Runtime compatibility adaptation     | runtime requirements    | adapted execution       | executor             | compatibility validated              |
| `sdk-manager`            | SDK/runtime-library governance       | SDK configs             | managed SDKs            | dependency-validator | pinned SDK versions required         |
| `plugin-loader`          | Runtime plugin loading               | plugin artifacts        | loaded plugins          | plugin-manager       | unsigned plugins rejected            |
| `integration-router`     | Cross-system integration routing     | integration requests    | routed integrations     | api-gateway          | integration isolation required       |
| `connector-manager`      | External-system connector governance | connectors              | active connectors       | tool-registry        | connector validation mandatory       |
| `service-adapter`        | External-service compatibility       | service APIs            | adapted integrations    | integration-coder    | semantic preservation required       |
| `runtime-launcher`       | Runtime/service launching            | launch configs          | running services        | environment-manager  | validated launch configs only        |
| `package-manager`        | Dependency/package governance        | package manifests       | managed packages        | dependency-validator | vulnerable packages blocked          |
| `tool-cache`             | Cached tool-output storage           | tool outputs            | reusable cache          | knowledge-cache      | cache consistency required           |
| `api-validator`          | External-API validation              | API responses           | validation reports      | schema-validator     | malformed APIs rejected              |
| `runtime-bridge`         | Cross-runtime interoperability       | runtime interfaces      | bridged execution       | runtime-adapter      | compatibility enforced               |
| `integration-validator`  | Integration correctness validation   | integrations            | integration reports     | validator            | incompatible integrations blocked    |
| `environment-validator`  | Environment consistency validation   | runtime environments    | environment reports     | validator            | drift detection mandatory            |
| `network-adapter`        | Network/protocol adaptation          | network requests        | adapted network traffic | network-guard        | secure protocols only                |
| `runtime-installer`      | Runtime installation/setup           | runtime artifacts       | installed runtimes      | sandbox              | reproducible installation required   |
| `workflow-integrator`    | External-workflow integration        | workflow APIs           | integrated workflows    | workflow-engine      | deterministic orchestration required |
| `external-state-sync`    | External-state synchronization       | external system state   | synchronized state      | state-replicator     | consistency mandatory                |
| `protocol-manager`       | Protocol compatibility management    | communication protocols | protocol mappings       | service-adapter      | unsupported protocols rejected       |
| `toolchain-orchestrator` | Toolchain coordination               | tool dependencies       | coordinated toolchains  | tool-selector        | deterministic execution ordering     |
| `integration-monitor`    | External-integration monitoring      | integration telemetry   | integration reports     | telemetry-manager    | degraded integrations isolated       |
| `runtime-exporter`       | Runtime/export packaging             | builds/artifacts        | export packages         | artifact-publisher   | validated exports only               |
# AI/LLM Coordination Skills

These govern model reasoning, prompting, agent coordination, and controlled intelligence orchestration.

| Skill                       | Responsibility                     | Inputs               | Outputs                 | Invokes              | Critical Rules                         |
| --------------------------- | ---------------------------------- | -------------------- | ----------------------- | -------------------- | -------------------------------------- |
| `prompt-builder`            | Structured prompt generation       | context/tasks        | optimized prompts       | context-builder      | deterministic templates                |
| `prompt-validator`          | Prompt sanity validation           | prompts              | validated prompts       | policy-engine        | unsafe prompts rejected                |
| `agent-spawner`             | Temporary-agent creation           | task specifications  | specialized agents      | orchestrator         | bounded agent count                    |
| `agent-coordinator`         | Multi-agent synchronization        | agent outputs        | coordinated reasoning   | debate               | isolated reasoning required            |
| `reasoning-controller`      | Reasoning-depth management         | tasks/budgets        | reasoning strategy      | budget-manager       | bounded reasoning depth                |
| `hallucination-detector`    | Fabrication detection              | model outputs        | hallucination reports   | validator            | unverifiable claims flagged            |
| `response-normalizer`       | Structured-output normalization    | raw generations      | normalized outputs      | schema-enforcer      | schema-first outputs                   |
| `chain-manager`             | Multi-step reasoning orchestration | tasks                | reasoning chains        | reasoning-controller | cycle prevention mandatory             |
| `reflection-engine`         | Self-critique generation           | outputs              | reflective critique     | debate               | critique mandatory for high-risk tasks |
| `consistency-checker`       | Cross-response consistency         | multiple outputs     | consistency verdict     | validator            | contradictions escalated               |
| `context-router`            | Context-distribution management    | memory/context       | routed context          | memory-manager       | bounded context size                   |
| `agent-memory-sync`         | Agent-context synchronization      | agent states         | synchronized memory     | working-memory       | isolated state consistency required    |
| `persona-manager`           | Specialized-agent persona control  | agent configs        | active personas         | agent-spawner        | personas cannot bypass policy          |
| `reasoning-validator`       | Reasoning-quality validation       | reasoning chains     | reasoning verdicts      | validator            | unsupported reasoning rejected         |
| `debate-orchestrator`       | Debate-session coordination        | debate participants  | structured debate       | debate               | deterministic debate flow              |
| `thought-compiler`          | Intermediate-thought compilation   | reasoning traces     | structured reasoning    | response-normalizer  | internal reasoning hidden from users   |
| `model-capability-profiler` | Model capability analysis          | model telemetry      | capability profiles     | model-router         | evidence-based profiling only          |
| `model-calibrator`          | Confidence calibration             | model outputs        | calibrated confidence   | trust-calibrator     | overconfidence penalized               |
| `agent-terminator`          | Agent lifecycle cleanup            | active agents        | terminated agents       | orchestrator         | orphan agents forbidden                |
| `reasoning-cache`           | Cached reasoning reuse             | reasoning traces     | reusable reasoning      | knowledge-cache      | stale reasoning invalidated            |
| `goal-interpreter`          | User-goal interpretation           | user requests        | structured goals        | spec-writer          | ambiguous goals escalated              |
| `instruction-compiler`      | Instruction normalization          | prompts/requirements | executable instructions | planner              | conflicting instructions rejected      |
| `response-validator`        | Response correctness validation    | generated responses  | validated responses     | validator            | invalid outputs blocked                |
| `multi-model-coordinator`   | Multi-model orchestration          | model outputs        | coordinated responses   | model-router         | deterministic aggregation              |
| `inference-scheduler`       | Inference workload scheduling      | inference tasks      | scheduled inference     | scheduler            | budget-aware scheduling                |
| `capability-router`         | Route tasks to best capabilities   | task metadata        | routed tasks            | capability-registry  | unauthorized routing forbidden         |
| `reasoning-trace-manager`   | Reasoning-trace persistence        | reasoning chains     | reasoning history       | reasoning-memory     | trace provenance preserved             |
| `adaptive-prompt-engine`    | Dynamic prompt optimization        | runtime telemetry    | optimized prompts       | prompt-builder       | bounded adaptation only                |
| `alignment-checker`         | Alignment/policy compliance        | model outputs        | alignment verdicts      | ethics-guard         | misaligned outputs blocked             |
| `output-ranker`             | Candidate-output ranking           | candidate responses  | ranked outputs          | trust-manager        | evidence-weighted ranking              |

---

# Security & Safety Skills

These enforce runtime safety, access governance, defensive execution, and protection against unsafe behavior.

| Skill                      | Responsibility                          | Inputs                       | Outputs                | Invokes              | Critical Rules                    |
| -------------------------- | --------------------------------------- | ---------------------------- | ---------------------- | -------------------- | --------------------------------- |
| `permission-manager`       | Permission enforcement                  | runtime requests             | permission verdicts    | policy-engine        | deny-by-default                   |
| `credential-guard`         | Credential/token protection             | secrets/tokens               | secured credentials    | secret-scanner       | secrets never logged              |
| `threat-detector`          | Threat detection                        | runtime activity             | threat reports         | diagnostics          | high-risk activity halted         |
| `sandbox-enforcer`         | Isolation enforcement                   | execution requests           | isolated execution     | sandbox              | isolation mandatory               |
| `network-guard`            | Network-access governance               | outbound requests            | network verdicts       | policy-engine        | restricted network access         |
| `data-loss-prevention`     | Sensitive-data protection               | runtime outputs              | sanitized outputs      | validator            | PII leakage blocked               |
| `integrity-checker`        | Runtime/artifact integrity verification | artifacts/state              | integrity reports      | invariant-checker    | corruption halts execution        |
| `exploit-detector`         | Exploit-pattern detection               | commands/code                | exploit warnings       | security-review      | exploit signatures blocked        |
| `access-auditor`           | Access logging/verification             | access events                | audit records          | audit-logger         | immutable access logs             |
| `safety-simulator`         | Safety dry-run analysis                 | execution plans              | safety forecasts       | simulation-engine    | unsafe plans blocked              |
| `isolation-manager`        | Runtime isolation governance            | runtime environments         | isolated runtimes      | sandbox-enforcer     | cross-isolation leakage forbidden |
| `policy-firewall`          | Runtime policy firewall                 | runtime actions              | filtered actions       | policy-engine        | unsafe actions denied             |
| `runtime-defender`         | Active runtime defense                  | runtime telemetry            | defensive actions      | threat-detector      | autonomous defense bounded        |
| `tamper-detector`          | Tampering/intrusion detection           | filesystem/runtime state     | tamper alerts          | diagnostics          | tampering escalated immediately   |
| `trust-boundary-enforcer`  | Trust-boundary enforcement              | inter-service communication  | trusted communication  | permission-manager   | trust-boundary violations blocked |
| `secure-channel-manager`   | Secure communication governance         | network traffic              | secured channels       | network-guard        | encrypted channels mandatory      |
| `input-sanitizer`          | Unsafe-input sanitization               | external/user input          | sanitized input        | validator            | injection prevention mandatory    |
| `output-sanitizer`         | Sensitive-output filtering              | generated outputs            | sanitized outputs      | data-loss-prevention | secret leakage forbidden          |
| `runtime-quarantine`       | Quarantine unsafe runtimes              | compromised runtime state    | quarantined execution  | safety-controller    | quarantined runtimes isolated     |
| `incident-response-engine` | Security-incident response              | threat reports               | response actions       | alert-manager        | critical incidents prioritized    |
| `attack-surface-analyzer`  | Attack-surface analysis                 | architecture/code            | attack-surface reports | security-review      | exposed surfaces minimized        |
| `compliance-firewall`      | Regulatory/policy enforcement           | runtime actions              | compliance verdicts    | compliance-checker   | non-compliance blocked            |
| `identity-verifier`        | Identity/authenticity verification      | runtime identities           | identity verdicts      | identity-manager     | spoofing prevented                |
| `secure-storage-manager`   | Secure artifact/secret storage          | sensitive artifacts          | encrypted storage      | credential-guard     | encrypted-at-rest mandatory       |
| `runtime-safety-monitor`   | Safety-state monitoring                 | runtime telemetry            | safety reports         | health-monitor       | unsafe runtimes halted            |
| `zero-trust-engine`        | Zero-trust execution governance         | runtime requests             | trust evaluations      | permission-manager   | no implicit trust                 |
| `abuse-detector`           | Abuse/misuse detection                  | usage telemetry              | abuse reports          | anomaly-detector     | abuse escalated automatically     |
| `security-orchestrator`    | Security-subsystem coordination         | security states              | coordinated defense    | runtime-defender     | synchronized defense required     |
| `recovery-guard`           | Secure recovery validation              | rollback/recovery operations | validated recovery     | rollback-manager     | unsafe recovery blocked           |
| `supply-chain-guard`       | Dependency/supply-chain security        | dependencies/packages        | supply-chain reports   | dependency-validator | compromised packages rejected     |
# Distributed & Parallel Execution Skills

These manage distributed runtimes, multi-node execution, parallel workflows, synchronization, and fault tolerance.

| Skill                            | Responsibility                       | Inputs                 | Outputs                 | Invokes               | Critical Rules                       |
| -------------------------------- | ------------------------------------ | ---------------------- | ----------------------- | --------------------- | ------------------------------------ |
| `distributed-scheduler`          | Multi-node task scheduling           | distributed task graph | node assignments        | scheduler             | deterministic placement              |
| `worker-manager`                 | Worker lifecycle management          | workers/tasks          | active workers          | executor              | failed workers recycled              |
| `node-health-monitor`            | Distributed-node health monitoring   | node telemetry         | node status             | health-monitor        | unhealthy nodes isolated             |
| `state-replicator`               | Distributed-state replication        | runtime state          | replicated state        | checkpoint-manager    | consistency mandatory                |
| `consensus-coordinator`          | Distributed consensus management     | distributed decisions  | consensus state         | debate                | quorum enforcement required          |
| `load-balancer`                  | Runtime load balancing               | workloads              | balanced execution      | throughput-manager    | overload prevention mandatory        |
| `distributed-lock-manager`       | Distributed resource locking         | shared resources       | distributed locks       | lock-manager          | deadlocks forbidden                  |
| `failover-manager`               | Automatic failover handling          | node failures          | failover execution      | watchdog              | automatic recovery required          |
| `shard-manager`                  | Task/data sharding                   | workloads/data         | shards                  | distributed-scheduler | deterministic sharding               |
| `cluster-orchestrator`           | Cluster-wide coordination            | cluster state          | orchestration decisions | meta-orchestrator     | cluster consistency required         |
| `node-coordinator`               | Cross-node synchronization           | node states            | synchronized cluster    | coordination-engine   | state divergence forbidden           |
| `distributed-queue-manager`      | Distributed queue coordination       | distributed queues     | synchronized queues     | task-queue            | queue consistency required           |
| `replication-validator`          | Replication correctness validation   | replicated state       | replication reports     | validator             | inconsistent replicas rejected       |
| `cross-node-router`              | Inter-node routing                   | distributed messages   | routed traffic          | event-bus             | deterministic routing                |
| `distributed-checkpoint-manager` | Distributed checkpoint orchestration | node checkpoints       | cluster checkpoints     | checkpoint-manager    | atomic distributed checkpoints       |
| `replica-manager`                | Replica lifecycle governance         | replicas               | active replicas         | state-replicator      | stale replicas removed               |
| `distributed-event-bus`          | Cluster-wide event propagation       | runtime events         | distributed events      | event-bus             | ordered event propagation            |
| `parallel-executor`              | High-concurrency execution           | parallel tasks         | execution results       | executor              | race conditions prevented            |
| `distributed-recovery-engine`    | Distributed runtime recovery         | cluster failures       | recovered cluster       | rollback-manager      | partial recovery forbidden           |
| `federation-manager`             | Multi-cluster federation             | cluster metadata       | federated execution     | cluster-orchestrator  | federation trust boundaries enforced |
| `partition-detector`             | Network/cluster partition detection  | network telemetry      | partition reports       | diagnostics           | split-brain prevention required      |
| `split-brain-guard`              | Prevent split-brain execution        | distributed state      | safe cluster state      | consensus-coordinator | multiple leaders forbidden           |
| `leader-election-manager`        | Leader-election coordination         | cluster topology       | elected leaders         | consensus-coordinator | deterministic elections required     |
| `distributed-telemetry-sync`     | Cross-node telemetry synchronization | telemetry streams      | synchronized telemetry  | telemetry-manager     | telemetry consistency mandatory      |
| `replication-compressor`         | Efficient state replication          | distributed state      | compressed replication  | state-replicator      | integrity preservation required      |
| `distributed-capacity-planner`   | Cluster-capacity planning            | cluster workloads      | capacity forecasts      | capacity-planner      | cluster ceilings enforced            |
| `remote-execution-manager`       | Remote execution governance          | remote tasks           | remote execution        | sandbox-enforcer      | remote isolation required            |
| `cross-runtime-sync`             | Multi-runtime synchronization        | runtime states         | synchronized runtimes   | runtime-synchronizer  | synchronization consistency required |
| `distributed-cache-manager`      | Shared/distributed cache governance  | cached state           | synchronized caches     | knowledge-cache       | stale caches invalidated             |
| `multi-region-coordinator`       | Multi-region runtime coordination    | regional runtimes      | synchronized regions    | cluster-orchestrator  | regional consistency mandatory       |

---

# Learning & Adaptation Skills

These govern controlled optimization, runtime learning, adaptive execution, and long-term system evolution.

| Skill                           | Responsibility                       | Inputs                    | Outputs                     | Invokes            | Critical Rules                          |
| ------------------------------- | ------------------------------------ | ------------------------- | --------------------------- | ------------------ | --------------------------------------- |
| `pattern-miner`                 | Detect recurring execution patterns  | execution history         | pattern reports             | lesson-extractor   | statistically significant patterns only |
| `optimization-engine`           | Runtime optimization proposals       | telemetry/history         | optimization plans          | self-improvement   | proposals only                          |
| `heuristic-manager`             | Execution-heuristic governance       | runtime metrics           | tuned heuristics            | scheduler          | bounded adaptation only                 |
| `strategy-evaluator`            | Execution-strategy evaluation        | strategy outcomes         | strategy rankings           | metrics-engine     | evidence-based ranking                  |
| `failure-learner`               | Learn from failures                  | diagnostics/history       | learned mitigations         | replanner          | validated lessons only                  |
| `success-profiler`              | Profile successful executions        | completed runs            | success signatures          | pattern-miner      | reproducibility required                |
| `adaptive-router`               | Adaptive runtime routing             | workload metrics          | routing decisions           | model-router       | bounded adaptation                      |
| `knowledge-distiller`           | Distill reusable knowledge           | historical artifacts      | distilled knowledge         | project-memory     | deduplicated knowledge                  |
| `workflow-optimizer`            | Optimize execution pipelines         | orchestration history     | optimized workflows         | planner            | invariants preserved                    |
| `capability-evaluator`          | Runtime capability evaluation        | skill metrics             | capability scores           | trust-manager      | objective scoring only                  |
| `behavior-profiler`             | Runtime-behavior profiling           | execution telemetry       | behavior profiles           | analytics-engine   | privacy-safe profiling only             |
| `adaptive-planner`              | Dynamically adjust plans             | runtime feedback          | updated plans               | replanner          | spec consistency preserved              |
| `execution-tuner`               | Runtime-performance tuning           | telemetry metrics         | tuned runtime configs       | throughput-manager | bounded tuning only                     |
| `feedback-analyzer`             | Human/runtime feedback analysis      | feedback streams          | feedback insights           | summarizer         | noisy feedback filtered                 |
| `heuristic-validator`           | Validate adaptive heuristics         | tuned heuristics          | heuristic reports           | validator          | unstable heuristics rejected            |
| `experience-repository`         | Persistent execution experience      | runtime history           | reusable experience base    | archive-manager    | validated experience only               |
| `adaptation-controller`         | Govern adaptive behavior             | runtime adaptations       | approved adaptations        | policy-engine      | unsafe adaptation blocked               |
| `learning-scheduler`            | Learning-cycle coordination          | historical runs           | scheduled learning tasks    | scheduler          | bounded learning budgets                |
| `knowledge-evaluator`           | Validate learned knowledge           | learned patterns          | knowledge reports           | validator          | false patterns rejected                 |
| `execution-predictor`           | Predict execution outcomes           | historical telemetry      | execution forecasts         | risk-evaluator     | uncertainty explicitly modeled          |
| `adaptive-memory-manager`       | Adaptive memory optimization         | memory usage patterns     | optimized memory retrieval  | memory-manager     | critical memories preserved             |
| `optimization-validator`        | Validate optimization safety         | optimization proposals    | validation verdicts         | validator          | regressions forbidden                   |
| `evolution-simulator`           | Simulate runtime evolution           | improvement proposals     | simulated outcomes          | simulation-engine  | unsafe evolution rejected               |
| `policy-learner`                | Learn governance improvements        | governance telemetry      | policy suggestions          | governance-engine  | human approval required                 |
| `runtime-analyst`               | Long-term runtime trend analysis     | telemetry history         | runtime trends              | metrics-engine     | statistically grounded analysis         |
| `capability-trainer`            | Improve capability-selection logic   | routing outcomes          | trained capability mappings | capability-router  | explainability required                 |
| `adaptation-auditor`            | Audit adaptive behavior              | adaptation history        | adaptation audits           | audit-logger       | full adaptation traceability            |
| `continuous-improvement-engine` | Coordinate iterative improvements    | historical execution data | improvement roadmap         | self-improvement   | cannot self-deploy changes              |
| `drift-detector`                | Detect runtime-behavior drift        | telemetry baselines       | drift reports               | diagnostics        | significant drift escalated             |
| `stability-optimizer`           | Optimize long-term runtime stability | stability metrics         | stabilization plans         | reliability-engine | stability prioritized over speed        |

---

# Human Collaboration Skills

These govern human-in-the-loop workflows, approvals, collaboration, and transparency.

| Skill                      | Responsibility                        | Inputs                  | Outputs                      | Invokes                  | Critical Rules                          |
| -------------------------- | ------------------------------------- | ----------------------- | ---------------------------- | ------------------------ | --------------------------------------- |
| `approval-manager`         | Human approval workflows              | risky actions           | approval decisions           | risk-evaluator           | mandatory for HIGH risk                 |
| `handoff-manager`          | Human-agent task transfer             | task state              | transferred tasks            | state-manager            | full context required                   |
| `feedback-integrator`      | Integrate human feedback              | user feedback           | updated execution state      | replanner                | feedback traceability required          |
| `clarification-engine`     | Clarification-request generation      | ambiguous requirements  | clarification prompts        | spec-review              | ambiguity must be explicit              |
| `review-sync`              | Human-review synchronization          | review comments         | synchronized reviews         | reviewer                 | hidden review state forbidden           |
| `override-manager`         | Controlled human overrides            | override requests       | override state               | policy-engine            | overrides fully logged                  |
| `collaboration-tracker`    | Collaboration-history tracking        | interactions            | collaboration logs           | audit-logger             | immutable collaboration history         |
| `notification-manager`     | Runtime/user notifications            | runtime events          | notifications                | alert-manager            | critical events prioritized             |
| `explanation-engine`       | Human-readable reasoning explanations | decisions               | explanations                 | decision-report          | traceable explanations only             |
| `trust-calibrator`         | Human trust calibration               | execution history       | trust recommendations        | trust-manager            | conservative trust defaults             |
| `interaction-orchestrator` | Human-agent interaction coordination  | user/runtime events     | synchronized interactions    | event-bus                | deterministic interaction ordering      |
| `approval-escalator`       | Escalate unresolved approvals         | blocked decisions       | escalated approvals          | risk-governor            | unresolved HIGH risk cannot proceed     |
| `review-assistant`         | Assist human-review workflows         | code/reports            | review summaries             | summarizer               | summaries must preserve risks           |
| `decision-explainer`       | Explain system decisions              | runtime decisions       | decision narratives          | reasoning-trace-manager  | explanation provenance required         |
| `human-context-manager`    | Human-context continuity              | user/project context    | active collaboration context | conversation-memory      | bounded context retention               |
| `collaboration-validator`  | Validate collaboration consistency    | collaboration state     | collaboration reports        | validator                | inconsistent collaboration blocked      |
| `meeting-summarizer`       | Summarize collaboration sessions      | meetings/discussions    | summaries/action items       | summarizer               | action-item extraction mandatory        |
| `consent-manager`          | Manage user approvals/consent         | approval policies       | consent states               | policy-engine            | explicit consent required               |
| `escalation-manager`       | Coordinate human escalation workflows | runtime escalations     | escalated actions            | notification-manager     | escalation traceability mandatory       |
| `human-feedback-memory`    | Persist human feedback history        | review feedback         | reusable feedback memory     | project-memory           | validated feedback only                 |
| `alignment-explainer`      | Explain alignment/safety decisions    | policy decisions        | alignment explanations       | ethics-guard             | transparent safety reasoning            |
| `interactive-debugger`     | Collaborative debugging workflows     | runtime failures        | debugging sessions           | diagnostics              | debugging history preserved             |
| `human-priority-manager`   | Prioritize human instructions         | user directives         | prioritized execution        | scheduler                | human directives logged                 |
| `collaboration-analytics`  | Analyze collaboration effectiveness   | interaction telemetry   | collaboration metrics        | metrics-engine           | privacy-preserving analytics            |
| `communication-router`     | Route collaboration communications    | messages/events         | routed communication         | interaction-orchestrator | deterministic routing required          |
| `stakeholder-manager`      | Multi-stakeholder coordination        | stakeholder inputs      | coordinated decisions        | approval-manager         | conflicting stakeholder input escalated |
| `transparency-engine`      | Runtime transparency governance       | runtime actions         | transparency reports         | audit-logger             | hidden critical actions forbidden       |
| `guidance-engine`          | Provide workflow guidance             | runtime state           | actionable guidance          | explanation-engine       | guidance must be evidence-based         |
| `session-facilitator`      | Coordinate collaborative sessions     | collaborative workflows | facilitated sessions         | interaction-orchestrator | collaboration consistency required      |
| `human-safety-guard`       | Protect against unsafe human actions  | override requests       | safety verdicts              | safety-controller        | unsafe overrides blocked                |
# Simulation & Testing Environment Skills

These manage simulation environments, synthetic testing, dry-run execution, sandbox experimentation, and scenario validation.

| Skill                      | Responsibility                       | Inputs                 | Outputs                       | Invokes                   | Critical Rules                      |
| -------------------------- | ------------------------------------ | ---------------------- | ----------------------------- | ------------------------- | ----------------------------------- |
| `simulation-engine`        | Dry-run/simulation execution         | plans/tasks            | simulated outcomes            | planner                   | no real mutations                   |
| `scenario-generator`       | Synthetic-scenario generation        | specs/risk models      | test scenarios                | test-design               | realistic edge cases required       |
| `sandbox-runtime`          | Isolated testing runtime             | execution requests     | isolated execution            | sandbox-enforcer          | strict isolation mandatory          |
| `load-simulator`           | High-load/runtime simulation         | workload models        | load-test results             | throughput-manager        | reproducible simulations            |
| `chaos-engine`             | Failure/chaos testing                | runtime systems        | resilience reports            | diagnostics               | production safeguards required      |
| `fault-injector`           | Controlled failure injection         | runtimes/services      | injected faults               | chaos-engine              | bounded failure scope               |
| `traffic-simulator`        | Synthetic traffic generation         | traffic models         | traffic streams               | load-balancer             | deterministic replay supported      |
| `integration-simulator`    | Cross-system integration simulation  | integrations/APIs      | simulated integrations        | integration-validator     | external side effects blocked       |
| `deployment-simulator`     | Deployment dry-run testing           | deployment plans       | simulated deployments         | deployment-validator      | destructive actions prohibited      |
| `runtime-emulator`         | Runtime-environment emulation        | runtime configs        | emulated runtime              | environment-manager       | environment parity required         |
| `state-simulator`          | Runtime-state evolution simulation   | state transitions      | simulated states              | state-manager             | state consistency enforced          |
| `adversarial-simulator`    | Adversarial behavior simulation      | attack/risk models     | adversarial reports           | security-review           | adversarial coverage mandatory      |
| `recovery-simulator`       | Disaster/failure recovery simulation | recovery plans         | recovery outcomes             | disaster-recovery-manager | rollback validation required        |
| `benchmark-simulator`      | Performance benchmark simulation     | workload patterns      | benchmark projections         | benchmark-gate            | calibrated simulations only         |
| `user-behavior-simulator`  | Synthetic-user interaction modeling  | usage models           | simulated interactions        | interaction-orchestrator  | realistic behavior constraints      |
| `policy-simulator`         | Governance/policy simulation         | runtime policies       | simulated governance outcomes | policy-engine             | unsafe policies flagged             |
| `parallelism-simulator`    | Concurrent-execution simulation      | task graphs            | concurrency reports           | parallelism-validator     | race-condition detection mandatory  |
| `network-simulator`        | Distributed-network simulation       | network models         | network-behavior reports      | distributed-scheduler     | partition/failure modeling required |
| `latency-simulator`        | Runtime-latency simulation           | execution traces       | latency projections           | latency-monitor           | worst-case analysis mandatory       |
| `capacity-simulator`       | Capacity/scaling simulation          | workload forecasts     | capacity projections          | capacity-planner          | infrastructure ceilings enforced    |
| `simulation-validator`     | Simulation-result validation         | simulation outputs     | validation reports            | validator                 | unrealistic simulations rejected    |
| `synthetic-data-generator` | Generate synthetic datasets          | schemas/models         | synthetic data                | data-validator            | no sensitive-data leakage           |
| `experiment-orchestrator`  | Coordinate controlled experiments    | experiments/configs    | experiment results            | simulation-engine         | reproducibility required            |
| `what-if-analyzer`         | Hypothetical-outcome analysis        | alternative strategies | projected outcomes            | reasoning-controller      | uncertainty explicitly modeled      |
| `staging-manager`          | Staging-environment coordination     | deployments/builds     | staged systems                | deployment-orchestrator   | production isolation mandatory      |
| `test-environment-manager` | Testing-environment lifecycle        | test configs           | managed test environments     | sandbox-runtime           | reproducible environments required  |
| `simulation-telemetry`     | Simulation telemetry collection      | simulation metrics     | simulation analytics          | telemetry-manager         | telemetry consistency required      |
| `rollback-simulator`       | Rollback-safety simulation           | rollback plans         | rollback forecasts            | rollback-manager          | irreversible rollback rejected      |
| `stress-tester`            | Extreme-condition testing            | stress models          | stress-test reports           | chaos-engine              | resource protection mandatory       |
| `resilience-evaluator`     | Runtime-resilience analysis          | simulation outcomes    | resilience scores             | reliability-engine        | catastrophic weaknesses escalated   |

---

# Economic & Resource Governance Skills

These manage runtime costs, compute efficiency, token budgets, resource allocation, and economic optimization.

| Skill                          | Responsibility                         | Inputs                   | Outputs                      | Invokes               | Critical Rules                       |
| ------------------------------ | -------------------------------------- | ------------------------ | ---------------------------- | --------------------- | ------------------------------------ |
| `budget-manager`               | Runtime/token governance               | usage metrics            | budget decisions             | model-router          | hard ceilings enforced               |
| `cost-analyzer`                | Runtime-cost analysis                  | usage telemetry          | cost reports                 | metrics-engine        | accurate accounting required         |
| `resource-allocator`           | Resource allocation management         | workloads/resources      | allocation plans             | scheduler             | starvation forbidden                 |
| `compute-optimizer`            | Compute-efficiency optimization        | runtime telemetry        | optimized compute usage      | throughput-manager    | bounded optimization only            |
| `token-economy-manager`        | Token-budget governance                | token usage              | token allocation             | reasoning-controller  | runaway token usage blocked          |
| `priority-allocator`           | Priority-based resource allocation     | task priorities          | prioritized execution        | scheduler             | critical workloads prioritized       |
| `quota-manager`                | Runtime quota enforcement              | quotas/usage             | quota verdicts               | policy-engine         | quota violations blocked             |
| `resource-forecaster`          | Resource-demand prediction             | telemetry history        | resource forecasts           | capacity-planner      | uncertainty modeled explicitly       |
| `cost-predictor`               | Cost forecasting                       | workload forecasts       | projected costs              | optimization-engine   | conservative estimates preferred     |
| `efficiency-validator`         | Runtime-efficiency validation          | runtime metrics          | efficiency reports           | validator             | severe inefficiency escalated        |
| `utilization-monitor`          | Resource-utilization monitoring        | runtime telemetry        | utilization reports          | resource-monitor      | idle-resource detection mandatory    |
| `throughput-economist`         | Throughput/cost tradeoff optimization  | workload metrics         | optimized throughput         | throughput-manager    | stability prioritized over speed     |
| `cache-economy-manager`        | Cache-cost optimization                | cache telemetry          | optimized caching            | knowledge-cache       | stale caches invalidated             |
| `scaling-economist`            | Infrastructure scaling optimization    | scaling telemetry        | scaling strategies           | autoscaler            | overprovisioning minimized           |
| `runtime-accountant`           | Runtime resource accounting            | execution telemetry      | accounting records           | audit-logger          | immutable accounting logs            |
| `compute-scheduler`            | Compute-aware scheduling               | workloads/budgets        | compute schedules            | distributed-scheduler | budget-aware execution mandatory     |
| `energy-efficiency-manager`    | Energy-aware execution optimization    | resource metrics         | energy-efficient execution   | compute-optimizer     | efficiency balanced with performance |
| `capacity-economist`           | Capacity/cost balancing                | infrastructure forecasts | capacity strategies          | capacity-planner      | resilience requirements preserved    |
| `resource-arbitrator`          | Resolve resource contention            | competing workloads      | arbitration decisions        | scheduler             | fairness guarantees required         |
| `cost-governor`                | Runtime cost-governance enforcement    | runtime costs            | governance decisions         | policy-engine         | runaway costs halted                 |
| `economic-simulator`           | Resource/cost simulation               | workload models          | economic forecasts           | simulation-engine     | realistic assumptions required       |
| `resource-auditor`             | Resource-usage auditing                | telemetry/history        | audit reports                | audit-logger          | traceable resource accounting        |
| `optimization-economist`       | Cost-aware optimization proposals      | runtime telemetry        | optimization recommendations | self-improvement      | regressions forbidden                |
| `latency-cost-balancer`        | Latency/cost balancing                 | runtime metrics          | balanced execution strategy  | latency-monitor       | latency SLAs preserved               |
| `resource-reservation-manager` | Reserved-resource governance           | reservations             | reserved allocations         | resource-allocator    | reservation conflicts forbidden      |
| `budget-forecast-engine`       | Long-term budget forecasting           | historical telemetry     | budget forecasts             | metrics-engine        | uncertainty explicitly modeled       |
| `runtime-throttler`            | Budget-aware throttling                | usage telemetry          | throttled execution          | throttle-manager      | graceful degradation required        |
| `idle-resource-reclaimer`      | Reclaim unused resources               | utilization reports      | reclaimed capacity           | cleanup-manager       | active workloads protected           |
| `economic-policy-engine`       | Resource-governance policy enforcement | governance rules         | economic policies            | governance-engine     | policy consistency mandatory         |
| `fairness-controller`          | Fair-resource distribution             | workload priorities      | fairness-adjusted execution  | scheduler             | starvation prevention mandatory      |
# Workflow & Process Automation Skills

These govern reusable workflows, process templates, automation pipelines, orchestration patterns, and execution lifecycle management.

| Skill                        | Responsibility                        | Inputs                  | Outputs                | Invokes               | Critical Rules                    |
| ---------------------------- | ------------------------------------- | ----------------------- | ---------------------- | --------------------- | --------------------------------- |
| `workflow-engine`            | Execute workflow graphs               | workflow definitions    | workflow execution     | scheduler             | deterministic workflows required  |
| `workflow-template-manager`  | Reusable workflow-template governance | workflow templates      | managed templates      | workflow-engine       | version-controlled templates only |
| `pipeline-orchestrator`      | Multi-stage pipeline coordination     | execution pipelines     | orchestrated execution | sdlc                  | stage-order integrity mandatory   |
| `automation-manager`         | Automation lifecycle management       | automation rules        | active automations     | policy-engine         | unsafe automation blocked         |
| `trigger-engine`             | Event-triggered workflow activation   | runtime events          | triggered workflows    | event-bus             | deterministic trigger ordering    |
| `workflow-validator`         | Workflow correctness validation       | workflow graphs         | validation reports     | validator             | cyclic workflows rejected         |
| `process-coordinator`        | Multi-process coordination            | process states          | synchronized processes | runtime-synchronizer  | process isolation required        |
| `task-dispatcher`            | Task distribution/orchestration       | runnable tasks          | dispatched tasks       | scheduler             | dependency order preserved        |
| `execution-pipeline-manager` | Pipeline execution governance         | execution stages        | managed pipelines      | pipeline-orchestrator | failed stages halt pipelines      |
| `automation-scheduler`       | Scheduled automation execution        | schedules/events        | scheduled runs         | scheduler             | missed schedules logged           |
| `workflow-checkpointer`      | Workflow-state persistence            | workflow state          | checkpoints            | checkpoint-manager    | recoverable workflows mandatory   |
| `process-validator`          | Process-integrity validation          | process state           | process verdicts       | validator             | inconsistent processes halted     |
| `event-trigger-router`       | Trigger-event routing                 | runtime events          | routed triggers        | trigger-engine        | duplicate triggers prevented      |
| `state-transition-manager`   | Workflow-state transition governance  | workflow states         | valid transitions      | phase-manager         | illegal transitions blocked       |
| `execution-router`           | Route execution flows                 | execution metadata      | routed execution       | workflow-engine       | deterministic routing required    |
| `automation-auditor`         | Automation-history auditing           | automation telemetry    | audit reports          | audit-logger          | immutable automation logs         |
| `pipeline-optimizer`         | Pipeline-performance optimization     | pipeline telemetry      | optimized pipelines    | optimization-engine   | workflow semantics preserved      |
| `retry-orchestrator`         | Workflow retry coordination           | failed stages           | retry execution        | retry-controller      | bounded retries enforced          |
| `handoff-coordinator`        | Cross-stage handoff management        | workflow outputs        | synchronized handoffs  | handoff-manager       | artifact consistency required     |
| `parallel-workflow-manager`  | Concurrent-workflow governance        | workflow DAGs           | parallel workflows     | parallelism-manager   | conflicting workflows isolated    |
| `dependency-gatekeeper`      | Workflow-dependency enforcement       | task dependencies       | gated execution        | dependency-resolver   | unsatisfied dependencies blocked  |
| `automation-policy-engine`   | Workflow-governance enforcement       | workflow policies       | policy verdicts        | policy-engine         | non-compliant workflows denied    |
| `execution-recorder`         | Workflow-execution recording          | execution events        | execution history      | audit-logger          | full workflow traceability        |
| `rollback-orchestrator`      | Workflow rollback coordination        | rollback requests       | rollback execution     | rollback-manager      | partial rollback forbidden        |
| `workflow-analytics-engine`  | Workflow telemetry analysis           | workflow metrics        | analytics reports      | metrics-engine        | bottleneck analysis mandatory     |
| `dynamic-workflow-adapter`   | Adaptive workflow modification        | runtime telemetry       | adapted workflows      | adaptive-planner      | invariants preserved              |
| `process-isolation-manager`  | Process-boundary enforcement          | concurrent processes    | isolated processes     | sandbox-enforcer      | cross-process leakage forbidden   |
| `orchestration-monitor`      | Workflow/orchestration monitoring     | orchestration telemetry | orchestration reports  | health-monitor        | stuck workflows escalated         |
| `job-lifecycle-manager`      | Job lifecycle governance              | jobs/execution state    | managed jobs           | task-queue            | orphan jobs forbidden             |
| `workflow-recovery-engine`   | Workflow failure recovery             | failed workflows        | recovered workflows    | replanner             | deterministic recovery required   |

---

# Compliance, Governance & Audit Skills

These govern regulatory compliance, auditability, governance enforcement, accountability, and policy adherence.

| Skill                         | Responsibility                          | Inputs                  | Outputs                       | Invokes                | Critical Rules                         |
| ----------------------------- | --------------------------------------- | ----------------------- | ----------------------------- | ---------------------- | -------------------------------------- |
| `compliance-checker`          | Policy/spec compliance validation       | runtime state           | compliance reports            | validator              | governance enforcement mandatory       |
| `governance-engine`           | Runtime governance coordination         | governance configs      | governance actions            | policy-engine          | policy consistency required            |
| `audit-logger`                | Immutable audit logging                 | runtime actions         | audit trails                  | archive-manager        | append-only logs                       |
| `audit-validator`             | Audit-trail integrity validation        | audit records           | validation reports            | validator              | tampered audits rejected               |
| `regulation-manager`          | Regulatory-rule governance              | compliance rules        | enforced regulations          | compliance-checker     | outdated regulations rejected          |
| `policy-enforcer`             | Runtime-policy enforcement              | runtime actions         | enforcement verdicts          | policy-engine          | deny-by-default policies               |
| `traceability-engine`         | End-to-end traceability management      | artifacts/events        | traceability graph            | lineage-tracker        | full provenance required               |
| `risk-governor`               | System-wide risk governance             | runtime risks           | mitigation decisions          | risk-evaluator         | HIGH-risk escalation mandatory         |
| `evidence-manager`            | Audit-evidence preservation             | logs/artifacts          | preserved evidence            | archive-manager        | evidence immutability mandatory        |
| `compliance-reporter`         | Compliance-report generation            | audit/compliance data   | compliance reports            | compliance-report      | audit-ready reporting required         |
| `governance-validator`        | Governance-consistency validation       | governance state        | validation verdicts           | invariant-checker      | conflicting governance blocked         |
| `retention-policy-manager`    | Data/artifact retention governance      | retention rules         | retention actions             | data-retention-manager | policy-compliant retention mandatory   |
| `privacy-governor`            | Privacy-policy governance               | sensitive data          | privacy verdicts              | data-loss-prevention   | unauthorized exposure blocked          |
| `consent-auditor`             | Consent-history validation              | consent records         | consent audits                | consent-manager        | explicit consent traceability required |
| `accountability-engine`       | Responsibility/accountability tracking  | runtime actions         | accountability records        | audit-logger           | actor attribution mandatory            |
| `legal-compliance-engine`     | Legal/regulatory validation             | runtime operations      | legal-compliance verdicts     | compliance-checker     | legal violations escalated             |
| `ethics-review-board`         | Ethical-governance analysis             | runtime decisions       | ethical verdicts              | ethics-guard           | unethical behavior blocked             |
| `governance-orchestrator`     | Governance-subsystem coordination       | governance states       | coordinated governance        | meta-orchestrator      | governance synchronization required    |
| `policy-version-manager`      | Policy-version governance               | policies/rules          | versioned policies            | archive-manager        | immutable policy history               |
| `audit-replay-engine`         | Replay historical audit trails          | audit logs              | replayed audits               | replay-memory          | deterministic replay required          |
| `certification-manager`       | Certification/compliance tracking       | certifications          | certification status          | compliance-reporter    | expired certifications invalid         |
| `data-sovereignty-manager`    | Jurisdictional-data governance          | data locality rules     | sovereignty verdicts          | privacy-governor       | cross-region violations blocked        |
| `governance-analytics-engine` | Governance telemetry analysis           | governance metrics      | governance insights           | metrics-engine         | governance drift detection mandatory   |
| `risk-audit-engine`           | Risk-focused audit analysis             | risk telemetry          | audit findings                | diagnostics            | unresolved risks escalated             |
| `transparency-validator`      | Transparency/compliance validation      | runtime actions         | transparency reports          | transparency-engine    | hidden critical actions rejected       |
| `chain-of-custody-manager`    | Artifact custody tracking               | sensitive artifacts     | custody chains                | provenance-engine      | immutable custody tracking             |
| `compliance-simulator`        | Simulate governance/compliance outcomes | policy changes          | simulated compliance outcomes | simulation-engine      | unsafe policies flagged                |
| `disclosure-manager`          | Disclosure/reporting governance         | disclosure requirements | managed disclosures           | audit-reporter         | mandatory disclosures enforced         |
| `oversight-coordinator`       | Human/regulatory oversight coordination | oversight requests      | coordinated oversight         | approval-manager       | oversight actions logged               |
| `trust-governance-engine`     | Trust/reputation governance             | trust metrics           | governance decisions          | trust-manager          | trust manipulation forbidden           |

---

# Final Runtime Shape

## Public Layer (User-Facing)

```text id="n2lmga"
build
debug
review
architect
test
document
optimize
secure
research
```

---

## Internal Runtime Layer

```text id="q3nqqf"
100+ specialized orchestration/runtime skills
```

---

# Architectural Principle

## Users interact with:

* workflows
* goals
* outcomes
* engineering intent

## The runtime internally manages:

* orchestration
* retries
* consensus
* validation
* governance
* memory
* observability
* distributed execution
* safety
* compliance
* optimization
* recovery

This separation gives:

* stable UX
* hidden implementation freedom
* deterministic orchestration
* modular scaling
* safer long-term evolution
* enterprise-grade runtime governance