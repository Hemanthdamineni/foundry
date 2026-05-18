# Quality Definition

## Definition of Done
A task is "Done" when ALL of the following are true:
1. All spec requirements have corresponding implementations
2. All CRITICAL review issues are resolved
3. All tests pass with coverage ≥ 80%
4. Code passes lint (ruff) and type checking (mypy)
5. Git commit created with phase history
6. No unresolved security findings

## Quality Gates
- **Specs → Planning**: Requirements, Scope, Constraints sections present
- **Planning → Coding**: Implementation Plan, File Changes, Risks sections present
- **Coding → Review**: Files exist on disk, parse without errors
- **Review → Testing**: All Must Fix issues have test stubs
- **Testing → Done**: All tests pass, coverage ≥ threshold

## Review Standards
- Every requirement maps to implementation
- No scope creep beyond spec
- Error handling explicit — no swallowed exceptions
- Security considerations addressed
- Architecture matches plan

## Debate Standards
- 3-round protocol: independent → cross-exposure → residual objections
- Minority reports preserved (not averaged away)
- Sycophantic collapse flagged if all agents converge identically
- Stalemate escalated to judge
