# Final Priority TODOs (Core Architecture)

These are the foundational items required before the system can reliably function as a true autonomous engineering system.

---

# P0 — Critical / Foundational TODOs

---

## 1. Pre-Spec Context Harvesting System

### Goal

Make the system ask every important question before spec approval and never require human clarification afterward.

### Must Include

* Requirement interrogation
* Constraint extraction
* Environment analysis
* Deployment assumptions
* Edge-case questioning
* Scalability expectations
* Risk tolerance
* Architecture preferences
* Dependency expectations
* Coding standards detection

### Required Outputs

```text id="7nr14o"
context_bundle.json
resolved_requirements.md
```

### Critical Rule

After:

```text id="j99vfw"
SPEC_APPROVED = TRUE
```

Then:

```text id="n8qeh9"
NO HUMAN QUESTIONS ALLOWED
```

Only:

* autonomous replanning
* autonomous compromises
* autonomous recovery

This directly addresses:

* “Make it ask questions”
* “Make implementation questions happen before specs”



---

## 2. Hierarchical Iterative Execution Engine

### Goal

Replace waterfall coding with iterative implementation loops.

### Required Architecture

```text id="m2muvs"
SPEC
→ SYSTEM_PHASES
    → IMPLEMENTATION_PHASES
        → MICRO_TASKS
```

### Required Execution Pattern

```text id="18f2v0"
IMPLEMENT_PHASE
→ LOCAL_TEST
→ REVIEW
→ INTEGRATION_TEST
→ REGRESSION_TEST
→ CHECKPOINT
→ NEXT_PHASE
```

### Required Properties

* Incremental execution
* Incremental stabilization
* Progressive integration
* Progressive regression protection
* Localized failures
* Safe convergence

### This Fixes

* Single-pass execution
* Giant implementation bursts
* Late integration failures
* Context overload

This is the most important architectural upgrade.



---

## 3. Multi-Level Testing Architecture

### Goal

Guarantee stability at every implementation layer.

### Required Test Layers

#### Unit Testing

Component correctness.

#### Integration Testing

Inter-component compatibility.

#### System Testing

Full workflow correctness.

#### Regression Testing

Prevent old feature breakage.

#### Property/Fuzz Testing

Edge-case discovery.

#### Benchmark Testing

Performance stability.

#### Security Testing

Vulnerability prevention.

### Required Trigger Rules

After every implementation phase:

```text id="4n5d95"
RUN:
- integration tests
- regression tests
- stability checks
```

### Required Tools

* pytest
* hypothesis
* playwright
* coverage
* benchmarks
* fuzzers
* semgrep
* bandit

This directly addresses:

* “write test files whenever possible”



---

## 4. Judge & Validation Hierarchy

### Goal

Make approvals trustworthy.

### Required Judge Layers

#### Tool Judges

Objective truth.

#### Semantic Judges

Spec alignment.

#### Architecture Judges

Long-term maintainability.

#### Security Judges

Security correctness.

#### Risk Judges

Operational safety.

#### Integration Judges

Cross-module stability.

### Critical Rule

```text id="wmdg5q"
NO SINGLE JUDGE MAY APPROVE ALONE
```

### Required Consensus

```text id="g6xvns"
TOOLS
+ REVIEWERS
+ ARCHITECTURE_JUDGES
```

### This Fixes

* Weak judge agents
* Premature approvals
* Incorrect merges

Directly addresses:

* “Make sure the Judge agents work properly”



---

## 5. Parallel Subagent Coordination System

### Goal

Enable real multi-team execution safely.

### Required Subteams

```text id="43x3zs"
Planning Team
Backend Team
Frontend Team
Testing Team
Security Team
Integration Team
Documentation Team
Review Team
Benchmark Team
```

### Required Features

* Dependency-aware scheduling
* Path locking
* Merge coordination
* Conflict prediction
* Parallel implementation
* Parallel reviews
* Parallel test generation

### Required Debate Types

* Architecture debates
* Security debates
* API debates
* Refactor debates
* Merge debates

### This Fixes

* Weak parallelism
* Underutilized subagents
* Sequential bottlenecks

Directly addresses:

* “properly use subagents for parallel execution and debates”



---

## 6. Autonomous Failure Recovery & Replanning Engine

### Goal

Allow unattended recovery from failures.

### Required Recovery Layers

#### Local Retry

Small implementation fixes.

#### Local Replan

Rebuild current implementation phase.

#### Structural Replan

Rebuild downstream plan.

#### Full Recovery

Rollback + restore.

### Required Rules

```text id="wul62m"
LOCALIZE FAILURES FIRST
```

Avoid:

```text id="c9y69l"
FULL SYSTEM REPLANS
```

unless necessary.

### Required Triggers

