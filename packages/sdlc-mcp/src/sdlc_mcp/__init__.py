"""sdlc-mcp: MCP server exposing SDLC task orchestration as tools.

This package provides a Model Context Protocol server that wraps the
Helix SDLC pipeline (judge evaluation, multi-agent debate, phase-graph
orchestration, and SQLite persistence) behind four tools:

- ``sdlc_create_task`` — create a new SDLC task
- ``sdlc_get_next_action`` — get the next phase action for a task
- ``sdlc_submit_output`` — submit phase output for judge/debate evaluation
- ``sdlc_list_tasks`` — list tasks by status
"""

from __future__ import annotations

from sdlc_mcp.server import SDLCMCPServer

__all__ = ["SDLCMCPServer"]
