"""JudgeEngine — LLM transition evaluation via pluggable LLM provider.

Evaluates phase output quality before allowing transitions. Deterministic
preconditions (schema checks) run first; the LLM judge runs second.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sdlc.adapters.llm import LLMProvider
from sdlc.engine.schema_checks import validate_phase_output
from sdlc.exceptions import JudgeError
from sdlc.models import JudgeVerdict

if TYPE_CHECKING:
    from sdlc.models import Task


VERDICT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {
            "type": "string",
            "enum": ["info", "warning", "error", "critical"],
        },
    },
    "required": ["passed", "reason"],
}

_TRANSITION_PROMPT_KEYS: dict[tuple[str, str], str] = {
    ("Specs", "Planning"): "judge_specs_to_planning",
    ("Planning", "Coding"): "judge_planning_to_coding",
    ("Coding", "Review"): "judge_coding_to_review",
    ("Review", "Coding"): "judge_review_to_coding",
    ("Review", "Testing"): "judge_review_to_testing",
}


class JudgeEngine:
    """LLM-based judge that evaluates phase outputs using Ollama format=.

    Does NOT mutate phase state — returns a verdict only.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "qwen3:8b",
    ) -> None:
        self._provider = provider
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def transition_prompt_key(self, from_phase: str, to_phase: str) -> str | None:
        """Return the locked prompt key for a transition, if one exists."""
        return _TRANSITION_PROMPT_KEYS.get((from_phase, to_phase))

    async def evaluate(
        self,
        task: Task,
        from_phase: str,
        to_phase: str,
        output: str,
    ) -> JudgeVerdict:
        """Three-stage gate: phase match -> deterministic checks -> LLM judge.

        Stage 1 (phase match) is handled by the caller.
        Stage 2: deterministic schema checks — reject immediately if violations.
        Stage 3: LLM judge via Ollama format= — only runs if stage 2 passes.
        """
        schema_violations = validate_phase_output(from_phase, output)
        if schema_violations:
            return JudgeVerdict(
                passed=False,
                reason="Deterministic schema checks failed",
                issues=[str(v) for v in schema_violations],
                severity="error",
            )

        prompt_key = self.transition_prompt_key(from_phase, to_phase)
        if prompt_key is None:
            return JudgeVerdict(passed=True, reason="No judge configured for this transition")

        if prompt_key in task.locked_prompts:
            prompt_text = task.locked_prompts[prompt_key]
        else:
            prompt_text = self._default_prompt(from_phase, to_phase)

        try:
            return await self._llm_judge(prompt_text, output)
        except JudgeError:
            return JudgeVerdict(
                passed=True,
                reason="Judge unavailable — proceeding without LLM evaluation",
                issues=[],
                severity="info",
            )

    def _default_prompt(self, from_phase: str, to_phase: str) -> str:
        return (
            f"Evaluate the output of the '{from_phase}' phase before it transitions to "
            f"'{to_phase}'. Determine if the output is complete, correct, and ready.\n\n"
            f"Output:\n{{output}}\n\n"
            f"Return a JSON object with 'passed' (bool), 'reason' (str), "
            f"'issues' (array of strings), and 'severity' (info/warning/error/critical)."
        )

    async def _llm_judge(self, prompt_template: str, output: str) -> JudgeVerdict:
        prompt = prompt_template.replace("{output}", output)

        try:
            content = await self._provider.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                temperature=0.0,
                response_format=VERDICT_JSON_SCHEMA,
            )
        except RuntimeError as exc:
            raise JudgeError(  # noqa: TRY003
                "Judge LLM call failed",
                failure_type="model_timeout",
                details={"error": str(exc)},
            ) from exc

        if not content.strip():
            return JudgeVerdict(
                passed=False,
                reason="Judge returned empty response",
                issues=["Empty LLM response"],
                severity="error",
            )

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return JudgeVerdict(
                passed=False,
                reason=f"Judge returned unparseable JSON: {content[:200]}",
                issues=["Invalid JSON response from judge"],
                severity="error",
            )

        try:
            return JudgeVerdict(**data)
        except (TypeError, ValueError) as exc:
            return JudgeVerdict(
                passed=False,
                reason=f"Judge verdict schema mismatch: {exc}",
                issues=[f"Schema error: {exc}"],
                severity="error",
            )
