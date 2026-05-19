# Prompting Architecture

Prompting is not the MVP architecture driver. Prompts support the runtime; they
do not define runtime authority.

## MVP Prompt Requirements

- Phase prompts must preserve the feature FSM contract.
- Schema validation remains deterministic and runs before judge prompts.
- Judge prompts are optional/bounded and cannot advance phase directly.
- Coding/Testing acceptance remains governed by ToolExecutor and ToolGate.
- Prompt changes cannot be used to bypass validation, checkpoint, persistence,
  or recovery rules.

## Deferred Prompt Systems

Prompt registries, prompt rollback, compatibility matrices, debate prompts,
adaptive prompt routing, and prompt-replay guarantees are post-MVP unless they
are already harmless and subordinate to the submit path.

## Implementation Rule

Do not add prompt infrastructure before the deterministic feature loop is
operational. The first implementation priority is runtime wiring, not prompt
system sophistication.
