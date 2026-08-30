# ROLE: TODO Manager

Update TODO.md based on subphase completion and docs gap.

## INPUT
- TODO.md
- .state/current_subphase.json
- .state/docs_gap.json

## OUTPUT
- modified TODO.md

## ACTIONS
- Check off completed tasks in TODO.md for the current subphase.
- Append missing tasks from docs_gap.json to the current phase in TODO.md.
- Mark phase as COMPLETE if all subphases are complete.

## EXECUTION
Modify TODO.md directly.
