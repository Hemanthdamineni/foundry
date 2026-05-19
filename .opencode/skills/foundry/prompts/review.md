You are in the **Review** phase. Your goal is to review the code for issues.

Output must include these sections (required for schema validation):
- `## Issues Found` - numbered list of issues with file/line references
- `## Severity` - CRITICAL (blocks merge), WARNING, NOTE per issue
- `## Must Fix` - subset of CRITICAL issues with concrete fix suggestions

Check for:
- Correctness and logic errors
- Security vulnerabilities
- Performance issues
- Style and convention violations
- Missing edge cases
- Test coverage
- Spec alignment: every requirement must be implemented

If CRITICAL issues exist, they must be fixed in Coding before proceeding.
Be thorough. This is a quality gate.
