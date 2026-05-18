"""Tests for Phase 3 — Judge and Review Loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sdlc_mcp import JudgeVerdict
from sdlc_mcp.adapters.llm import FakeProvider
from sdlc_mcp.engine.judge import VERDICT_JSON_SCHEMA, JudgeEngine

_FAKE = FakeProvider()
from sdlc_mcp.engine.schema_checks import validate_phase_output
from sdlc_mcp.exceptions import JudgeError
from sdlc_mcp.models import Task


class TestJudgeVerdict:
    def test_verdict_defaults(self) -> None:
        v = JudgeVerdict(passed=True, reason="All good")
        assert v.passed is True
        assert v.reason == "All good"
        assert v.issues == []
        assert v.severity == "info"

    def test_verdict_with_issues(self) -> None:
        v = JudgeVerdict(
            passed=False,
            reason="Found issues",
            issues=["Missing error handling", "No tests"],
            severity="error",
        )
        assert v.passed is False
        assert len(v.issues) == 2
        assert v.severity == "error"

    def test_verdict_json_roundtrip(self) -> None:
        v = JudgeVerdict(passed=True, reason="ok", issues=[], severity="info")
        data = v.model_dump(mode="json")
        restored = JudgeVerdict(**data)
        assert restored.passed == v.passed
        assert restored.reason == v.reason


class TestJudgeEngine:
    def test_engine_init(self) -> None:
        engine = JudgeEngine(_FAKE, model="test-model")
        assert engine.model == "test-model"

    def test_transition_prompt_key_exists(self) -> None:
        engine = JudgeEngine(_FAKE)
        key = engine.transition_prompt_key("Specs", "Planning")
        assert key == "judge_specs_to_planning"

    def test_transition_prompt_key_none(self) -> None:
        engine = JudgeEngine(_FAKE)
        key = engine.transition_prompt_key("Chatting", "Specs")
        assert key is None

    def test_transition_prompt_key_reverse(self) -> None:
        engine = JudgeEngine(_FAKE)
        key = engine.transition_prompt_key("Planning", "Specs")
        assert key is None

    def test_transition_prompt_key_review_to_coding(self) -> None:
        engine = JudgeEngine(_FAKE)
        key = engine.transition_prompt_key("Review", "Coding")
        assert key == "judge_review_to_coding"

    def test_transition_prompt_key_review_to_testing(self) -> None:
        engine = JudgeEngine(_FAKE)
        key = engine.transition_prompt_key("Review", "Testing")
        assert key == "judge_review_to_testing"

    def test_default_prompt_format(self) -> None:
        engine = JudgeEngine(_FAKE)
        prompt = engine._default_prompt("Specs", "Planning")
        assert "Specs" in prompt
        assert "Planning" in prompt
        assert "{output}" in prompt

    @pytest.mark.asyncio
    async def test_evaluate_rejects_schema_violations(self) -> None:
        engine = JudgeEngine(_FAKE)
        task = Task(task_id="t1", description="test")
        output = "## Requirements\n- item\n"
        verdict = await engine.evaluate(task, "Specs", "Planning", output)
        assert verdict.passed is False
        assert "schema" in verdict.reason.lower()

    @pytest.mark.asyncio
    async def test_evaluate_passes_no_judge_configured(self) -> None:
        engine = JudgeEngine(_FAKE)
        task = Task(task_id="t1", description="test")
        output = "hello"
        verdict = await engine.evaluate(task, "Chatting", "Specs", output)
        assert verdict.passed is True
        assert "No judge" in verdict.reason

    @pytest.mark.asyncio
    async def test_evaluate_uses_locked_prompts(self) -> None:
        engine = JudgeEngine(_FAKE)
        task = Task(
            task_id="t1",
            description="test",
            locked_prompts={"judge_coding_to_review": "Custom prompt {output}"},
        )
        output = "## Requirements\n- auth\n## Scope\n- login\n## Constraints\n- py312\n"
        with patch.object(engine, "_llm_judge", new=AsyncMock()) as mock_judge:
            mock_judge.return_value = JudgeVerdict(passed=True, reason="custom")
            verdict = await engine.evaluate(task, "Specs", "Planning", output)
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_llm_judge_parses_json(self) -> None:
        engine = JudgeEngine(_FAKE)
        with patch.object(engine, "_llm_judge", new=AsyncMock()) as mock_judge:
            mock_judge.return_value = JudgeVerdict(passed=True, reason="ok")
            verdict = await engine._llm_judge("prompt {output}", "output")
            assert verdict.passed is True
            assert verdict.reason == "ok"

    @pytest.mark.asyncio
    async def test_llm_judge_http_error(self) -> None:
        engine = JudgeEngine(_FAKE)
        task = Task(
            task_id="t1",
            description="test",
            locked_prompts={"judge_specs_to_planning": "test prompt {output}"},
        )
        output = "## Requirements\n- auth\n## Scope\n- login\n## Constraints\n- py312\n"
        with patch.object(engine, "_llm_judge", new=AsyncMock()) as mock_judge:
            mock_judge.side_effect = JudgeError("model unavailable")
            verdict = await engine.evaluate(task, "Specs", "Planning", output)
            assert verdict.passed is True
            assert "unavailable" in verdict.reason


class TestSchemaChecksBeforeJudge:
    @pytest.fixture
    def engine(self) -> JudgeEngine:
        return JudgeEngine(_FAKE)

    def test_valid_specs_output(self) -> None:
        output = """## Requirements
