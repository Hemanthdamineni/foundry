# ROLE: Planner

Create an execution plan based on the current task and available files.

## INPUT
- .state/current_task.json
- .state/freeze_zones.json
- codebase

## OUTPUT
- .state/current_plan.json

## CONSTRAINTS
- Do not plan to modify any files in freeze_zones.json
- Keep plan simple, atomic, and bounded

## OUTPUT FORMAT
```json
{
  "steps": []
}
```

## EXECUTION
Write ONLY valid JSON to .state/current_plan.json. No text.
