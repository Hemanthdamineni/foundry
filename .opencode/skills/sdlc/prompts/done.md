You are in the **Done** phase. Your goal is to summarize what was accomplished, document key decisions and known issues, and formally complete the task.

## Phase Purpose
- Provide a clear summary of what was built or changed
- Document key architectural and design decisions
- Record known issues, limitations, or technical debt
- Formally mark the task as complete

## Input Requirements
- All previous phase outputs (specs, plan, code, review, testing)
- Final state of the codebase

## Output Format

No strict schema validation for Done phase. Your output SHOULD include:

### ## Summary
- One-paragraph overview of what was accomplished
- Link back to the original task description

### ## What Was Built
- List of features implemented or changes made
- For each: description and key files involved

### ## Key Decisions
- Important architectural or design decisions
- Rationale for each

### ## Known Issues
- Bugs, limitations, or technical debt not addressed
- Be honest — this helps the next developer

### ## Future Considerations
- Recommended follow-up work
- Scalability concerns for production
- Suggested improvements

## Rules
1. **Be honest about known issues.**
2. **Do NOT make additional code changes** — Done is for documentation only.
3. **Reference specific files and line numbers** where applicable.
4. **Call `sdlc_submit_output(task_id, phase="done", output=...)`** to persist completion.

## Transition Criteria
No further transitions. Task status changes to "completed".

## Common Pitfalls
- ❌ Forgetting to call `sdlc_submit_output`
- ❌ Making last-minute code changes
- ❌ Hiding known issues
- ❌ Being too verbose or too sparse
