"""Exception hierarchy for the SDLC models and orchestrator.

From Helix/foundry/sdlc/exceptions.py, extended with additional
exception types needed by the sdlc-models package.
"""

from __future__ import annotations

from typing import Any


class SDLCError(Exception):
    """Base exception for all SDLC errors."""

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


class ConfigError(SDLCError):
    """Configuration loading or validation error."""


class StoreError(SDLCError):
    """Persistence layer error."""


class PhaseError(SDLCError):
    """Phase transition or validation error."""


class ToolError(SDLCError):
    """Tool adapter execution error."""


class PolicyError(SDLCError):
    """Execution policy decision error."""


class CheckpointError(SDLCError):
    """Checkpoint save/restore error."""


class SandboxError(SDLCError):
    """Sandbox execution isolation error."""


class DebateError(SDLCError):
    """Debate runtime or consensus error."""


class JudgeError(SDLCError):
    """Judge evaluation error."""


class ModelError(SDLCError):
    """Model routing or inference error."""


class CodeGraphError(SDLCError):
    """Code graph / AST parsing error."""


class PhaseGraphError(SDLCError):
    """Phase graph definition or traversal error."""


class OrchestratorError(SDLCError):
    """Top-level orchestrator execution error."""


class SchemaViolationError(SDLCError):
    """Phase output schema validation error."""


__all__ = [
    "SDLCError",
    "ConfigError",
    "StoreError",
    "PhaseError",
    "ToolError",
    "PolicyError",
    "CheckpointError",
    "SandboxError",
    "DebateError",
    "JudgeError",
    "ModelError",
    "CodeGraphError",
    "PhaseGraphError",
    "OrchestratorError",
    "SchemaViolationError",
]
