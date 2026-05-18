"""Phase contract system — input/output validation, invariants, transition guards.

TODO #9: Without explicit contracts, phases become fuzzy and determinism collapses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.phase_contracts")


class PhaseContract(BaseModel):
    """Contract defining required inputs, outputs, validators, and failure paths."""

    phase: str
    required_inputs: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    failure_paths: list[str] = Field(default_factory=list)
    transition_guards: list[str] = Field(default_factory=list)


class ContractViolation(BaseModel):
    """A detected contract violation."""

    phase: str
    violation_type: str  # missing_input, missing_output, invariant, guard
    detail: str
    severity: str = "error"


class PhaseContractManager:
    """Manages and enforces phase contracts for deterministic execution."""

    def __init__(self) -> None:
        self._contracts: dict[str, PhaseContract] = {}

    def register(self, contract: PhaseContract) -> None:
        self._contracts[contract.phase] = contract

    def register_defaults(self) -> None:
        """Register default contracts for standard SDLC phases."""
        defaults = [
            PhaseContract(
                phase="Specs",
                required_inputs=["user_request"],
                required_outputs=["spec_output"],
                validators=["schema_check"],
                invariants=["spec_output_not_empty"],
            ),
            PhaseContract(
                phase="Planning",
                required_inputs=["spec_output"],
                required_outputs=["plan_output"],
                validators=["schema_check"],
                invariants=["plan_output_not_empty"],
            ),
            PhaseContract(
                phase="Coding",
                required_inputs=["plan_output"],
                required_outputs=["code_output"],
                validators=["ruff", "mypy"],
                invariants=["code_output_not_empty"],
            ),
            PhaseContract(
                phase="Review",
                required_inputs=["code_output"],
                required_outputs=["review_output"],
                validators=["schema_check"],
                transition_guards=["confidence_gate"],
            ),
            PhaseContract(
                phase="Testing",
                required_inputs=["code_output"],
                required_outputs=["test_output"],
                validators=["pytest"],
                invariants=["tests_pass"],
            ),
        ]
        for c in defaults:
            self.register(c)

    def validate_inputs(self, phase: str, available: dict[str, str]) -> list[ContractViolation]:
        """Validate that required inputs are present before phase starts."""
        contract = self._contracts.get(phase)
        if contract is None:
            return []
        violations: list[ContractViolation] = []
        for inp in contract.required_inputs:
            if inp not in available or not available[inp]:
                violations.append(ContractViolation(
                    phase=phase, violation_type="missing_input",
                    detail=f"Required input missing: {inp}",
                ))
        return violations

    def validate_outputs(self, phase: str, produced: dict[str, str]) -> list[ContractViolation]:
        """Validate that required outputs were produced after phase completes."""
        contract = self._contracts.get(phase)
        if contract is None:
            return []
        violations: list[ContractViolation] = []
        for out in contract.required_outputs:
            if out not in produced or not produced[out]:
                violations.append(ContractViolation(
                    phase=phase, violation_type="missing_output",
                    detail=f"Required output missing: {out}",
                ))
        return violations

    def check_transition_guards(self, phase: str, context: dict[str, Any]) -> list[ContractViolation]:
        """Check transition guards before allowing phase completion."""
        contract = self._contracts.get(phase)
        if contract is None:
            return []
        violations: list[ContractViolation] = []
        for guard in contract.transition_guards:
            if not context.get(guard, False):
                violations.append(ContractViolation(
                    phase=phase, violation_type="guard",
                    detail=f"Transition guard not satisfied: {guard}",
                ))
        return violations

    def get_validators(self, phase: str) -> list[str]:
        """Get the required validators for a phase."""
        contract = self._contracts.get(phase)
        return list(contract.validators) if contract else []

    def get_failure_paths(self, phase: str) -> list[str]:
        """Get the allowed failure paths for a phase."""
        contract = self._contracts.get(phase)
        return list(contract.failure_paths) if contract else []

    def get_contract(self, phase: str) -> PhaseContract | None:
        return self._contracts.get(phase)

    def all_contracts(self) -> dict[str, dict[str, Any]]:
        return {name: c.model_dump() for name, c in self._contracts.items()}
