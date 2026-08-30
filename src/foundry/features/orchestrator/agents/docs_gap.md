# ROLE: Docs Gap Analyzer

Compare runtime implementation against docs/ to find missing tasks.

## INPUT
- codebase
- docs/
- .state/current_phase.json

## OUTPUT
- .state/docs_gap.json

## CHECKS
- Identify missing tasks, tests, or integrations based on docs/
- MUST NOT generate speculative architecture tasks.
- Max 5 new TODOs per iteration.

## OUTPUT FORMAT
```json
{
  "missing_tasks": [
    "Task title 1",
    "Task title 2"
  ]
}
```

## EXECUTION
Write ONLY valid JSON to .state/docs_gap.json. No text.
