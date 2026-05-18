"""Phase graph loading, validation, and transition logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PhaseGraphError(Exception):
    """Phase graph validation or lookup error."""


class PhaseGraph:
    """Loads, validates, and queries phase graph templates."""

    def __init__(self, graph_data: dict[str, Any]) -> None:
        self._phases: list[str] = list(graph_data.get("phases", []))
        self._transitions: list[dict[str, str]] = list(graph_data.get("transitions", []))
        self._adj: dict[str, list[str]] = {}
        self._build_adjacency()
        self.validate()

    def _build_adjacency(self) -> None:
        self._adj = {}
        for phase in self._phases:
            self._adj[phase] = []
        for t in self._transitions:
            from_p = t.get("from")
            to_p = t.get("to")
            if from_p is None or to_p is None:
                continue
            if from_p in self._adj:
                self._adj[from_p].append(to_p)

    @classmethod
    def from_file(cls, path: str | Path) -> PhaseGraph:
        path = Path(path)
        if not path.exists():
            msg = f"Phase graph not found: {path}"
            raise PhaseGraphError(msg)
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            msg = f"Invalid phase graph in {path}"
            raise PhaseGraphError(msg)
        return cls(data)

    def validate(self) -> None:
        if not self._phases:
            msg = "Phase graph must have at least one phase"
            raise PhaseGraphError(msg)
        if "Done" not in self._phases:
            msg = "Phase graph must include a 'Done' phase"
            raise PhaseGraphError(msg)
        phase_set = set(self._phases)
        for transition in self._transitions:
            from_phase = transition.get("from")
            to_phase = transition.get("to")
            if from_phase not in phase_set or to_phase not in phase_set:
                msg = f"Transition references unknown phase: {transition}"
                raise PhaseGraphError(msg)
        start_phase = self._phases[0]
        reachable = self._reachable_from(start_phase)
        unreachable = [p for p in self._phases if p not in reachable]
        if unreachable:
            msg = f"Unreachable phases from '{start_phase}': {unreachable}"
            raise PhaseGraphError(msg)
        if self._adj.get("Done", []):
            msg = "Phase 'Done' must have no outgoing transitions"
            raise PhaseGraphError(msg)

    def _reachable_from(self, start: str) -> set[str]:
        visited: set[str] = set()
        stack = [start]
        while stack:
            phase = stack.pop()
            if phase in visited:
                continue
            visited.add(phase)
            stack.extend(
                neighbor for neighbor in self._adj.get(phase, [])
                if neighbor not in visited
            )
        return visited

    @property
    def phases(self) -> list[str]:
        return list(self._phases)

    @property
    def transitions(self) -> list[dict[str, str]]:
        return list(self._transitions)

    def next_phase(self, current: str) -> str | None:
        targets = self._adj.get(current, [])
        if not targets:
            return None
        if len(targets) == 1:
            return targets[0]
        return None

    def possible_next(self, current: str) -> list[str]:
        return list(self._adj.get(current, []))

    def is_valid_transition(self, from_phase: str, to_phase: str) -> bool:
        return to_phase in self._adj.get(from_phase, [])

    def index_of(self, phase: str) -> int:
        try:
            return self._phases.index(phase)
        except ValueError:
            return -1

    def progress(self, phase: str) -> float:
        idx = self.index_of(phase)
        if idx < 0:
            return 0.0
        total = len(self._phases)
        if total <= 1:
            return 100.0
        return ((idx + 1) / total) * 100
