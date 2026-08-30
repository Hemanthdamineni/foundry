"""JudgeEngine — LLM transition evaluation via pluggable LLM provider.

Evaluates phase output quality before allowing transitions.  Deterministic
preconditions (schema checks) run first; the LLM judge runs second.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from sdlc_judge.base import LLMProvider
from sdlc_models.exceptions import JudgeError
from sdlc_models.judge import JudgeVerdict
from sdlc_phases.checks import validate_phase_output

if TYPE_CHECKING:
    from sdlc_models.phases import Task


VERDICT_JSON_SCHEMA: dict[str, Any] = {
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
    """LLM-based judge that evaluates phase outputs.

    Does **not** mutate phase state — returns a verdict only.

    Parameters
    ----------
    provider:
        An :class:`LLMProvider` implementation used for the LLM judge stage.
    model:
        Model identifier passed to the provider (default ``"qwen3:8b"``).
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model: str = "qwen3:8b",
    ) -> None:
        self._provider = provider
        self._model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The model identifier used by this engine instance."""
        return self._model

    def transition_prompt_key(self, from_phase: str, to_phase: str) -> str | None:
        """Return the locked prompt key for a transition, if one exists.

        Returns ``None`` when the transition is not in the predefined map.
        """
        return _TRANSITION_PROMPT_KEYS.get((from_phase, to_phase))

    async def evaluate(
        self,
        task: Task,
        from_phase: str,
        to_phase: str,
        output: str,
    ) -> JudgeVerdict:
        """Three-stage gate: phase match -> deterministic checks -> LLM judge.

        Stages
        ------
        1. **Phase match** — handled by the caller before calling this method.
        2. **Deterministic schema checks** — structural preconditions enforced
           via :func:`sdlc_phases.checks.validate_phase_output`.  Returns a
           failing verdict immediately if violations are found.
        3. **LLM judge** — only runs when stage 2 passes.  The provider is
           called with a transition-specific or default prompt.  If the LLM
           call itself fails the verdict defaults to *passing* so the pipeline
           is not permanently blocked by transient judge failures.

        Parameters
        ----------
        task:
            The active task, used to look up *locked prompts* that override
            the default prompt for a transition.
        from_phase:
            The phase the task is transitioning from.
        to_phase:
            The phase the task is transitioning to.
        output:
            The raw output text produced during the *from* phase.

        Returns
        -------
        JudgeVerdict
            A structured verdict with ``passed``, ``reason``, ``issues``,
            and ``severity``.
        """
        # ---- Stage 2: deterministic schema checks -------------------------
        schema_violations = validate_phase_output(from_phase, output)
        if schema_violations:
            return JudgeVerdict(
                passed=False,
                reason="Deterministic schema checks failed",
                issues=[str(v) for v in schema_violations],
                severity="error",
            )

        # ---- Stage 2.5: schema-only mode ------------------------------------
        if self._provider is None:
            return JudgeVerdict(
                passed=True,
                reason="Schema-only mode — no LLM provider configured",
            )

        # ---- Stage 3: LLM judge -------------------------------------------
        prompt_key = self.transition_prompt_key(from_phase, to_phase)
        if prompt_key is None:
            return JudgeVerdict(
                passed=True,
                reason="No judge configured for this transition",
            )

        if prompt_key in task.locked_prompts:
            prompt_text = task.locked_prompts[prompt_key]
        else:
            prompt_text = self._default_prompt(from_phase, to_phase)

        try:
            return await self._llm_judge(prompt_text, output)
        except JudgeError:
            return JudgeVerdict(
                passed=True,
                reason="Judge unavailable -- proceeding without LLM evaluation",
                issues=[],
                severity="info",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_prompt(self, from_phase: str, to_phase: str) -> str:
        """Build a generic judge prompt for an arbitrary transition."""
        return (
            f"Evaluate the output of the '{from_phase}' phase before it transitions to "
            f"'{to_phase}'. Determine if the output is complete, correct, and ready.\n\n"
            f"Output:\n{{output}}\n\n"
            f"Return a JSON object with 'passed' (bool), 'reason' (str), "
            f"'issues' (array of strings), and 'severity' (info/warning/error/critical)."
        )

    async def _llm_judge(self, prompt_template: str, output: str) -> JudgeVerdict:
        """Call the LLM provider and parse the structured response.

        Parameters
        ----------
        prompt_template:
            A template string containing a ``{output}`` placeholder.
        output:
            The actual phase output to substitute into the template.

        Returns
        -------
        JudgeVerdict
            Parsed from the provider's JSON response.

        Raises
        ------
        JudgeError
            If the provider call itself fails (network error, timeout).
        """
        prompt = prompt_template.replace("{output}", output)

        try:
            content = await self._provider.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                temperature=0.0,
                response_format=VERDICT_JSON_SCHEMA,
            )
        except RuntimeError as exc:
            raise JudgeError(
                "Judge LLM call failed",
                failure_type="model_timeout",
                details={"error": str(exc)},
            ) from exc

        # -- Empty / whitespace-only response --------------------------------
        if not content.strip():
            return JudgeVerdict(
                passed=False,
                reason="Judge returned empty response",
                issues=["Empty LLM response"],
                severity="error",
            )

        # -- JSON parse ------------------------------------------------------
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return JudgeVerdict(
                passed=False,
                reason=f"Judge returned unparseable JSON: {content[:200]}",
                issues=["Invalid JSON response from judge"],
                severity="error",
            )

        # -- Schema validation via JudgeVerdict constructor ------------------
        try:
            return JudgeVerdict(**data)
        except (TypeError, ValueError) as exc:
            return JudgeVerdict(
                passed=False,
                reason=f"Judge verdict schema mismatch: {exc}",
                issues=[f"Schema error: {exc}"],
                severity="error",
            )
