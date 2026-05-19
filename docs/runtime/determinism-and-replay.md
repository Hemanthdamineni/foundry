# Determinism and Replay

MVP requires deterministic execution semantics, not advanced deterministic
replay.

## MVP Determinism

Determinism means:

- one feature FSM;
- one submit pipeline;
- one ordered validation path;
- one SQLite task authority;
- one latest-checkpoint recovery path;
- bounded retries;
- explicit failure instead of silent fallback.

## Not MVP Replay

The following are deferred:

- reconstructing historical model/tool output streams;
- replaying trace logs into equivalent runtime state;
- versioned checkpoint chain selection;
- prompt registry rollback;
- workspace/git state replay;
- regression comparison between historical runs.

Existing replay or enhanced checkpoint files are not operational MVP guarantees
until they are wired into runtime and covered by integration tests.

## MVP Validation

The required determinism tests are operational:

1. same accepted input advances the same phase;
2. invalid phase transition is rejected;
3. ToolGate order is lint, types, tests;
4. rejected gate result does not write accepted checkpoint;
5. restart/resume returns latest accepted phase;
6. SQLite/checkpoint mismatch is explicit failure.
