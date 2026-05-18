"""Per-transition deterministic preconditions — structural checks before any LLM evaluation.

Each phase transition defines a set of required sections or artifact conditions
that must be satisfied before the orchestrator considers the output valid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from sdlc.models import FailureType


CHECK_CONTEXT_HARVESTING_SECTIONS = ["Questions", "Constraints"]


class SchemaViolationError(Exception):
    """Raised when an output fails structural validation."""

    def __init__(
        self,
        message: str,
        *,
        section: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.section = section
        self.details = details or {}
        super().__init__(message)


SchemaViolation = SchemaViolationError


def _find_section(output: str, section_heading: str) -> str | None:
    """Extract the content of a ##-style section from a phase output."""
    lines = output.splitlines()
    start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") and section_heading.lower() in stripped.lower():
            start = i
            break
    if start < 0:
        return None
    content_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("## "):
            break
        content_lines.append(line)
    return "\n".join(content_lines).strip() if content_lines else ""


def _has_min_content(output: str, min_lines: int = 3) -> bool:
    return sum(1 for line in output.splitlines() if line.strip()) >= min_lines


CHECK_SPEC_SECTIONS = ["Requirements", "Scope", "Constraints"]

CHECK_PLAN_SECTIONS = ["Implementation Plan", "File Changes", "Risks"]

CHECK_CODE_ARTIFACTS = ["Files Modified"]

CHECK_REVIEW_SECTIONS = ["Issues Found", "Severity", "Must Fix"]

CHECK_TEST_SECTIONS = ["Test Results", "Coverage", "Failed"]


def check_context_harvesting_output(output: str) -> list[SchemaViolationError]:
    """Validate ContextHarvesting phase output has required question/constraint sections."""
    violations: list[SchemaViolationError] = []
    for section in CHECK_CONTEXT_HARVESTING_SECTIONS:
        content = _find_section(output, section)
        if content is None:
            violations.append(
                SchemaViolationError(
                    f"Missing required section: ## {section}",
                    section=section,
                    details={"required_section": section},
                ),
            )
        elif not content:
            violations.append(
                SchemaViolationError(
                    f"Section ## {section} is empty",
                    section=section,
                    details={"required_section": section},
                ),
            )
    return violations


def check_specs_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    for section in CHECK_SPEC_SECTIONS:
        content = _find_section(output, section)
        if content is None:
            violations.append(
                SchemaViolationError(
                    f"Missing required section: ## {section}",
                    section=section,
                    details={"required_section": section},
                ),
            )
        elif not content:
            violations.append(
                SchemaViolationError(
                    f"Section ## {section} is empty",
                    section=section,
                    details={"required_section": section},
                ),
            )
    return violations


def check_planning_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    for section in CHECK_PLAN_SECTIONS:
        content = _find_section(output, section)
        if content is None:
            violations.append(
                SchemaViolationError(
                    f"Missing required section: ## {section}",
                    section=section,
                    details={"required_section": section},
                ),
            )
        elif not content:
            violations.append(
                SchemaViolationError(
                    f"Section ## {section} is empty",
                    section=section,
                    details={"required_section": section},
                ),
            )
    return violations


def check_coding_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    found_any = any(
        _find_section(output, artifact) is not None
        for artifact in CHECK_CODE_ARTIFACTS
    )
    if not found_any:
        violations.append(
            SchemaViolationError(
                "Output must reference specific files modified",
                section="Files Modified",
                details={"message": "No file references found in output"},
            ),
        )
    return violations


def check_review_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    for section in CHECK_REVIEW_SECTIONS:
        content = _find_section(output, section)
        if content is None:
            violations.append(
                SchemaViolationError(
                    f"Missing required section: ## {section}",
                    section=section,
                    details={"required_section": section},
                ),
            )
        elif not content:
            violations.append(
                SchemaViolationError(
                    f"Section ## {section} is empty",
                    section=section,
                    details={"required_section": section},
                ),
            )
    return violations


def check_testing_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    for section in CHECK_TEST_SECTIONS:
        content = _find_section(output, section)
        if content is None:
            violations.append(
                SchemaViolationError(
                    f"Missing required section: ## {section}",
                    section=section,
                    details={"required_section": section},
                ),
            )
        elif not content:
            violations.append(
                SchemaViolationError(
                    f"Section ## {section} is empty",
                    section=section,
                    details={"required_section": section},
                ),
            )
    return violations


def check_done_output(output: str) -> list[SchemaViolationError]:
    violations: list[SchemaViolationError] = []
    if not _has_min_content(output, min_lines=2):
        violations.append(
            SchemaViolationError(
                "Done output must include a summary of what was accomplished",
                section="Summary",
                details={"message": "Output is too brief"},
            ),
        )
    return violations


_PHASE_CHECKERS: dict[str, Callable[[str], list[SchemaViolationError]]] = {
    "ContextHarvesting": check_context_harvesting_output,
    "Specs": check_specs_output,
    "Planning": check_planning_output,
    "Coding": check_coding_output,
    "Review": check_review_output,
    "Testing": check_testing_output,
    "Done": check_done_output,
}


def validate_phase_output(phase: str, output: str) -> list[SchemaViolationError]:
    """Run the deterministic section checks for the given phase.

    Returns a list of SchemaViolationErrors. An empty list means the output
    passes all structural preconditions.
    """
    checker = _PHASE_CHECKERS.get(phase)
    if checker is None:
        return []
    return checker(output)


def violations_to_failure_type(violations: list[SchemaViolationError]) -> FailureType:
    return FailureType.TERMINAL_VALIDATION if violations else FailureType.ORCHESTRATION_LIMIT
