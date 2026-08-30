"""AuditTrail — structured audit logging for all operations.

Provides a high-level audit interface that tracks user actions, system
events, and security events. Built on Chronicle for append-only storage.

Architecture reference:
    OB Observability — "Audit trail and compliance logging"
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.audit")


# --------------------------------------------------------------------------- #
#  Event categories
# # --------------------------------------------------------------------------- #


class AuditCategory:
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"
    SECURITY_EVENT = "security_event"
    GOVERNANCE_DECISION = "governance_decision"
    TASK_LIFECYCLE = "task_lifecycle"
    WORKSPACE_OPERATION = "workspace_operation"
    CONFIGURATION_CHANGE = "configuration_change"


@dataclass
class AuditEntry:
    """A single audit trail entry."""

    entry_id: str
    category: str
    action: str
    actor: str
    target: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: str | None = None
    task_id: str | None = None
    workspace_id: str | None = None
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "category": self.category,
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "details": self.details,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "success": self.success,
            "error_message": self.error_message,
        }


# --------------------------------------------------------------------------- #
#  AuditTrail
# --------------------------------------------------------------------------- #


class AuditTrail:
    """Structured audit logging for all operations.

    Usage::

        audit = AuditTrail()

        # Track user action
        await audit.log_action(
            category=AuditCategory.USER_ACTION,
            action="create_task",
            actor="user_123",
            target="task_456",
            details={"prompt": "Implement auth"},
        )

        # Track governance decision
        await audit.log_action(
            category=AuditCategory.GOVERNANCE_DECISION,
            action="check_passed",
            actor="system",
            target="task_456",
            details={"rigor": "standard", "max_repairs": 3},
        )

        # Query audit trail
        entries = await audit.query(category="user_action", limit=100)
    """

    # In-memory storage (can be extended to persist via Chronicle)
    MAX_ENTRIES = 10000

    def __init__(self, chronicle: Any | None = None) -> None:
        self._chronicle = chronicle
        self._entries: list[AuditEntry] = []
        self._start_time = time.time()

    async def log_action(
        self,
        *,
        category: str,
        action: str,
        actor: str,
        target: str = "",
        details: dict[str, Any] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditEntry:
        """Log an audit event."""
        entry = AuditEntry(
            entry_id=f"audit_{uuid.uuid4().hex[:12]}",
            category=category,
            action=action,
            actor=actor,
            target=target,
            details=details or {},
            session_id=session_id,
            task_id=task_id,
            workspace_id=workspace_id,
            success=success,
            error_message=error_message,
        )

        self._entries.append(entry)

        # Enforce max entries (drop oldest)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]

        # Persist to Chronicle if available
        if self._chronicle:
            try:
                await self._chronicle.append(
                    f"audit.{category}.{action}",
                    entry.to_dict(),
                    task_id=task_id,
                )
            except Exception as exc:
                log.warning("failed to persist audit entry to Chronicle: %s", exc)

        log.debug(
            "audit: [%s] %s by %s → %s (success=%s)",
            category,
            action,
            actor,
            target,
            success,
        )

        return entry

    async def query(
        self,
        *,
        category: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        results = list(self._entries)

        if category:
            results = [e for e in results if e.category == category]
        if action:
            results = [e for e in results if e.action == action]
        if actor:
            results = [e for e in results if e.actor == actor]
        if task_id:
            results = [e for e in results if e.task_id == task_id]
        if workspace_id:
            results = [e for e in results if e.workspace_id == workspace_id]
        if since:
            results = [e for e in results if e.timestamp >= since]

        # Most recent first, limit
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def get_task_history(self, task_id: str) -> list[AuditEntry]:
        """Get all audit entries for a specific task."""
        return await self.query(task_id=task_id, limit=1000)

    async def get_actor_history(self, actor: str) -> list[AuditEntry]:
        """Get all audit entries for a specific actor."""
        return await self.query(actor=actor, limit=1000)

    @property
    def stats(self) -> dict[str, Any]:
        categories: dict[str, int] = {}
        for entry in self._entries:
            categories[entry.category] = categories.get(entry.category, 0) + 1

        return {
            "total_entries": len(self._entries),
            "categories": categories,
            "uptime_s": time.time() - self._start_time,
        }

    def clear(self) -> int:
        """Clear all audit entries. Returns the number of entries cleared."""
        count = len(self._entries)
        self._entries.clear()
        return count
