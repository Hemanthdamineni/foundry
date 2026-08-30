# Phase 0: Baseline Enforcement

## Phase Overview

**Goal:** Freeze the corrected MVP boundary in executable terms before runtime code changes begin.

**Rationale:** The project has enough scaffolded modules to create false confidence. Phase 0 prevents implementation drift by making the runtime path, supported workflow, and readiness vocabulary enforceable.

**Dependencies:** Corrected `planning/README.md`, `planning/MASTER-ROADMAP.md`, `planning/RUNTIME-SPEC.md`, `planning/DEPENDENCY-GRAPH.md`.

**Runtime impact:** No behavioral runtime change is required in this phase. It constrains all later implementation.

**Blocking systems:** None.

**Acceptance gates:**

- Planning files agree that MVP is feature-only.
- Planning files agree that `submit_output -> ToolExecutor -> ToolGate -> validation -> checkpoint -> persistence -> recovery` is the authoritative path.
- Deferred systems are not listed as MVP work.
- Non-feature workflows are not treated as operational.

## Task P0-01: Establish Execution Plan Index

**Objective:** Make this execution layer the implementation control surface for MVP work.

**Subsystem:** Planning.

**Priority:** P0.

**Dependencies:** Corrected planning baseline.

**Files/modules involved:**

- `planning/execution/PHASE-0.md`
- `planning/execution/PHASE-1.md`
- `planning/execution/PHASE-2.md`
- `planning/execution/PHASE-3.md`
- `planning/execution/PHASE-4.md`
- `planning/execution/MVP-COMPLETION.md`

**Runtime integration points:** None.

**Expected runtime behavior:** No runtime behavior changes.

**Implementation notes:** Keep execution planning in these phase files. Do not create extra phase specs unless implementation exposes a real gap.

**Failure considerations:** If these files diverge from `MASTER-ROADMAP.md`, the roadmap remains the higher-level source of truth and this layer must be corrected.

### Ordered Subtasks

1. Create `planning/execution/`.
2. Add one file per implementation phase.
3. Define each phase by runtime wiring tasks, not subsystem aspirations.
4. Link every task to concrete files and runtime integration points.
5. Keep all deferred systems out of MVP tasks.

### Runtime Invariants

- No new runtime boundary is introduced.
- The feature workflow remains the only MVP workflow.
- SQLite remains the MVP task authority.

### Validation Requirements

- Review all files for deferred-system leakage.
- Confirm no phase depends on rollback, replay, dashboard, memory, or multi-agent coordination.
- Done when all phase files exist and match corrected MVP scope.

## Task P0-02: Enforce MVP Vocabulary

**Objective:** Ensure implementation status cannot be reported as complete based only on file existence.

**Subsystem:** Planning and status reporting.

**Priority:** P0.

**Dependencies:** P0-01.

**Files/modules involved:**

- `planning/README.md`
- `planning/MASTER-ROADMAP.md`
- `planning/execution/*.md`

**Runtime integration points:** None.

**Expected runtime behavior:** No runtime behavior changes.

**Implementation notes:** Use only these status terms: `file exists`, `scaffolded`, `partially wired`, `operationally integrated`, `production-ready`, `deferred`, `non-operational concept`.

**Failure considerations:** Avoid `[x]` checklists for modules unless the module is operationally integrated.

### Ordered Subtasks

1. Scan planning files for stale readiness claims.
2. Replace module-complete phrasing with operational status.
3. Mark advanced systems deferred or non-operational where appropriate.
4. Keep MVP status tied to integration tests and runtime behavior.

### Runtime Invariants

- Operational readiness means runtime path integration.
- Production readiness is not an MVP status.

### Validation Requirements

- Search for phrases such as "fully implemented", "all implemented", and "production ready".
- Done when stale claims are absent from `planning/` and root execution docs.

## Task P0-03: Lock Feature-Only Scope

**Objective:** Prevent implementation tasks from drifting into workflow families before feature is operational.

**Subsystem:** Workflow planning.

**Priority:** P0.

**Dependencies:** P0-01.

**Files/modules involved:**

- `planning/TOOLING-AND-WORKFLOWS-SPEC.md`
- `sdlc/runtime/app.py`
- `sdlc/runtime/tools/task.py`
- `sdlc/graphs/feature.yaml`

**Runtime integration points:**

- `sdlc_create_task`
- `get_next_action`
- `submit_output`

**Expected runtime behavior:** Phase 1 implementation must either reject non-feature modes or clearly mark them unsupported until graph selection is real.

**Implementation notes:** Do not wire bugfix/refactor/research/docs in MVP. The existing graph files may remain, but they are not supported workflows.

**Failure considerations:** Accepting a mode while always loading the feature graph is a false capability and must be corrected in Phase 1.

### Ordered Subtasks

1. Keep `feature` as the only executable workflow in execution plans.
2. Include unsupported-mode correction in Phase 1.
3. Exclude workflow-specific budgets and model routing from MVP.

### Runtime Invariants

- One workflow.
- One FSM.
- One submit pipeline.

### Validation Requirements

- Done when Phase 1 includes a concrete non-feature mode handling task.
- Done when no Phase 0-4 task requires non-feature graphs.

