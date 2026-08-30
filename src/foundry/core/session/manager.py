"""SessionManager — persistent session state across restarts.

Sessions are the fundamental unit of agent continuity. A session preserves:
- Conversation history (messages, tool calls, responses)
- Working state (current phase, active tasks, pending approvals)
- Context window (what the agent "sees" right now)
- Workspace association (which workspace this session operates in)

Sessions can be:
- Created (new conversation)
- Paused (state saved to disk, agent can resume later)
- Resumed (state restored, agent continues from where it left off)
- Archived (completed or abandoned, kept for history)

Architecture reference:
    L2 Session Runtime — "How does execution persist?"
    CH Chronicle — sessions are chronicle-tracked
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.session")


# --------------------------------------------------------------------------- #
#  Session state
# --------------------------------------------------------------------------- #


class SessionStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    RESUMED = "resumed"
    ARCHIVED = "archived"


@dataclass
class SessionMessage:
    """A single message in the session conversation."""

    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: list[dict[str, Any]] | None = None
    tool_results: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", 0.0),
            tool_calls=data.get("tool_calls"),
            tool_results=data.get("tool_results"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionState:
    """Complete session state — the agent's "brain" at a point in time."""

    session_id: str
    workspace_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = SessionStatus.ACTIVE

    # Conversation
    messages: list[SessionMessage] = field(default_factory=list)

    # Working state
    current_phase: str | None = None
    active_tasks: list[str] = field(default_factory=list)
    pending_approvals: list[str] = field(default_factory=list)

    # Context window
    context_window: dict[str, Any] = field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "messages": [m.to_dict() for m in self.messages],
            "current_phase": self.current_phase,
            "active_tasks": self.active_tasks,
            "pending_approvals": self.pending_approvals,
            "context_window": self.context_window,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        messages = [
            SessionMessage.from_dict(m) for m in data.get("messages", [])
        ]
        return cls(
            session_id=data.get("session_id", ""),
            workspace_id=data.get("workspace_id"),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            status=data.get("status", SessionStatus.ACTIVE),
            messages=messages,
            current_phase=data.get("current_phase"),
            active_tasks=data.get("active_tasks", []),
            pending_approvals=data.get("pending_approvals", []),
            context_window=data.get("context_window", {}),
            metadata=data.get("metadata", {}),
        )


# --------------------------------------------------------------------------- #
#  SessionManager
# --------------------------------------------------------------------------- #


