"""MemoryAdapter — ToolAdapter wrapper over Acervo for cross-task memory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sdlc.adapters.base import ToolAdapter, ToolCapability

if TYPE_CHECKING:
    from sdlc.adapters.memory.acervo import Acervo


class MemoryAdapter(ToolAdapter):
    """ToolAdapter that wraps Acervo for deterministic cross-task memory."""

    name: str = "memory"
    capability: ToolCapability = ToolCapability.CODE_GRAPH

    def __init__(self, acervo: Acervo | None = None) -> None:
        self._acervo = acervo

    def _result(
        self,
        *,
        passed: bool,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "capability": self.capability.value,
            "passed": passed,
            "summary": summary,
            "details": details or {},
        }

    async def validate(self, task: Any) -> bool:
        if isinstance(task, dict):
            return "content" in task or "query" in task
        return self._acervo is not None

    async def execute(self, task: Any) -> dict[str, Any]:
        if self._acervo is None:
            return self._result(passed=False, summary="Acervo not initialized")

        if not isinstance(task, dict):
            return self._result(passed=False, summary="Task must be a dict")

        if "content" in task:
            engram = await self._acervo.store(
                content=task["content"],
                task_id=task.get("task_id", ""),
                phase=task.get("phase", ""),
                tags=task.get("tags", []),
                source=task.get("source", "unknown"),
                importance=task.get("importance", 0.5),
                metadata=task.get("metadata", {}),
            )
            return self._result(
                passed=True,
                summary=f"Stored engram {engram.engram_id}",
                details={"engram_id": engram.engram_id},
            )

        if "query" in task:
            results = await self._acervo.query(
                phase=task.get("phase"),
                tags=task.get("tags"),
                keywords=task.get("keywords"),
                source=task.get("source"),
                min_importance=task.get("min_importance", 0.3),
                limit=task.get("limit", 10),
            )
            return self._result(
                passed=True,
                summary=f"Found {len(results)} engrams",
                details={
                    "engrams": [e.model_dump(mode="json") for e in results],
                    "count": len(results),
                },
            )

        return self._result(passed=False, summary="No content or query provided")

    async def healthcheck(self) -> bool:
        return self._acervo is not None
