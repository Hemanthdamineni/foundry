"""Chronicle — append-only immutable event log (CH layer).

The Chronicle is the **system of record** for all state changes in Foundry.
Every significant event — task creation, phase transition, tool execution,
budget change, workspace mutation — is recorded as an immutable entry.

Key properties:
- **Append-only**: entries are never updated or deleted.
- **Ordered**: entries are monotonically increasing by sequence number.
- **Immutable**: once written, an entry's hash chain cannot be tampered with.
- **Queryable**: entries can be filtered by type, workspace, task, time range.

Built on the ``audit_events`` store table. Each entry is hash-chained
to provide tamper-evidence (similar to a blockchain, but simpler).

Architecture reference:
    CH Chronicle — "Append-only system of record"
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.chronicle")


# --------------------------------------------------------------------------- #
#  Chronicle entry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChronicleEntry:
    """A single immutable event in the chronicle."""

    sequence: int  # Monotonically increasing
    timestamp: float  # Unix epoch
    event_type: str  # "task.created", "phase.transition", "tool.executed", etc.
    workspace_id: str | None  # Workspace context
    task_id: str | None  # Task context
    data: dict[str, Any]  # Event payload
    previous_hash: str  # Hash of the previous entry (tamper chain)
    entry_hash: str  # Hash of this entry (computed from content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }


def _compute_hash(sequence: int, timestamp: float, event_type: str, data: dict[str, Any], previous_hash: str) -> str:
    """Compute SHA-256 hash of entry content for tamper detection."""
    content = json.dumps({
        "sequence": sequence,
        "timestamp": timestamp,
        "event_type": event_type,
        "data": data,
        "previous_hash": previous_hash,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
#  Chronicle store interface
# --------------------------------------------------------------------------- #


class Chronicle:
    """Append-only event log backed by the SQLite audit_events table.

    Usage::

        chronicle = Chronicle(store)
        await chronicle.append("task.created", {"prompt": "..."}, workspace_id="ws_abc", task_id="task_123")
        entries = await chronicle.query(event_type="task.*", limit=50)
    """

    def __init__(self, store: Any) -> None:
        """Initialize with a StoreBackend instance."""
        self._store = store
        self._last_hash: str = "genesis"
        self._sequence: int = 0
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Load the last sequence and hash from the store on first access."""
        if self._loaded:
            return
        try:
            # Query chronicle entries (stored with chronicle.* event types)
            entries = await self._store.task_events("_chronicle_meta", limit=1000)
            if entries:
                # Find the last chronicle entry
                chronicle_entries = [
                    e for e in entries
                    if e.get("event_type", "").startswith("chronicle.")
                ]
                if chronicle_entries:
                    last = chronicle_entries[-1]
                    payload = last.get("payload", {})
                    self._sequence = payload.get("sequence", 0)
                    self._last_hash = payload.get("entry_hash", "genesis")
        except Exception:
            # Table might not have meta entry yet — start fresh
            self._sequence = 0
            self._last_hash = "genesis"
        self._loaded = True

    async def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        workspace_id: str | None = None,
        task_id: str | None = None,
    ) -> ChronicleEntry:
        """Append an immutable entry to the chronicle.

        Returns the created entry with computed hash chain.
        """
        await self._ensure_loaded()

        self._sequence += 1
        timestamp = time.time()

        entry_hash = _compute_hash(
            self._sequence, timestamp, event_type, data, self._last_hash
        )

        entry = ChronicleEntry(
            sequence=self._sequence,
            timestamp=timestamp,
            event_type=event_type,
            workspace_id=workspace_id,
            task_id=task_id,
            data=data,
            previous_hash=self._last_hash,
            entry_hash=entry_hash,
        )

        # Persist to audit_events table
        await self._store.add_event(
            event_type=f"chronicle.{event_type}",
            payload=entry.to_dict(),
            task_id=task_id or "_chronicle_meta",
        )

        # Update chain state
        self._last_hash = entry_hash

        log.debug("chronicle append: seq=%d type=%s hash=%s", self._sequence, event_type, entry_hash[:8])
        return entry

    async def query(
        self,
        *,
        event_type: str | None = None,
        workspace_id: str | None = None,
        task_id: str | None = None,
        since_sequence: int | None = None,
        limit: int = 100,
    ) -> list[ChronicleEntry]:
        """Query chronicle entries with optional filters.

        Returns entries in chronological order (oldest first).
        """
        await self._ensure_loaded()

        # Query all audit events (chronicle uses chronicle.* event types)
        try:
            raw = await self._store.task_events(
                task_id or "_chronicle_meta",
                limit=limit * 10,  # fetch more to account for filtering
            )
        except Exception:
            return []

        entries = []
        for r in raw:
            event_type_raw = r.get("event_type", "")
            if not event_type_raw.startswith("chronicle."):
                continue

            payload = r.get("payload", {})
            if not payload or "sequence" not in payload:
                continue

            entry = ChronicleEntry(
                sequence=payload["sequence"],
                timestamp=payload["timestamp"],
                event_type=payload["event_type"],
                workspace_id=payload.get("workspace_id"),
                task_id=payload.get("task_id"),
                data=payload.get("data", {}),
                previous_hash=payload.get("previous_hash", ""),
                entry_hash=payload.get("entry_hash", ""),
            )

            # Apply filters
            if event_type and entry.event_type != event_type:
                continue
            if workspace_id and entry.workspace_id != workspace_id:
                continue
            if task_id and entry.task_id != task_id:
                continue
            if since_sequence and entry.sequence <= since_sequence:
                continue

            entries.append(entry)

        return sorted(entries, key=lambda e: e.sequence)[:limit]

    async def verify_chain(self) -> tuple[bool, int]:
        """Verify the integrity of the hash chain.

        Returns (is_valid, last_valid_sequence). If any entry's hash doesn't
        match its computed hash, or the previous_hash doesn't match the prior
        entry's hash, the chain is considered broken.
        """
        await self._ensure_loaded()

        entries = await self.query(limit=10000)
        if not entries:
            return True, 0

        prev_hash = "genesis"
        for entry in entries:
            expected_hash = _compute_hash(
                entry.sequence, entry.timestamp, entry.event_type,
                entry.data, prev_hash,
            )
            if entry.entry_hash != expected_hash:
                log.warning(
                    "chronicle chain broken at seq=%d: expected %s, got %s",
                    entry.sequence, expected_hash[:8], entry.entry_hash[:8],
                )
                return False, entry.sequence - 1
            if entry.previous_hash != prev_hash:
                log.warning(
                    "chronicle previous_hash mismatch at seq=%d",
                    entry.sequence,
                )
                return False, entry.sequence - 1
            prev_hash = entry.entry_hash

        return True, entries[-1].sequence

    @property
    def last_sequence(self) -> int:
        return self._sequence

    @property
    def last_hash(self) -> str:
        return self._last_hash