class SessionManager:
    """Manages session lifecycle — create, pause, resume, archive.

    Sessions are persisted to the SQLite store and can be resumed across
    restarts. The SessionManager coordinates with the Chronicle to track
    all session state changes.

    Usage::

        mgr = SessionManager(store, chronicle)
        session = mgr.create(workspace_id="ws_abc")
        mgr.add_message(session.session_id, SessionMessage(role="user", content="Hello"))
        mgr.pause(session.session_id)
        # ... later ...
        session = mgr.resume(session.session_id)
    """

    def __init__(self, store: Any, chronicle: Any | None = None) -> None:
        self._store = store
        self._chronicle = chronicle
        self._sessions: dict[str, SessionState] = {}

    async def create(
        self,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionState:
        """Create a new session."""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"

        state = SessionState(
            session_id=session_id,
            workspace_id=workspace_id,
            metadata=metadata or {},
        )

        self._sessions[session_id] = state

        # Persist to store
        await self._save(state)

        # Chronicle the creation
        if self._chronicle:
            await self._chronicle.append(
                "session.created",
                {"session_id": session_id, "workspace_id": workspace_id},
                workspace_id=workspace_id,
            )

        log.info("session created: %s", session_id)
        return state

    async def get(self, session_id: str) -> SessionState | None:
        """Get session state by ID."""
        # Try in-memory first
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from store
        state = await self._load(session_id)
        if state:
            self._sessions[session_id] = state
        return state

    async def pause(self, session_id: str) -> SessionState | None:
        """Pause a session (save state, mark as paused)."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.status = SessionStatus.PAUSED
        state.updated_at = time.time()

        await self._save(state)

        if self._chronicle:
            await self._chronicle.append(
                "session.paused",
                {"session_id": session_id, "message_count": len(state.messages)},
                workspace_id=state.workspace_id,
            )

        log.info("session paused: %s", session_id)
        return state

    async def resume(self, session_id: str) -> SessionState | None:
        """Resume a paused session (restore state, mark as active)."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.status = SessionStatus.RESUMED
        state.updated_at = time.time()

        await self._save(state)

        if self._chronicle:
            await self._chronicle.append(
                "session.resumed",
                {"session_id": session_id, "message_count": len(state.messages)},
                workspace_id=state.workspace_id,
            )

        log.info("session resumed: %s", session_id)
        return state

    async def archive(self, session_id: str) -> SessionState | None:
        """Archive a session (completed or abandoned)."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.status = SessionStatus.ARCHIVED
        state.updated_at = time.time()

        await self._save(state)

        if self._chronicle:
            await self._chronicle.append(
                "session.archived",
                {"session_id": session_id, "message_count": len(state.messages)},
                workspace_id=state.workspace_id,
            )

        log.info("session archived: %s", session_id)
        return state

    async def add_message(
        self,
        session_id: str,
        message: SessionMessage,
    ) -> SessionState | None:
        """Add a message to the session conversation."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.messages.append(message)
        state.updated_at = time.time()

        await self._save(state)
        return state

    async def update_phase(self, session_id: str, phase: str) -> SessionState | None:
        """Update the current phase of a session."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.current_phase = phase
        state.updated_at = time.time()

        await self._save(state)
        return state

    async def add_task(self, session_id: str, task_id: str) -> SessionState | None:
        """Add a task to the session's active tasks."""
        state = await self.get(session_id)
        if state is None:
            return None

        if task_id not in state.active_tasks:
            state.active_tasks.append(task_id)
            state.updated_at = time.time()
            await self._save(state)

        return state

    async def remove_task(self, session_id: str, task_id: str) -> SessionState | None:
        """Remove a task from the session's active tasks."""
        state = await self.get(session_id)
        if state is None:
            return None

        if task_id in state.active_tasks:
            state.active_tasks.remove(task_id)
            state.updated_at = time.time()
            await self._save(state)

        return state

    async def update_context(
        self,
        session_id: str,
        context: dict[str, Any],
    ) -> SessionState | None:
        """Update the session's context window."""
        state = await self.get(session_id)
        if state is None:
            return None

        state.context_window.update(context)
        state.updated_at = time.time()

        await self._save(state)
        return state

    async def list_sessions(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SessionState]:
        """List sessions with optional filters."""
        # For now, return in-memory sessions
        # TODO: query from store when store supports session listing
        results = list(self._sessions.values())

        if workspace_id:
            results = [s for s in results if s.workspace_id == workspace_id]
        if status:
            results = [s for s in results if s.status == status]

        return sorted(results, key=lambda s: s.updated_at, reverse=True)[:limit]

    # -- Persistence -------------------------------------------------------- #

    async def _save(self, state: SessionState) -> None:
        """Save session state to the store."""
        # Use checkpoint mechanism for session persistence
        try:
            await self._store.save_checkpoint(
                task_id=state.session_id,
                data=state.to_dict(),
            )
        except Exception as exc:
            log.warning("failed to save session %s: %s", state.session_id, exc)

    async def _load(self, session_id: str) -> SessionState | None:
        """Load session state from the store."""
        try:
            checkpoint = await self._store.load_checkpoint(
                task_id=session_id,
                checkpoint_id="session_state",
            )
            if checkpoint:
                return SessionState.from_dict(checkpoint)
        except Exception as exc:
            log.warning("failed to load session %s: %s", session_id, exc)
        return None
