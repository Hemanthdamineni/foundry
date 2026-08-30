"""Phase graph contract definitions — lightweight dataclasses for graph, routing, and prompts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhaseGraphContract:
    """Describes the phase graph shape: edges and mandatory gates.

    Differs from sdlc_phases.graph.PhaseGraph in that this is a pure-data
    representation (no YAML loading, no validation logic).
    """

    edges: dict[str, tuple[str, ...]] = field(default_factory=dict)
    required_completed: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def allowed_next(self, phase: str) -> tuple[str, ...]:
        """Return the tuple of phases reachable from *phase*."""
        return self.edges.get(phase, ())


@dataclass(frozen=True)
class ModelRouting:
    """Maps phases and roles to the models that should serve them."""

    roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    phases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def models_for_phase(self, phase: str) -> tuple[str, ...]:
        """Return the model tuple configured for *phase*."""
        return self.phases.get(phase, ())

    @property
    def all_models(self) -> set[str]:
        """Return the union of every model referenced across roles and phases."""
        result: set[str] = set()
        for models in self.phases.values():
            result.update(models)
        for models in self.roles.values():
            result.update(models)
        return result


@dataclass(frozen=True)
class PromptContracts:
    """Maps each phase to its system prompt template."""

    phases: dict[str, str] = field(default_factory=dict)

    def system_prompt_for(self, phase: str) -> str | None:
        """Return the system prompt configured for *phase*, or None."""
        return self.phases.get(phase)
