"""Bootstrap engine — automatic workspace initialization and upgrade."""

from sdlc_mcp.bootstrap.engine import BootstrapEngine
from sdlc_mcp.bootstrap.workspace import detect_workspace, WorkspaceState

__all__ = ["BootstrapEngine", "detect_workspace", "WorkspaceState"]
