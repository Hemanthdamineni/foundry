"""VCS adapters — git worktree and GitHub CI/CD integration."""

from sdlc.adapters.vcs.git import GitAdapter
from sdlc.adapters.vcs.github import GitHubAdapter

__all__ = ["GitAdapter", "GitHubAdapter"]
