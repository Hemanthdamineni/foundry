"""MCP — LLM-free orchestrator exposing TurnEngine as MCP tools.

This server has zero LLM provider imports. The host agent (Claude Code,
OpenCode, Codex, etc.) provides all text generation. Foundry manages state,
transitions, and persistence only.
"""

from __future__ import annotations

from foundry.features.mcp.server import app

__all__ = ["app"]