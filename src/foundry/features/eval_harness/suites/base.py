"""EvalScenario and EvalSuite — test-case and collection models
for the evaluation harness.

Each scenario represents a single evaluation case: feed an input through the
judge or debate pipeline and compare the outcome against expected results.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvalScenario(BaseModel):
    """A single evaluation case.

    Attributes
    ----------
    name:
        Human-readable label for the scenario (e.g. "valid spec with
        clear requirements").
    input:
        The phase output text to evaluate.
    expected_pass:
        Whether the evaluation is expected to pass (``True``) or fail
        (``False``).  ``None`` means no assertion on pass/fail.
    phase:
        SDLC phase context for the evaluation (e.g. ``"Specs"``,
        ``"Coding"``, ``"Review"``).
    from_phase:
        Transition source phase — used when evaluating a specific
        phase transition.  Defaults to *phase*.
    to_phase:
        Transition target phase — used when evaluating a specific
        phase transition.  Defaults to ``"Done"``.
    metadata:
        Arbitrary key-value pairs for additional context (tags, issue
        references, etc.).
    """

    name: str
    input: str
    expected_pass: bool | None = None
    phase: str = "Review"
    from_phase: str | None = None
    to_phase: str = "Done"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalSuite(BaseModel):
    """A named collection of evaluation scenarios.

    Attributes
    ----------
    name:
        Unique identifier for the suite (e.g. ``"specs-regression"``).
    description:
        Optional human-readable description.
    scenarios:
        The list of evaluation cases that comprise this suite.
    """

    name: str
    description: str = ""
    scenarios: list[EvalScenario] = Field(default_factory=list)
