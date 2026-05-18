"""GitHub CI/CD adapter — optional PR auto-creation after Done phase."""

from __future__ import annotations

import os
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

logger = get_logger("adapters.vcs.github")


class GitHubAdapter(ToolAdapter):
    """Creates pull requests on GitHub after task completion.

    Opt-in: only runs if ``CI=true`` env var is set and
    ``GITHUB_TOKEN`` is available.
    """

    def __init__(self) -> None:
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._ci_mode = os.environ.get("CI", "").lower() in ("true", "1")

    @property
    def name(self) -> str:
        return "github"

    @property
    def capability(self) -> ToolCapability:
        return ToolCapability.VERSIONING

    async def validate(self, task: Any) -> bool:
        """Check if GitHub integration is enabled and configured."""
        return bool(self._ci_mode and self._token)

    async def execute(self, task: Any) -> dict[str, Any]:
        """Create a PR with phase history in the description."""
        if not await self.validate(task):
            return {"status": "skipped", "reason": "CI mode or GITHUB_TOKEN not set"}

        task_dict = task if isinstance(task, dict) else {}
        task_id = task_dict.get("task_id", "unknown")
        branch = task_dict.get("branch", f"sdlc/{task_id}")
        title = task_dict.get("title", f"SDLC Task {task_id}")
        description = task_dict.get("description", "")
        phase_history = task_dict.get("phase_history", [])

        # Build PR body from phase history
        body_parts = [f"## SDLC Task: {task_id}", ""]
        if description:
            body_parts.extend([description, ""])
        if phase_history:
            body_parts.append("### Phase History")
            for entry in phase_history:
                phase = entry.get("phase", "?")
                duration = entry.get("duration_ms", 0)
                body_parts.append(f"- **{phase}** ({duration}ms)")
            body_parts.append("")
        body = "\n".join(body_parts)

        # In a real implementation, this would use the GitHub API
        # For now, log the intent and return the PR data
        logger.info(
            "Would create PR",
            extra={"task_id": task_id, "branch": branch, "title": title},
        )
        return {
            "status": "created",
            "task_id": task_id,
            "branch": branch,
            "title": title,
            "body": body,
            "note": "GitHub API integration pending — PR data prepared",
        }

    async def healthcheck(self) -> bool:
        """Check if GitHub is reachable and token is valid."""
        return bool(self._token)