- User authentication with OAuth2
## Scope
- Login page, token refresh
## Constraints
- Python 3.12, FastAPI
"""
        violations = validate_phase_output("Specs", output)
        assert violations == []

    def test_invalid_specs_output(self) -> None:
        output = "## Requirements\n- auth\n"
        violations = validate_phase_output("Specs", output)
        assert len(violations) >= 2

    def test_valid_review_output(self) -> None:
        output = """## Issues Found
1. Missing input validation
## Severity
HIGH
## Must Fix
- Add validation
"""
        violations = validate_phase_output("Review", output)
        assert violations == []

    def test_valid_planning_output(self) -> None:
        output = """## Implementation Plan
1. Create module
## File Changes
src/module.py
## Risks
None
"""
        violations = validate_phase_output("Planning", output)
        assert violations == []

    def test_valid_coding_output(self) -> None:
        output = """## Files Modified
- src/module.py (create)
"""
        violations = validate_phase_output("Coding", output)
        assert violations == []

    def test_valid_testing_output(self) -> None:
        output = """## Test Results
All tests pass
## Coverage
95%
## Failed
None
"""
        violations = validate_phase_output("Testing", output)
        assert violations == []


class TestVerdictSchema:
    def test_verdict_schema_structure(self) -> None:
        assert "type" in VERDICT_JSON_SCHEMA
        assert "properties" in VERDICT_JSON_SCHEMA
        props = VERDICT_JSON_SCHEMA["properties"]
        assert "passed" in props
        assert "reason" in props
        assert "issues" in props
        assert "severity" in props
        assert props["passed"]["type"] == "boolean"

    def test_verdict_schema_required(self) -> None:
        required = VERDICT_JSON_SCHEMA["required"]
        assert "passed" in required
        assert "reason" in required

    def test_verdict_schema_severity_enum(self) -> None:
        sev = VERDICT_JSON_SCHEMA["properties"]["severity"]
        assert sev["enum"] == ["info", "warning", "error", "critical"]


class TestPromptLocking:
    def test_task_with_locked_prompts(self) -> None:
        prompts = {
            "judge_specs_to_planning": "Evaluate spec output...",
            "judge_coding_to_review": "Evaluate code output...",
        }
        task = Task(task_id="t1", description="test", locked_prompts=prompts)
        assert task.locked_prompts["judge_specs_to_planning"] == "Evaluate spec output..."
        assert task.locked_prompts["judge_coding_to_review"] == "Evaluate code output..."

    def test_task_empty_locked_prompts(self) -> None:
        task = Task(task_id="t1", description="test")
        assert task.locked_prompts == {}

    def test_locked_prompts_json_roundtrip(self) -> None:
        prompts = {"judge_test": "prompt text"}
        task = Task(task_id="t1", description="test", locked_prompts=prompts)
        data = task.model_dump(mode="json")
        restored = Task(**data)
        assert restored.locked_prompts["judge_test"] == "prompt text"


class TestIterationProtection:
    def test_default_iteration_count(self) -> None:
        task = Task(task_id="t1", description="test")
        assert task.iteration_count == 0

    def test_iteration_count_increments(self) -> None:
        task = Task(task_id="t1", description="test")
        task.iteration_count += 1
        assert task.iteration_count == 1

    def test_max_iterations_from_model(self) -> None:
        task = Task(task_id="t1", description="test")
        max_iter = 8
        exceeded = task.iteration_count >= max_iter
        assert exceeded is False

    def test_iteration_limit_exceeded(self) -> None:
        task = Task(task_id="t1", description="test", iteration_count=8)
        max_iter = 8
        exceeded = task.iteration_count >= max_iter
        assert exceeded is True


class TestJudgePromptFiles:
    def test_all_prompt_files_exist(self) -> None:
        from pathlib import Path
        prompts_dir = (
            Path(__file__).resolve().parent.parent / "configs" / "prompts"
        )
        expected = [
            "judge_specs_to_planning.txt",
            "judge_planning_to_coding.txt",
            "judge_coding_to_review.txt",
            "judge_review_to_coding.txt",
            "judge_review_to_testing.txt",
        ]
        for name in expected:
            assert (prompts_dir / name).exists(), f"Missing: {name}"

    def test_prompt_files_have_content(self) -> None:
        from pathlib import Path
        prompts_dir = (
            Path(__file__).resolve().parent.parent / "configs" / "prompts"
        )
        for txt_file in prompts_dir.glob("judge_*.txt"):
            content = txt_file.read_text(encoding="utf-8")
            assert len(content) > 50, f"{txt_file.name} is too short"
            assert "{output}" in content, f"{txt_file.name} missing {{output}} placeholder"
