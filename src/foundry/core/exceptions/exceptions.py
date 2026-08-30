"""Foundry exception hierarchy — all feature-level errors inherit from FoundryError."""

from __future__ import annotations

from typing import Any


class FoundryError(Exception):
    """Base exception for all Foundry errors."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.failure_type = failure_type
        self.details = details or {}
        super().__init__(message)


class JudgeError(FoundryError):
    """LLM judge evaluation error."""


class DebateError(FoundryError):
    """Debate runtime or consensus error."""


class PhaseGraphError(FoundryError):
    """Phase graph validation or lookup error."""


class OrchestratorError(FoundryError):
    """Orchestrator-level phase transition error."""


class SchemaViolationError(FoundryError):
    """Raised when an output fails structural validation."""

    def __init__(
        self,
        message: str,
        *,
        section: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.section = section
        super().__init__(message, failure_type="schema_violation", details=details)


class StoreError(FoundryError):
    """Persistence layer error."""


class SandboxError(FoundryError):
    """Sandbox execution isolation error."""


class GuardrailError(FoundryError):
    """Guardrail policy violation error."""


class AuthError(FoundryError):
    """Authentication or authorization error."""


class SecretsError(FoundryError):
    """Secrets management error."""

class ConfigError(FoundryError):
    """Configuration error."""
    pass
