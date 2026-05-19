# Workflow Reference

> MVP workflow reference. Feature is the only supported workflow before MVP
> completion.

## Supported MVP Workflow

### Feature

```
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
                         ^                 |
                         +-- Review -> Coding
```

The host agent drives each phase using:

1. `sdlc_create_task(description, mode="feature")`
2. `sdlc_get_next_action(task_id)`
3. `sdlc_submit_output(task_id, phase, output, next_phase?)`
4. repeat until Done

## Unsupported Before MVP

These graph files may exist but are not operational workflow support:

- bugfix;
- refactor;
- research;
- docs;
- feature harvesting;
- review-only.

Until mode-specific graph selection is implemented, non-feature modes must be
rejected or clearly reported as unsupported. They must not silently run the
feature graph.

## Feature Acceptance

Feature workflow is operational only when:

- every transition goes through `submit_output`;
- schema-invalid outputs are rejected;
- Coding and Testing require ToolGate approval;
- rejected attempts remain visible;
- accepted transitions write SQLite state and latest checkpoint;
- restart/resume returns the latest accepted phase.
