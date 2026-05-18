# Quality Standards

## Code Quality
- All new code must have tests
- Lint clean (ruff check .)
- Type-check clean (mypy .)
- Line length ≤ 100 characters

## SDLC Phase Quality
- **Specs**: Complete requirements, clear scope, documented constraints
- **Planning**: Feasible plan with identified risks and file changes
- **Coding**: Correct, secure, idiomatic code following project conventions
- **Review**: Thorough analysis with specific issues and severity classification
- **Testing**: Adequate coverage with meaningful assertions

## Review Criteria
Code reviews check for:
1. Correctness — does the code do what it should?
2. Security — any vulnerabilities or unsafe patterns?
3. Style — consistent with project conventions?
4. Edge cases — error states and boundary conditions handled?
5. Testing — adequate test coverage?

## Determinism
- Context retrieval is deterministic (no embeddings/LLM calls)
- Phase transitions are deterministic (FSM with no side effects)
- Schema checks are deterministic (structural validation only)
- Debate consensus has a deterministic fallback (majority vote)