* repeated failures
* integration instability
* architecture conflicts
* benchmark collapse
* unresolved review loops

---

## 7. Persistent Execution State Machine

### Goal

Enable week-long autonomous execution safely.

### Must Persist

* current phase
* implementation stage
* retries
* validators
* benchmarks
* integration state
* unresolved risks
* branch state
* checkpoints

### Required Files

```text id="3hn2h5"
state.json
task_state.json
phase_state.json
integration_state.json
```

### Required Recovery Behavior

```text id="h3rkpo"
RESUME EXACTLY
FROM LAST STABLE CHECKPOINT
```

---

## 8. Atomic Git & Checkpoint System

### Goal

Make every implementation step recoverable.

### Required Behavior

After each stable implementation phase:

```text id="04pnzs"
COMMIT
→ TAG
→ SNAPSHOT
→ CHECKPOINT
```

### Required Commit Rules

* atomic commits
* phase-scoped commits
* validated commits
* rollback-safe commits

### Required Repository Behavior

```text id="a1rn14"
INITIALIZE_GIT_REPO_ALWAYS
```

### Required Features

* branch-per-task
* branch-per-phase
* deterministic rollback
* replayable history

Directly addresses:

* “initialize git repo everytime”
* “make atomic github commits”

---

## 9. Incremental Validation Pipeline

### Goal

Continuously stabilize the system.

### Required Validation Levels

#### Per Microtask

* syntax
* lint
* local tests

#### Per Implementation Phase

* integration
* security
* architecture checks

#### Per Milestone

* regression
* benchmark
* system tests

### Critical Rule

```text id="e0djx8"
NO PHASE MAY CONTINUE UNLESS CURRENT STATE IS STABLE
```

---

## 10. Structured Progress Tracking System

### Goal

Measure convergence explicitly.

### Required Metrics

* tests fixed
* new failures
* coverage delta
* retry effectiveness
* regression count
* benchmark trends
* unresolved issues
* integration stability

### Required Outputs

```json id="c46rwi"
{
  "phase_progress": 0.74,
  "integration_stability": 0.91,
  "retry_effectiveness": 0.67
}
```

This prevents orchestrator guessing.



---

## 11. Repository Understanding & Indexing Phase

### Goal

Understand the repository before planning.

### Required Capabilities

* dependency graph extraction
* architecture discovery
* API mapping
* test discovery
* module ownership
* hotspot analysis
* complexity analysis

### Required Outputs

```text id="yp21jp"
repo_graph.json
architecture_map.json
dependency_graph.json
```



---

## 12. Spec-Locked Autonomous Decision System

### Goal

Prevent silent requirement drift.

### Required Rule

After spec approval:

```text id="cn87bd"
NO REQUIREMENT CHANGES
```

Allowed:

* implementation adaptation
* architecture adaptation
* execution adaptation

Not allowed:

* hidden feature changes
* hidden scope expansion

---

## 13. Sandbox & Isolation System

### Goal

Safely execute autonomous operations.

### Required Features

* Docker isolation
* resource quotas
* process isolation
* network policy control
* ephemeral workspaces
* execution sandboxes

### Required Policies

* CPU limits
* memory limits
* filesystem isolation
* timeout enforcement



---

## 14. Runtime Observability & Dashboard System

### Goal

Monitor long autonomous runs.

### Must Track

* current phase
* retries
* integration stability
* validator health
* benchmark trends
* queue state
* model utilization
* confidence trends

### Required Outputs

```text id="o8i7m6"
live_dashboard.json
execution_timeline.json
```



---

## 15. Policy & Config Framework

### Goal

Allow user customization safely.

### Required Config Files

```text id="y9e4p7"
policy.yaml
runtime_config.yaml
models.yaml
validators.yaml
skills.yaml
mcps.yaml
```

### Required Config Areas

* autonomy level
* retry budgets
* strictness levels
* model routing
* checkpoint frequency
* benchmark thresholds
* security thresholds

Directly addresses:

* “Think of a way for users to change the config”

---

# P1 — High Priority TODOs

---

## 16. Dynamic Replanning Engine

### Required Features

* downstream replanning
* preserved stable work
* selective rollback
* dependency-aware replanning

---

## 17. Continuous Regression Prevention

### Required Features

* rolling regression suite
* API contract verification
* benchmark regression detection
* compatibility checks

---

## 18. Cross-Phase Memory Compression

### Required Outputs

```text id="ydw0vg"
phase_summary.md
decision_summary.md
integration_summary.md
```

### Goal

Prevent context explosion.

---

## 19. Prompt Registry & Versioning System

### Required Features

* prompt hashing
* prompt rollback
* versioned prompts
* compatibility tracking



---

## 20. Deterministic Replay System

### Required Features

* phase replay
* execution replay
* debate replay
* checkpoint replay



---

