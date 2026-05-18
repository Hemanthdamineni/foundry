"""Git worktree adapter — branch-per-task, atomic commits, tag/snapshot/checkpoint."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.vcs.git")

# Maximum slug length for branch names
_MAX_SLUG_LEN = 40


def _slugify(text: str) -> str:
    """Convert description to a URL-safe slug for branch names."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:_MAX_SLUG_LEN].rstrip("-")


async def _run_git(
    *args: str,
    cwd: str | Path | None = None,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )


class GitAdapter(ToolAdapter):
    """Git version control adapter implementing ToolAdapter."""

    def __init__(self, workspace: str | Path) -> None:
        self._workspace = Path(workspace)

    @property
    def name(self) -> str:
        return "git"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.VERSIONING

    async def validate(self, task: Any) -> bool:
        """Check if we're in a git repository."""
        rc, _, _ = await _run_git("rev-parse", "--git-dir", cwd=self._workspace)
        return rc == 0

    async def execute(self, task: Any) -> dict[str, Any]:
        """Execute a git operation based on task type."""
        action = task.get("action", "status") if isinstance(task, dict) else "status"
        dispatch = {
            "init": self._init_repo,
            "status": self._status,
            "create_branch": self._create_branch,
            "commit": self._commit,
            "tag": self._tag,
            "rollback": self._rollback,
            "checkpoint": self._checkpoint,
        }
        handler = dispatch.get(action, self._status)
        return await handler(task if isinstance(task, dict) else {})

    async def healthcheck(self) -> bool:
        """Check if git is available."""
        rc, _, _ = await _run_git("--version")
        return rc == 0

    # ── Git Operations ──────────────────────────────────────────

    async def init_repo(self) -> dict[str, Any]:
        """Initialize a git repo if one doesn't exist."""
        return await self._init_repo({})

    async def _init_repo(self, _task: dict[str, Any]) -> dict[str, Any]:
        rc, _, _ = await _run_git("rev-parse", "--git-dir", cwd=self._workspace)
        if rc == 0:
            return {"action": "init", "status": "already_initialized"}
        rc, out, err = await _run_git("init", cwd=self._workspace)
        if rc != 0:
            return {"action": "init", "status": "error", "error": err}
        # Initial commit so branches work
        rc2, _, _ = await _run_git(
            "commit", "--allow-empty", "-m", "sdlc: initial commit",
            cwd=self._workspace,
        )
        return {"action": "init", "status": "initialized", "output": out}

    async def _status(self, _task: dict[str, Any]) -> dict[str, Any]:
        rc, out, err = await _run_git("status", "--porcelain", cwd=self._workspace)
        if rc != 0:
            return {"action": "status", "status": "error", "error": err}
        _, branch, _ = await _run_git(
            "branch", "--show-current", cwd=self._workspace,
        )
        return {
            "action": "status",
            "branch": branch,
            "dirty_files": len(out.splitlines()) if out else 0,
            "changes": out,
        }

    async def create_task_branch(
        self,
        task_id: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a branch for a task: sdlc/<task_id>-<slug>."""
        return await self._create_branch({
            "task_id": task_id,
            "description": description,
        })

    async def _create_branch(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task.get("task_id", "unknown")
        description = task.get("description", "")
        slug = _slugify(description) if description else "task"
        branch = f"sdlc/{task_id}-{slug}"
        rc, out, err = await _run_git(
            "checkout", "-b", branch, cwd=self._workspace,
        )
        if rc != 0:
            return {"action": "create_branch", "status": "error", "error": err}
        return {"action": "create_branch", "branch": branch, "status": "created"}

    async def phase_commit(
        self,
        task_id: str,
        phase: str,
        summary: str,
    ) -> dict[str, Any]:
        """Create an atomic phase-scoped commit."""
        return await self._commit({
            "task_id": task_id,
            "phase": phase,
            "summary": summary,
        })

    async def _commit(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task.get("task_id", "unknown")
        phase = task.get("phase", "unknown")
        summary = task.get("summary", "phase complete")
        message = f"sdlc({task_id}): {phase} — {summary}"

        # Stage all changes
        rc, _, err = await _run_git("add", "-A", cwd=self._workspace)
        if rc != 0:
            return {"action": "commit", "status": "error", "error": err}

        # Check if there are staged changes
        rc, diff, _ = await _run_git(
            "diff", "--cached", "--name-only", cwd=self._workspace,
        )
        if not diff:
            return {"action": "commit", "status": "nothing_to_commit"}

        rc, out, err = await _run_git(
            "commit", "-m", message, cwd=self._workspace,
        )
        if rc != 0:
            return {"action": "commit", "status": "error", "error": err}

        _, sha, _ = await _run_git("rev-parse", "HEAD", cwd=self._workspace)
        return {
            "action": "commit",
            "status": "committed",
            "sha": sha,
            "message": message,
            "files_changed": len(diff.splitlines()),
        }

    async def _tag(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task.get("task_id", "unknown")
        phase = task.get("phase", "done")
        tag_name = f"sdlc/{task_id}/{phase}"
        rc, _, err = await _run_git(
            "tag", tag_name, cwd=self._workspace,
        )
        if rc != 0:
            return {"action": "tag", "status": "error", "error": err}
        return {"action": "tag", "tag": tag_name, "status": "created"}

    async def _rollback(self, task: dict[str, Any]) -> dict[str, Any]:
        target = task.get("target")  # commit SHA or tag
        if not target:
            return {"action": "rollback", "status": "error", "error": "No target specified"}
        rc, _, err = await _run_git(
            "reset", "--hard", target, cwd=self._workspace,
        )
        if rc != 0:
            return {"action": "rollback", "status": "error", "error": err}
        return {"action": "rollback", "status": "rolled_back", "target": target}

    async def _checkpoint(self, task: dict[str, Any]) -> dict[str, Any]:
        """Commit + tag + return state for checkpoint system."""
        commit_result = await self._commit(task)
        if commit_result.get("status") == "error":
            return commit_result
        tag_result = await self._tag(task)
        return {
            "action": "checkpoint",
            "commit": commit_result,
            "tag": tag_result,
            "status": "checkpointed",
        }
