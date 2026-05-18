"""Deterministic execution runtime — ensures same inputs produce same phase flow.

TODO #1: Deterministic phase transitions, execution ordering, task scheduling,
prompt hash locking, model routing determinism, replay-safe execution IDs.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("runtime.execution_runtime")


def _deterministic_id(seed: str) -> str:
    """Generate a deterministic execution ID from a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _replay_safe_id() -> str:
    """Generate a replay-safe execution ID (timestamp + random)."""
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:8]}"


class ExecutionContext(BaseModel):
    """Immutable execution context for deterministic phase transitions."""

    execution_id: str
    task_id: str
    phase: str
    iteration: int = 0
    prompt_hash: str = ""
    model_id: str = ""
    parent_execution_id: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhaseTransition(BaseModel):
    """A recorded phase transition for replay."""

    from_phase: str
    to_phase: str
    execution_id: str
    reason: str = ""
    approved_by: str = ""  # orchestrator, judge, etc.
    timestamp: str = ""
    deterministic: bool = True


class ArtifactContract(BaseModel):
    """Contract for stable artifact generation."""

    phase: str
    artifact_name: str
    content_hash: str = ""
    schema_version: int = 1
    required: bool = True
    validated: bool = False


class ExecutionRuntime:
    """Deterministic execution runtime — the core execution engine.

    Guarantees:
    - Same inputs → same phase flow (deterministic transitions)
    - Deterministic orchestration decisions
    - Reproducible retries
    - Deterministic recovery paths
    - Replay-safe execution IDs
    """

    def __init__(self) -> None:
        self._transitions: list[PhaseTransition] = []
        self._contexts: dict[str, ExecutionContext] = {}
        self._prompt_locks: dict[str, str] = {}  # phase → locked prompt hash
        self._model_locks: dict[str, str] = {}  # phase → locked model ID
        self._artifact_contracts: dict[str, list[ArtifactContract]] = {}
        self._execution_order: list[str] = []  # ordered phase list

    # ── Execution Context ───────────────────────────────────────

    def create_context(
        self,
        task_id: str,
        phase: str,
        *,
        iteration: int = 0,
        prompt_hash: str = "",
        model_id: str = "",
        parent_id: str = "",
        deterministic_seed: str = "",
    ) -> ExecutionContext:
        """Create a new execution context with a replay-safe ID."""
        if deterministic_seed:
            exec_id = _deterministic_id(f"{task_id}:{phase}:{iteration}:{deterministic_seed}")
        else:
            exec_id = _replay_safe_id()

        ctx = ExecutionContext(
            execution_id=exec_id,
            task_id=task_id,
            phase=phase,
            iteration=iteration,
            prompt_hash=prompt_hash or self._prompt_locks.get(phase, ""),
            model_id=model_id or self._model_locks.get(phase, ""),
            parent_execution_id=parent_id,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._contexts[exec_id] = ctx
        return ctx

    def get_context(self, execution_id: str) -> ExecutionContext | None:
        return self._contexts.get(execution_id)

    # ── Deterministic Phase Transitions ─────────────────────────

    def set_execution_order(self, phases: list[str]) -> None:
        """Set the deterministic execution order."""
        self._execution_order = list(phases)

    def next_phase(self, current_phase: str) -> str | None:
        """Get the deterministic next phase."""
        try:
            idx = self._execution_order.index(current_phase)
            if idx + 1 < len(self._execution_order):
                return self._execution_order[idx + 1]
        except ValueError:
            pass
        return None

    def record_transition(
        self,
        from_phase: str,
        to_phase: str,
        execution_id: str,
        *,
        reason: str = "",
        approved_by: str = "orchestrator",
    ) -> PhaseTransition:
        """Record a phase transition for replay."""
        transition = PhaseTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            execution_id=execution_id,
            reason=reason,
            approved_by=approved_by,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._transitions.append(transition)
        return transition

    def validate_transition(self, from_phase: str, to_phase: str) -> bool:
        """Validate that a phase transition is allowed by the execution order."""
        if not self._execution_order:
            return True  # No order set, allow all
        try:
            from_idx = self._execution_order.index(from_phase)
            to_idx = self._execution_order.index(to_phase)
            # Allow forward transitions and same-phase retries
            return to_idx >= from_idx
        except ValueError:
            return False

    # ── Prompt Hash Locking ─────────────────────────────────────

    def lock_prompt(self, phase: str, prompt_hash: str) -> None:
        """Lock a prompt hash for a phase — ensures deterministic prompt usage."""
        self._prompt_locks[phase] = prompt_hash

    def verify_prompt(self, phase: str, prompt_hash: str) -> bool:
        """Verify that the prompt matches the locked hash."""
        locked = self._prompt_locks.get(phase)
        if locked is None:
            return True  # No lock set
        return locked == prompt_hash

    # ── Model Routing Determinism ───────────────────────────────

    def lock_model(self, phase: str, model_id: str) -> None:
        """Lock a model ID for a phase — ensures deterministic routing."""
        self._model_locks[phase] = model_id

    def get_model(self, phase: str) -> str | None:
        """Get the locked model for a phase."""
        return self._model_locks.get(phase)

    # ── Artifact Contracts ──────────────────────────────────────

    def register_artifact_contract(
        self,
        phase: str,
        artifact_name: str,
        *,
        required: bool = True,
    ) -> ArtifactContract:
        """Register an expected artifact for a phase."""
        contract = ArtifactContract(
            phase=phase,
            artifact_name=artifact_name,
            required=required,
        )
        self._artifact_contracts.setdefault(phase, []).append(contract)
        return contract

    def validate_artifacts(self, phase: str, produced: dict[str, str]) -> dict[str, Any]:
        """Validate produced artifacts against contracts."""
        contracts = self._artifact_contracts.get(phase, [])
        missing: list[str] = []
        validated: list[str] = []

        for contract in contracts:
            if contract.artifact_name in produced:
                contract.content_hash = produced[contract.artifact_name]
                contract.validated = True
                validated.append(contract.artifact_name)
            elif contract.required:
                missing.append(contract.artifact_name)

        return {
            "phase": phase,
            "valid": len(missing) == 0,
            "validated": validated,
            "missing": missing,
        }

    # ── Replay ──────────────────────────────────────────────────

    def get_transition_log(self) -> list[dict[str, Any]]:
        """Get the full transition log for replay."""
        return [t.model_dump() for t in self._transitions]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_transitions": len(self._transitions),
            "active_contexts": len(self._contexts),
            "locked_prompts": len(self._prompt_locks),
            "locked_models": len(self._model_locks),
            "execution_order": self._execution_order,
        }