## 21. Autonomous Test Generation Pipeline

### Required Features

* unit test synthesis
* property-based testing
* mutation testing
* fuzzing
* snapshot tests



---

## 22. Architecture Drift Detection

### Required Features

* planned vs actual comparison
* layer violation detection
* circular dependency detection
* architectural consistency scoring



---

## 23. Environment Reproducibility System

### Required Features

* deterministic environments
* dependency locking
* runtime fingerprinting
* reproducible builds



---

## 24. Long-Run Autonomous Controller

### Required Features

* pause/resume
* overnight mode
* stagnation detection
* watchdog timers
* thermal/resource awareness

---

# P2 — Medium / Non-Priority TODOs

---

## 25. Benchmark Trend Intelligence

Historical performance analysis.

---

## 26. Semantic Code Ownership

Symbol-level ownership tracking.

---

## 27. Artifact Provenance Tracking

Track:

* generating agent
* approving debate
* prompt version
* validator source



---

## 28. Capability Negotiation System

Dynamic MCP/tool compatibility management.

---

## 29. Cost & Resource Governor

Adaptive routing and token/resource budgeting.

---

## 30. Configurable Autonomy Modes

### Required Modes

```text id="o6b0e3"
FULL_AUTONOMY
REVIEW_BEFORE_MERGE
HUMAN_ON_RISK
DEBUG_MODE
EDUCATIONAL_MODE
```



---

# Comprehensive Autonomous Phase Graph

```text id="h3ffwa"
PHASE_0_CONTEXT_HARVESTING
    → ask questions
    → gather constraints
    → environment analysis
    → ambiguity resolution

PHASE_1_SPEC_GENERATION
    → SPEC.json
    → acceptance tests
    → constraints
    → risk boundaries

PHASE_2_REPOSITORY_INDEXING
    → dependency graph
    → architecture graph
    → API discovery

PHASE_3_MACRO_PLANNING
    → system phases
    → implementation roadmap
    → integration roadmap

PHASE_4_IMPLEMENTATION_PHASE_PLANNING
    → microtasks
    → local test plans
    → rollback plans

PHASE_5_IMPLEMENTATION_LOOP
    IMPLEMENT_MICROTASK
        → local lint
        → local unit tests
        → local review
        → checkpoint

PHASE_6_PHASE_INTEGRATION
    → merge
    → integration tests
    → regression tests
    → benchmark checks

PHASE_7_PHASE_REVIEW
    → semantic judges
    → architecture judges
    → security judges
    → risk judges

PHASE_8_PHASE_STABILIZATION
    → bug fixing
    → refactoring
    → optimization
    → regression validation

PHASE_9_SYSTEM_INTEGRATION
    → global integration
    → full regression
    → benchmark validation

PHASE_10_SYSTEM_VALIDATION
    → final judges
    → spec validation
    → architecture validation

PHASE_11_DOCUMENTATION
    → docs
    → READMEs
    → architecture updates

PHASE_12_FINALIZATION
    → final reports
    → completion_report.json
    → tagged release
```

---

# Required MCPs

---

## Core MCPs

### Git MCP

* repo management
* commits
* branching
* tagging
* rollback

### Filesystem MCP

* safe file operations
* snapshots
* indexing

### Terminal MCP

* tool execution
* benchmarking
* testing

### Docker MCP

* sandboxing
* isolation
* reproducibility

### Memory MCP

* long-term memory
* retrieval
* compression

### Planning MCP

* task decomposition
* dependency graphs
* execution graphs

### Observability MCP

* dashboards
* metrics
* telemetry

### Replay MCP

* deterministic replay
* checkpoint recovery

---

# Required Skills

---

## Planning Skills

* spec generation
* ambiguity detection
* architecture planning
* dependency planning

---

## Coding Skills

* backend generation
* frontend generation
* refactoring
* optimization

---

## Testing Skills

* unit test generation
* integration test generation
* regression testing
* fuzz testing
* mutation testing

---

## Review Skills

* semantic review
* architecture review
* security review
* performance review

---

## Operational Skills

* git management
* rollback management
* benchmarking
* profiling
* deployment validation

---

# Final Core Architectural Shift

Old Model:

```text id="v09h4e"
PLAN
→ CODE EVERYTHING
→ TEST EVERYTHING
→ REVIEW EVERYTHING
```

Final Autonomous Model:

```text id="b2n22u"
PLAN ONCE

FOR EACH IMPLEMENTATION_PHASE:
    → implement
    → unit test
    → review
    → integrate
    → regression test
    → stabilize
    → checkpoint
    → continue

THEN:
    → global integration
    → system validation
    → release
```

That is the transition from:

```text id="p5j4vg"
multi-agent coding assistant
```

to:

```text id="7wl2s0"
fully autonomous engineering execution system
```