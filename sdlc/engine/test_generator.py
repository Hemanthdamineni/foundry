"""Autonomous test generation — synthesize unit tests, property tests, mutation tests.

TODO #21: Generates tests from spec requirements and code analysis.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.test_generator")


class GeneratedTest(BaseModel):
    """A single generated test case."""

    name: str
    test_type: str  # unit, property, mutation, fuzz, snapshot
    target_function: str = ""
    target_file: str = ""
    test_code: str = ""
    requirement_ref: str = ""
    priority: str = "medium"


class TestPlan(BaseModel):
    """A complete test generation plan."""

    task_id: str
    tests: list[GeneratedTest] = Field(default_factory=list)
    coverage_targets: dict[str, float] = Field(default_factory=dict)
    status: str = "pending"

    @property
    def by_type(self) -> dict[str, list[GeneratedTest]]:
        result: dict[str, list[GeneratedTest]] = {}
        for t in self.tests:
            result.setdefault(t.test_type, []).append(t)
        return result


class TestGenerator:
    """Generates test cases from spec requirements and code structure."""

    def __init__(self) -> None:
        self._plans: dict[str, TestPlan] = {}

    def generate_from_spec(
        self,
        task_id: str,
        spec_output: str,
        code_output: str = "",
    ) -> TestPlan:
        """Generate test plan from spec requirements and code output."""
        plan = TestPlan(task_id=task_id)

        # Extract requirements from spec
        requirements = self._extract_requirements(spec_output)
        files_modified = self._extract_files(code_output)

        # Generate unit tests for each requirement
        for i, req in enumerate(requirements):
            plan.tests.append(GeneratedTest(
                name=f"test_requirement_{i + 1}",
                test_type="unit",
                test_code=self._gen_unit_test_stub(req),
                requirement_ref=req,
                priority="high",
            ))

        # Generate property tests for functions
        for filepath in files_modified:
            plan.tests.append(GeneratedTest(
                name=f"test_properties_{filepath.replace('/', '_')}",
                test_type="property",
                target_file=filepath,
                test_code=self._gen_property_test_stub(filepath),
                priority="medium",
            ))

        # Generate edge case tests
        plan.tests.append(GeneratedTest(
            name="test_edge_cases_empty_input",
            test_type="unit",
            test_code=self._gen_edge_case_stub("empty input"),
            priority="high",
        ))
        plan.tests.append(GeneratedTest(
            name="test_edge_cases_null_values",
            test_type="unit",
            test_code=self._gen_edge_case_stub("null values"),
            priority="high",
        ))
        plan.tests.append(GeneratedTest(
            name="test_edge_cases_large_input",
            test_type="unit",
            test_code=self._gen_edge_case_stub("large input"),
            priority="medium",
        ))

        self._plans[task_id] = plan
        logger.info(
            "Test plan generated",
            extra={"task_id": task_id, "test_count": len(plan.tests)},
        )
        return plan

    def get_plan(self, task_id: str) -> TestPlan | None:
        return self._plans.get(task_id)

    def _extract_requirements(self, spec: str) -> list[str]:
        """Extract numbered requirements from spec output."""
        requirements: list[str] = []
        in_requirements = False
        for line in spec.splitlines():
            stripped = line.strip()
            if "## Requirements" in stripped or "## Requirement" in stripped:
                in_requirements = True
                continue
            if stripped.startswith("## ") and in_requirements:
                break
            if in_requirements and stripped:
                # Match numbered items or bullet points
                if stripped[0].isdigit() or stripped.startswith("-") or stripped.startswith("*"):
                    clean = stripped.lstrip("0123456789.-*) ").strip()
                    if clean:
                        requirements.append(clean)
        return requirements

    def _extract_files(self, code_output: str) -> list[str]:
        """Extract file paths from code output."""
        import re

        files: list[str] = []
        for line in code_output.splitlines():
            matches = re.findall(r"`([^\s`]+\.\w+)`", line)
            files.extend(matches)
        return list(set(files))[:20]  # Dedup and cap

    def _gen_unit_test_stub(self, requirement: str) -> str:
        return (
            f'def test_requirement():\n'
            f'    """Test: {requirement[:80]}"""\n'
            f'    # TODO: Implement test for this requirement\n'
            f'    assert True  # Placeholder\n'
        )

    def _gen_property_test_stub(self, filepath: str) -> str:
        return (
            f'# Property-based tests for {filepath}\n'
            f'from hypothesis import given, strategies as st\n\n'
            f'@given(st.text())\n'
            f'def test_handles_any_string_input(s):\n'
            f'    """Property: should handle arbitrary string input."""\n'
            f'    assert isinstance(s, str)\n'
        )

    def _gen_edge_case_stub(self, case: str) -> str:
        return (
            f'def test_edge_case_{case.replace(" ", "_")}():\n'
            f'    """Edge case: {case}"""\n'
            f'    # TODO: Implement edge case test\n'
            f'    assert True  # Placeholder\n'
        )
