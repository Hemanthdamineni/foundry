"""Tests for EvalScenario and EvalSuite models."""

from __future__ import annotations

from foundry.features.eval_harness.suites.base import EvalScenario, EvalSuite


class TestEvalScenario:
    """EvalScenario construction and defaults."""

    def test_minimal_scenario(self) -> None:
        """A scenario requires only name and input."""
        s = EvalScenario(name="test", input="some output")
        assert s.name == "test"
        assert s.input == "some output"
        assert s.expected_pass is None
        assert s.phase == "Review"
        assert s.to_phase == "Done"
        assert s.from_phase is None
        assert s.metadata == {}

    def test_full_scenario(self) -> None:
        """All fields can be set explicitly."""
        s = EvalScenario(
            name="full-test",
            input="phase output text",
            expected_pass=True,
            phase="Coding",
            from_phase="Planning",
            to_phase="Review",
            metadata={"jira": "PROJ-123"},
        )
        assert s.expected_pass is True
        assert s.phase == "Coding"
        assert s.from_phase == "Planning"
        assert s.to_phase == "Review"
        assert s.metadata["jira"] == "PROJ-123"

    def test_from_phase_defaults_to_phase(self) -> None:
        """When from_phase is None it remains None (not coerced)."""
        s = EvalScenario(name="default", input="x", phase="Specs")
        assert s.from_phase is None


class TestEvalSuite:
    """EvalSuite construction and defaults."""

    def test_empty_suite(self) -> None:
        """A suite can be created with no scenarios."""
        s = EvalSuite(name="empty-suite")
        assert s.name == "empty-suite"
        assert s.description == ""
        assert s.scenarios == []

    def test_suite_with_scenarios(self) -> None:
        """Scenarios are stored in order."""
        s1 = EvalScenario(name="a", input="x")
        s2 = EvalScenario(name="b", input="y")
        suite = EvalSuite(name="multi", scenarios=[s1, s2])
        assert len(suite.scenarios) == 2
        assert suite.scenarios[0].name == "a"
        assert suite.scenarios[1].name == "b"

    def test_suite_serialization_roundtrip(self) -> None:
        """EvalSuite is serializable via model_dump/model_validate."""
        s1 = EvalScenario(name="test", input="hello", expected_pass=True, phase="Coding")
        suite = EvalSuite(
            name="roundtrip",
            description="Test roundtrip",
            scenarios=[s1],
        )
        data = suite.model_dump()
        restored = EvalSuite.model_validate(data)
        assert restored.name == suite.name
        assert restored.description == suite.description
        assert len(restored.scenarios) == 1
        assert restored.scenarios[0].name == "test"
        assert restored.scenarios[0].expected_pass is True
