"""ToolAdapter ABC — the contract between the orchestrator and all external tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any


class ToolCapability(StrEnum):
    LINT = "lint"
    TYPING = "typing"
    TESTING = "testing"
    CODE_GRAPH = "code_graph"
    SANDBOX = "sandbox"
    VERSIONING = "versioning"
    WORKFLOW = "workflow"


class ToolAdapter(ABC):
    """Interface for all tool integrations. Orchestrator talks to capabilities, never tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""

    @property
    @abstractmethod
    def capability(self) -> ToolCapability:
        """The capability this adapter provides."""

    @abstractmethod
    async def validate(self, task: Any) -> bool:
        """Check if this adapter can handle the given task."""

    @abstractmethod
    async def execute(self, task: Any) -> dict[str, Any]:
        """Execute the tool and return results."""

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Check if the underlying tool is available and functioning."""
