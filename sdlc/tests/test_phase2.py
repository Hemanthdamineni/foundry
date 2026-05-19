"""Tests for Phase 2 — Deterministic Validation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure tool binaries (ruff, mypy, pytest) are on PATH for adapter tests
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent
_PIXI_BIN = str(PROJECT_DIR / ".pixi" / "envs" / "default" / "bin")
if os.path.exists(_PIXI_BIN):
    os.environ["PATH"] = f"{_PIXI_BIN}:{os.environ.get('PATH', '')}"

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.adapters.tools.mypy import MypyAdapter
from sdlc.adapters.tools.pytest import PytestAdapter
from sdlc.adapters.tools.ruff import RuffAdapter
from sdlc.engine.schema_checks import (
    SchemaViolationError,
    check_coding_output,
    check_done_output,
    check_planning_output,
    check_review_output,
    check_specs_output,
    check_testing_output,
    validate_phase_output,
)
from sdlc.models import FailureType
from sdlc.validators.deterministic.results import ValidationReport, ValidationResult
from sdlc.validators.deterministic.runner import ValidationRunner


class TestSchemaChecks:
    def test_specs_output_valid(self) -> None:
        output = """## Requirements
- Must handle user authentication
- Must support OAuth2
## Scope
- Login page, token refresh
## Constraints
- Python 3.12, FastAPI
"""
        violations = check_specs_output(output)
        assert violations == []

    def test_specs_output_missing_section(self) -> None:
        output = "## Requirements\n- item 1\n## Scope\n- item 2\n"
        violations = check_specs_output(output)
        assert len(violations) == 1
        assert "Constraints" in violations[0].section

    def test_specs_output_empty_section(self) -> None:
        output = "## Requirements\n\n## Scope\n\n## Constraints\n- some constraint\n"
        violations = check_specs_output(output)
        assert any("Requirements" in v.section for v in violations)
        assert any("Scope" in v.section for v in violations)

    def test_planning_output_valid(self) -> None:
        output = """## Implementation Plan
1. Create auth module
2. Add routes
## File Changes
src/auth.py (create), src/main.py (modify)
## Risks
- Token rotation may need extra work
"""
        violations = check_planning_output(output)
        assert violations == []

    def test_planning_output_missing_sections(self) -> None:
        output = "## Implementation Plan\n- step 1\n"
        violations = check_planning_output(output)
        assert len(violations) >= 2

    def test_coding_output_valid(self) -> None:
        output = """## Files Modified
- src/api/users.py (modify)
"""
        violations = check_coding_output(output)
        assert violations == []

    def test_coding_output_missing_file_refs(self) -> None:
        output = "## Summary\nImplemented user auth.\n"
        violations = check_coding_output(output)
        assert len(violations) == 1
        assert "Files Modified" in violations[0].section

    def test_review_output_valid(self) -> None:
        output = """## Issues Found
1. Missing input validation on login endpoint
## Severity
HIGH - auth bypass risk
## Must Fix
- Add input sanitization before merge
"""
        violations = check_review_output(output)
        assert violations == []

    def test_review_output_missing_severity(self) -> None:
        output = "## Issues Found\n- bug\n## Must Fix\n- fix it\n"
        violations = check_review_output(output)
        assert len(violations) == 1
        assert "Severity" in violations[0].section

    def test_testing_output_valid(self) -> None:
        output = """## Test Results
