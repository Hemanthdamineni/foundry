"""Team coordinator — manages parallel subagent coordination with path locking.

Handles multi-team orchestration, dependency-aware scheduling, path locking
to prevent concurrent edits to the same file, and merge coordination.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.team_coordinator")


class TeamDefinition(BaseModel):
    """A team of subagents working on a specific area."""

    team_id: str
    name: str
    subagent: str
    scope: list[str] = Field(default_factory=list)  # file path patterns
    depends_on: list[str] = Field(default_factory=list)
    status: str = "idle"  # idle, active, waiting, completed, failed
    assigned_files: list[str] = Field(default_factory=list)
    output: str = ""


class PathLock(BaseModel):
    """A lock on a file path to prevent concurrent edits."""

    path: str
    holder: str  # team_id
    acquired_at: str = ""


class MergeConflict(BaseModel):
    """A detected merge conflict between teams."""

    file_path: str
    team_a: str
    team_b: str
    resolution: str = "pending"  # pending, resolved, escalated


class TeamCoordinator:
    """Coordinates parallel team execution with path locking and merge management."""

    def __init__(self) -> None:
        self._teams: dict[str, TeamDefinition] = {}
        self._locks: dict[str, PathLock] = {}
        self._conflicts: list[MergeConflict] = []
        self._execution_order: list[list[str]] = []  # parallel groups
        self._lock = asyncio.Lock()

    def register_team(self, team: TeamDefinition) -> None:
        """Register a team for coordination."""
        self._teams[team.team_id] = team
        logger.info("Team registered", extra={"team_id": team.team_id, "name": team.name})

    def build_execution_order(self) -> list[list[str]]:
        """Build dependency-aware execution order as parallel groups.

        Teams within the same group can run in parallel.
        Groups must execute sequentially.
        """
        resolved: set[str] = set()
        groups: list[list[str]] = []
        remaining = set(self._teams.keys())

        while remaining:
            # Find teams whose dependencies are all resolved
            ready = [
                tid for tid in remaining
                if all(dep in resolved for dep in self._teams[tid].depends_on)
            ]
            if not ready:
                # Circular dependency — force remaining into one group
                logger.warning(
                    "Circular dependency detected, forcing group",
                    extra={"remaining": list(remaining)},
                )
                groups.append(list(remaining))
                break
            groups.append(ready)
            resolved.update(ready)
            remaining -= set(ready)

        self._execution_order = groups
        return groups

    async def acquire_path(self, path: str, team_id: str) -> bool:
        """Acquire a lock on a file path for exclusive editing."""
        async with self._lock:
            if path in self._locks and self._locks[path].holder != team_id:
                logger.warning(
                    "Path lock contention",
                    extra={"path": path, "holder": self._locks[path].holder, "requester": team_id},
                )
                return False
            self._locks[path] = PathLock(path=path, holder=team_id)
            return True

    async def release_path(self, path: str, team_id: str) -> bool:
        """Release a path lock."""
        async with self._lock:
            lock = self._locks.get(path)
            if lock and lock.holder == team_id:
                del self._locks[path]
                return True
            return False

    async def release_all(self, team_id: str) -> int:
        """Release all locks held by a team."""
        async with self._lock:
            released = 0
            to_remove = [p for p, lk in self._locks.items() if lk.holder == team_id]
            for path in to_remove:
                del self._locks[path]
                released += 1
            return released

    def check_conflicts(self) -> list[MergeConflict]:
        """Detect potential merge conflicts based on overlapping file assignments."""
        conflicts: list[MergeConflict] = []
        teams = list(self._teams.values())
        for i, team_a in enumerate(teams):
            for team_b in teams[i + 1 :]:
                overlap = set(team_a.assigned_files) & set(team_b.assigned_files)
                for path in overlap:
                    conflicts.append(MergeConflict(
                        file_path=path,
                        team_a=team_a.team_id,
                        team_b=team_b.team_id,
                    ))
        self._conflicts = conflicts
        return conflicts

    def get_status(self) -> dict[str, Any]:
        """Get full coordinator status."""
        return {
            "teams": {tid: t.model_dump() for tid, t in self._teams.items()},
            "active_locks": {p: lk.model_dump() for p, lk in self._locks.items()},
            "conflicts": [c.model_dump() for c in self._conflicts],
            "execution_order": self._execution_order,
        }
