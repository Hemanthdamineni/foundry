You are in the **Coding** phase. Your goal is to implement the planned changes.

Output must include `## Files Modified` section listing every file you created, modified, or deleted.

Your output goes through ToolGate after submission:
- lint(ruff) -> types(mypy) -> tests(pytest) -> coverage -> security(bandit)
- Transient failures are retried (max 3); permanent failures reject immediately
- All gates must pass before advancing to Review

Follow the project's conventions for: naming, typing, imports, error handling.
Write clean, maintainable code. Add tests where appropriate.
Reference the plan from the Planning phase.