All 42 tests passed
## Coverage
94% line coverage
## Failed
None
"""
        violations = check_testing_output(output)
        assert violations == []

    def test_testing_output_missing_sections(self) -> None:
        output = "## Test Results\n- passed\n"
        violations = check_testing_output(output)
        assert len(violations) >= 2

    def test_done_output_valid(self) -> None:
        output = "## Summary\nCompleted user auth feature with tests.\nCoverage: 94%."
        violations = check_done_output(output)
        assert violations == []

    def test_done_output_too_short(self) -> None:
        output = "Done."
        violations = check_done_output(output)
        assert len(violations) == 1

    def test_validate_phase_output_routes_correctly(self) -> None:
        spec_out = "## Requirements\n- auth\n## Scope\n- login\n## Constraints\n- py312\n"
        assert len(validate_phase_output("Specs", spec_out)) == 0
        coding_out = "No section references"
        assert len(validate_phase_output("Coding", coding_out)) == 1

    def test_validate_phase_output_unknown_phase(self) -> None:
        assert validate_phase_output("Chatting", "hello") == []

    def test_schema_violation_attributes(self) -> None:
        v = SchemaViolationError("test error", section="Test", details={"key": "val"})
        assert str(v) == "test error"
        assert v.section == "Test"
        assert v.details == {"key": "val"}


class TestValidationReport:
    def test_empty_report(self) -> None:
        report = ValidationReport(phase="Coding", task_id="t1")
        assert report.total_checks == 0
        assert report.all_passed is False
        assert report.passed_checks == 0
        assert report.failed_checks == 0

    def test_add_passing_result(self) -> None:
        report = ValidationReport(phase="Coding", task_id="t1")
        result = ValidationResult(
            adapter="ruff",
            capability="lint",
            passed=True,
            summary="No issues found",
        )
        report.add_result(result)
        assert report.total_checks == 1
        assert report.passed_checks == 1
        assert report.all_passed is True

    def test_add_failing_result(self) -> None:
        report = ValidationReport(phase="Review", task_id="t1")
        result = ValidationResult(
            adapter="mypy",
            capability="typing",
            passed=False,
            summary="Type errors found",
            failure_type=FailureType.TERMINAL_VALIDATION,
        )
        report.add_result(result)
        assert report.total_checks == 1
        assert report.failed_checks == 1
        assert report.all_passed is False

    def test_merge_reports(self) -> None:
        r1 = ValidationReport(phase="Coding", task_id="t1")
        r1.add_result(ValidationResult(adapter="ruff", capability="lint", passed=True, summary="ok"))
        r2 = ValidationReport(phase="Coding", task_id="t1")
        r2.add_result(
            ValidationResult(
                adapter="mypy", capability="typing", passed=False, summary="errors"
            )
        )
        merged = r1.merge(r2)
        assert merged.total_checks == 2
        assert merged.passed_checks == 1
        assert merged.failed_checks == 1
        assert merged.all_passed is False

    def test_primary_failure(self) -> None:
        report = ValidationReport(phase="Coding", task_id="t1")
        report.add_result(ValidationResult(adapter="ruff", capability="lint", passed=True, summary="ok"))
        report.add_result(
            ValidationResult(
                adapter="mypy",
                capability="typing",
                passed=False,
                summary="errors",
                failure_type=FailureType.TERMINAL_VALIDATION,
            )
        )
        assert report.primary_failure() == FailureType.TERMINAL_VALIDATION

    def test_primary_failure_none(self) -> None:
        report = ValidationReport(phase="Coding", task_id="t1")
        report.add_result(ValidationResult(adapter="ruff", capability="lint", passed=True, summary="ok"))
        assert report.primary_failure() is None

    def test_summary_format(self) -> None:
        report = ValidationReport(phase="Review", task_id="t1")
        report.add_result(ValidationResult(adapter="ruff", capability="lint", passed=True, summary="ok"))
        report.schema_violations.append("Missing section: ## Severity")
        summary = report.summary()
        assert "[PASS]" in summary
        assert "Missing section:" in summary


class MockPassAdapter(ToolAdapter):
    name = "mock_pass"
    capability = ToolCapability.LINT

    async def validate(self, task: object) -> bool:
        return True

    async def execute(self, task: object) -> dict:
        return {"adapter": "mock_pass", "capability": "lint", "passed": True, "summary": "pass", "details": []}

    async def healthcheck(self) -> bool:
        return True


class MockFailAdapter(ToolAdapter):
    name = "mock_fail"
    capability = ToolCapability.TYPING

    async def validate(self, task: object) -> bool:
        return True

    async def execute(self, task: object) -> dict:
        return {"adapter": "mock_fail", "capability": "typing", "passed": False, "summary": "fail", "details": []}

    async def healthcheck(self) -> bool:
        return True


class MockCrashAdapter(ToolAdapter):
    name = "mock_crash"
    capability = ToolCapability.TESTING

    async def validate(self, task: object) -> bool:
        return True

    async def execute(self, task: object) -> dict:
        msg = "internal error"
        raise RuntimeError(msg)

    async def healthcheck(self) -> bool:
        return False


class MockInvalidTaskAdapter(ToolAdapter):
    name = "mock_skip"
    capability = ToolCapability.CODE_GRAPH

    async def validate(self, task: object) -> bool:
        return False

    async def execute(self, task: object) -> dict:
        return {"adapter": "mock_skip", "capability": "code_graph", "passed": True, "summary": "skipped", "details": []}

    async def healthcheck(self) -> bool:
        return True


class TestValidationRunner:
    @pytest.mark.asyncio
    async def test_run_all_passes(self) -> None:
        runner = ValidationRunner(adapters=[MockPassAdapter()])
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Coding")
        assert report.total_checks == 1
        assert report.passed_checks == 1
        assert report.all_passed is True

    @pytest.mark.asyncio
    async def test_run_all_with_failures(self) -> None:
        runner = ValidationRunner(adapters=[MockFailAdapter()])
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Review")
        assert report.total_checks == 1
        assert report.failed_checks == 1
        assert report.all_passed is False

    @pytest.mark.asyncio
    async def test_run_all_mixed_results(self) -> None:
        runner = ValidationRunner(adapters=[MockPassAdapter(), MockFailAdapter()])
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Review")
        assert report.total_checks == 2
        assert report.passed_checks == 1
        assert report.failed_checks == 1
        assert report.all_passed is False

    @pytest.mark.asyncio
    async def test_run_all_crashing_adapter(self) -> None:
        runner = ValidationRunner(adapters=[MockCrashAdapter()])
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Testing")
        assert report.total_checks == 1
        assert report.failed_checks == 1

    @pytest.mark.asyncio
    async def test_valid_task_filtering(self) -> None:
        runner = ValidationRunner(adapters=[MockInvalidTaskAdapter(), MockPassAdapter()])
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Coding")
        assert report.total_checks == 1
        assert report.passed_checks == 1

    @pytest.mark.asyncio
    async def test_run_all_with_schema_violations(self) -> None:
        runner = ValidationRunner(adapters=[MockPassAdapter()])
        bad_output = "## Issues Found\n- something\n"
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Review", output=bad_output)
        assert len(report.schema_violations) >= 1

    @pytest.mark.asyncio
    async def test_runner_empty_adapters(self) -> None:
        runner = ValidationRunner()
        report = await runner.run_all({"task_id": "t1", "path": "."}, phase="Coding")
        assert report.total_checks == 0

    @pytest.mark.asyncio
    async def test_register_adapter(self) -> None:
        runner = ValidationRunner()
        assert runner.registered_capabilities() == []
        runner.register(MockPassAdapter())
        assert ToolCapability.LINT in runner.registered_capabilities()

    @pytest.mark.asyncio
    async def test_run_for_phase(self) -> None:
        runner = ValidationRunner(adapters=[MockPassAdapter()])
        report = await runner.run_for_phase({"task_id": "t1", "path": "."}, phase="Coding")
        assert report.phase == "Coding"


class TestToolCapabilities:
    def test_ruff_capability(self) -> None:
        adapter = RuffAdapter(ruff_path="false")
        assert adapter.name == "ruff"
        assert adapter.capability == ToolCapability.LINT

    def test_mypy_capability(self) -> None:
        adapter = MypyAdapter(mypy_path="false")
        assert adapter.name == "mypy"
        assert adapter.capability == ToolCapability.TYPING

    def test_pytest_capability(self) -> None:
        adapter = PytestAdapter(pytest_path="false")
        assert adapter.name == "pytest"
        assert adapter.capability == ToolCapability.TESTING

    @pytest.mark.asyncio
    async def test_adapter_validate_rejects_no_path(self) -> None:
        ruff = RuffAdapter(ruff_path="false")
        mypy = MypyAdapter(mypy_path="false")
        pytest_ = PytestAdapter(pytest_path="false")
        assert await ruff.validate({}) is False
        assert await mypy.validate({}) is False
        assert await pytest_.validate({}) is False

    @pytest.mark.asyncio
    async def test_adapter_validate_accepts_path(self) -> None:
        ruff = RuffAdapter(ruff_path="false")
        assert await ruff.validate({"path": "."}) is True

    @pytest.mark.asyncio
    async def test_adapter_healthcheck_missing_tool(self) -> None:
        ruff = RuffAdapter(ruff_path="nonexistent_tool_xyz")
        assert await ruff.healthcheck() is False
        mypy = MypyAdapter(mypy_path="nonexistent_tool_xyz")
        assert await mypy.healthcheck() is False
        pytest_ = PytestAdapter(pytest_path="nonexistent_tool_xyz")
        assert await pytest_.healthcheck() is False


class TestIntegrationAdapters:
    @pytest.mark.asyncio
    async def test_ruff_on_known_bad_file(self, tmp_path) -> None:
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("import os, sys\nx = 1\ny = 2\n")
        ruff = RuffAdapter()
        result = await ruff.execute({"path": str(bad_file)})
        assert isinstance(result, dict)
        assert "adapter" in result
        assert "capability" in result
        assert "passed" in result
        assert isinstance(result["passed"], bool)

    @pytest.mark.asyncio
    async def test_mypy_on_known_bad_file(self, tmp_path) -> None:
        bad_file = tmp_path / "bad_type.py"
        bad_file.write_text("def greet(name: str) -> int:\n    return name\n")
        mypy = MypyAdapter()
        result = await mypy.execute({"path": str(bad_file)})
        assert isinstance(result, dict)
        assert "passed" in result
        assert isinstance(result["passed"], bool)

    @pytest.mark.asyncio
    async def test_pytest_on_known_bad_file(self, tmp_path) -> None:
        bad_file = tmp_path / "test_bad.py"
        bad_file.write_text("def test_fail():\n    assert False\n")
        pytest_ = PytestAdapter()
        result = await pytest_.execute({"path": str(bad_file)})
        assert isinstance(result, dict)
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_ruff_on_valid_file(self, tmp_path) -> None:
        valid_file = tmp_path / "valid.py"
        valid_file.write_text('def greet(name: str) -> str:\n    return f"Hello, {name}!"\n')
        ruff = RuffAdapter()
        result = await ruff.execute({"path": str(valid_file)})
        assert isinstance(result, dict)
        assert isinstance(result["passed"], bool)

    @pytest.mark.asyncio
    async def test_integrated_runner_with_real_ruff(self, tmp_path) -> None:
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("import os, sys\nx = 1\n")
        ruff = RuffAdapter()
        runner = ValidationRunner(adapters=[ruff])
        report = await runner.run_all(
            {"task_id": "t1", "path": str(tmp_path)},
            phase="Coding",
        )
        assert report.total_checks == 1
        assert isinstance(report.all_passed, bool)
        assert isinstance(report.summary(), str)
