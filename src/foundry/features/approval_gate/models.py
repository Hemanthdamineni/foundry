"""Data models for the approval gate — human-in-the-loop checkpoint approvals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ApprovalRequest:
    """A pending approval request blocking a phase transition."""

    id: str
    task_id: str
    phase: str
    summary: str
    created_at: datetime = field(default_factory=_utc_now)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_pending(self) -> bool:
        return self.resolved_at is None

    @property
    def is_approved(self) -> bool:
        return self.resolved_at is not None and self.reason is None

    @property
    def is_rejected(self) -> bool:
        return self.resolved_at is not None and self.reason is not None


@dataclass
class ApprovalDecision:
    """The decision record after an approval request is resolved."""

    request_id: str
    approved: bool
    reason: str | None
    resolved_by: str
    resolved_at: datetime = field(default_factory=_utc_now)
