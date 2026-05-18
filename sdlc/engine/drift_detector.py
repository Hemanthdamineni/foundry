"""Architecture drift detection — planned vs actual comparison.

TODO #22: Detects layer violations, circular dependencies, and drift from spec.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.drift_detector")


class DriftViolation(BaseModel):
    """A detected architecture drift violation."""

    violation_type: str  # layer_violation, circular_dep, naming, missing_module
    severity: str = "warning"  # info, warning, error
    description: str = ""
    file_path: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class DriftReport(BaseModel):
    """Full drift analysis report."""

    violations: list[DriftViolation] = Field(default_factory=list)
    consistency_score: float = 1.0  # 0.0 = fully drifted, 1.0 = perfectly aligned
    layer_violations: int = 0
    circular_dependencies: int = 0
    missing_modules: int = 0
    naming_violations: int = 0

    @property
    def has_critical(self) -> bool:
        return any(v.severity == "error" for v in self.violations)


# ── Layer Rules ──────────────────────────────────────────────────────

# Allowed import directions: higher layers can import from lower layers.
# Lower layers MUST NOT import from higher layers.
LAYER_ORDER = {
    "models": 0,       # Base data models — imports nothing from sdlc
    "exceptions": 0,   # Base exceptions
    "log": 0,          # Logging — pure utility
    "config": 1,       # Configuration — imports models
    "adapters": 2,     # Tool adapters — imports models, config
    "engine": 3,       # Core engine — imports adapters, models
    "validators": 3,   # Validation — imports adapters, models
    "runtime": 4,      # MCP server — imports everything
    "cli": 4,          # CLI — imports everything
}


class DriftDetector:
    """Detects architecture drift by analyzing import graph and naming conventions."""

    def __init__(self) -> None:
        self._planned_structure: dict[str, Any] = {}

    def set_planned_structure(self, structure: dict[str, Any]) -> None:
        """Set the planned architecture for comparison."""
        self._planned_structure = structure

    def analyze_imports(
        self,
        import_graph: dict[str, list[str]],
    ) -> DriftReport:
        """Analyze the import graph for layer violations and circular deps."""
        report = DriftReport()

        # Check layer violations
        for source, targets in import_graph.items():
            source_layer = self._get_layer(source)
            for target in targets:
                target_layer = self._get_layer(target)
                if source_layer is not None and target_layer is not None:
                    if source_layer < target_layer:
                        report.violations.append(DriftViolation(
                            violation_type="layer_violation",
                            severity="error",
                            description=(
                                f"'{source}' (layer {source_layer}) imports "
                                f"'{target}' (layer {target_layer}) — upward import"
                            ),
                            file_path=source,
                            details={"source_layer": source_layer, "target_layer": target_layer},
                        ))
                        report.layer_violations += 1

        # Check circular dependencies
        cycles = self._find_cycles(import_graph)
        for cycle in cycles:
            report.violations.append(DriftViolation(
                violation_type="circular_dep",
                severity="error",
                description=f"Circular dependency: {' → '.join(cycle)}",
                details={"cycle": cycle},
            ))
            report.circular_dependencies += 1

        # Calculate consistency score
        total_imports = sum(len(v) for v in import_graph.values())
        if total_imports > 0:
            violation_count = report.layer_violations + report.circular_dependencies
            report.consistency_score = max(0.0, 1.0 - (violation_count / total_imports))

        return report

    def _get_layer(self, module_path: str) -> int | None:
        """Determine the layer number for a module path."""
        parts = module_path.replace("/", ".").split(".")
        for part in parts:
            if part in LAYER_ORDER:
                return LAYER_ORDER[part]
        return None

    def _find_cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """Find circular dependencies using DFS cycle detection."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    idx = path.index(neighbor) if neighbor in path else -1
                    if idx >= 0:
                        cycles.append(path[idx:] + [neighbor])
            path.pop()
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles[:10]  # Cap at 10 cycles
