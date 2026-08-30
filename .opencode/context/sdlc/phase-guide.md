# SDLC Phase Guide

## Phase Outputs

### Chatting
- Classify the user request
- Determine graph template (feature, bugfix, refactor, research, docs)
- Create task via `sdlc_create_task`

### Specs
- Comprehensive requirements document
- Must include: Requirements, Scope, Constraints, Acceptance Criteria, Risks
- After approval, NO human questions allowed

### Planning
- Detailed implementation plan
- Must include: Implementation Plan, File Changes, Architecture Decisions, Risks, Testing Strategy
- Debate may trigger for architectural decisions

### Coding
- Implementation of the plan
- Must list all files modified/created/deleted
- Runs through sandbox for bash commands
- Lint and format after changes

### Review
- Critical quality review
- Must include: Issues Found, Severity, Must Fix, Spec Alignment
- If CRITICAL issues found → back to Coding
- Debate may trigger for architectural concerns

### Testing
- Write and run tests
- Must include: Test Results, Coverage, Failed tests
- All tests must pass before advancing to Done

### Done
- Task complete
- Git commit and tag
- Summary to user
