"""VCS adapters — git worktree and GitHub CI/CD integration."""

from foundry.features.sdlc_runtime.adapters.vcs.git import GitAdapter
from foundry.features.sdlc_runtime.adapters.vcs.github import GitHubAdapter

__all__ = ["GitAdapter", "GitHubAdapter"]
