# Workflow Internals

MVP workflow internals are intentionally limited to the `feature` graph.

## Supported Workflow

```text
Chatting -> Specs -> Planning -> Coding -> Review -> Testing -> Done
```

`Review -> Coding` is the only MVP back edge.

The existing `Chatting -> Done` edge must not act as an accidental shortcut for
normal feature tasks. It is disabled or explicitly governed by an
early-completion policy with persisted reason and tests.

## Deferred Workflow Templates

Bugfix, docs, refactor, research, and feature-harvesting graph files may exist,
but are not operational workflow support until mode-to-graph selection,
validation, persistence, recovery, and integration tests exist for each.

## Implementation Rule

Graph file existence is not workflow readiness. A workflow is operational only
when a task can run through `submit_output`, persist accepted/rejected history,
enforce validation, checkpoint, and recover.
