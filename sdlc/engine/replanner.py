"""Dynamic replanning runtime — downstream invalidation with stable-work preservation.

TODO #11: Without replanning, failures cascade globally. Rule: PRESERVE COMPLETED STABLE WORK.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.replanner")


class ReplanScope(BaseModel):
    """Scope of a replan operation."""

    task_id: str
    trigger_phase: str
    reason: str = ""
    phases_to_invalidate: list[str] = Field(default_factory=list)
    phases_preserved: list[str] = Field(default_factory=list)
    files_affected: list[str] = Field(default_factory=list)
    new_plan: dict[str, Any] = Field(default_factory=dict)


class Replanner:
    """Dynamic replanning with dependency-aware invalidation and stable-work preservation."""

    def __init__(self) -> None:
        self._stable_phases: dict[str, set[str]] = {}  # task_id → stable phases
        self._phase_deps: dict[str, list[str]] = {}  # phase → depends-on phases
        self._history: list[ReplanScope] = []

    def mark_stable(self, task_id: str, phase: str) -> None:
        self._stable_phases.setdefault(task_id, set()).add(phase)

    def set_phase_dependencies(self, deps: dict[str, list[str]]) -> None:
        """Set phase dependency graph: phase → [phases it depends on]."""
        self._phase_deps = dict(deps)

    def plan_replan(
        self,
        task_id: str,
        trigger_phase: str,
        all_phases: list[str],
        reason: str = "",
    ) -> ReplanScope:
        """Plan a replan — determine which phases to invalidate and which to preserve."""
        stable = self._stable_phases.get(task_id, set())

        # Find trigger index
        try:
            trigger_idx = all_phases.index(trigger_phase)
        except ValueError:
            return ReplanScope(task_id=task_id, trigger_phase=trigger_phase, reason="Phase not found")

        # Invalidate downstream phases (after trigger), preserving stable ones
        to_invalidate: list[str] = []
        preserved: list[str] = []

        for phase in all_phases[trigger_idx:]:
            if phase in stable:
                preserved.append(phase)
            else:
                to_invalidate.append(phase)

        # Also invalidate phases that depend on invalidated phases
        extra_invalidations: list[str] = []
        for phase, deps in self._phase_deps.items():
            if any(d in to_invalidate for d in deps) and phase not in to_invalidate and phase not in stable:
                extra_invalidations.append(phase)
        to_invalidate.extend(extra_invalidations)

        scope = ReplanScope(
            task_id=task_id,
            trigger_phase=trigger_phase,
            reason=reason,
            phases_to_invalidate=to_invalidate,
            phases_preserved=preserved,
        )
        self._history.append(scope)
        logger.info(
            "Replan planned",
            extra={
                "task_id": task_id,
                "trigger": trigger_phase,
                "invalidated": len(to_invalidate),
                "preserved": len(preserved),
            },
        )
        return scope

    def apply_replan(self, scope: ReplanScope) -> dict[str, Any]:
        """Apply a replan — returns the invalidated and preserved lists."""
        return {
            "task_id": scope.task_id,
            "invalidated": scope.phases_to_invalidate,
            "preserved": scope.phases_preserved,
            "new_plan": scope.new_plan,
        }

    @property
    def history(self) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self._history]
