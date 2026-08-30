You are in the **Done** phase. Your goal is to summarize what was accomplished, document key decisions and known issues, and formally complete the task.

## Phase Purpose
- Provide a clear summary of what was built or changed
- Document key architectural and design decisions made during implementation
- Record known issues, limitations, or technical debt for future reference
- Formally mark the task as complete in the SDLC tracker

## Input Requirements
- All previous phase outputs (specs, plan, code, review, testing)
- Final state of the codebase

## Output Format

No strict schema validation for Done phase (free-form). Your output SHOULD include:

### `## Summary`
- One-paragraph overview of what was accomplished
- Link back to the original task description

### `## What Was Built`
- List of features implemented or changes made
- For each: brief description and key file(s) involved
- Format:
  ```
  - User registration API (`src/handlers/user_handler.py`)
  - Email validation utility (`src/utils/validation.py`)
  - Unit tests with 95% coverage (`tests/`)
  ```

### `## Key Decisions`
- Important architectural or design decisions made during the task
- Rationale for each decision
- Format:
  ```
  - SQLite chosen over PostgreSQL for MVP simplicity
  - JWT tokens over session-based auth for stateless scaling
  ```

### `## Known Issues`
- Bugs or limitations that were not fixed
- Performance concerns identified but not addressed
- Technical debt introduced
- Format:
  ```
  - Input validation on PATCH endpoints is minimal
  - No rate limiting implemented
  - Email format validation may reject some international addresses
  ```

### `## Future Considerations`
- Recommended follow-up work
- Scalability concerns for production
- Suggested improvements for next iteration

## Rules
1. **Be honest about known issues.** Do not hide limitations — they are essential information for the next task.
2. **Do NOT make additional code changes.** The Done phase is for documentation only.
3. **Reference specific files and line numbers** where applicable.
4. **Be concise but complete.** This summary serves as the task's permanent record.

## Error Handling
- If some requirements were not met, document them under `## Known Issues` or `## Out of Scope`
- If the task was cancelled or partially completed, note this clearly in the summary

## Transition Criteria
The task is complete. Call `sdlc_submit_output(task_id, phase="done", output=...)` to persist the summary.
- No further phase transitions occur after Done
- Task status changes to "completed" in SQLite

## Common Pitfalls
- ❌ Forgetting to call `sdlc_submit_output` — the task remains "active" in SQLite
- ❌ Making last-minute code changes — Done is for documentation, not implementation
- ❌ Being overly positive and hiding issues — known issues help the next developer
- ❌ Being too verbose — the summary should be skimmable, not a novel
- ❌ Omitting future considerations — context for the next task saves time
