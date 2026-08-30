"""Serve — FastAPI server with LLM-powered auto-orchestration.

Uses TurnEngine + auto_run for phase execution and agent-loop execution.
LLM providers (Ollama, OpenAI) are configured via env vars or YAML.
"""

from __future__ import annotations

from foundry.features.serve.server import app

__all__ = ["app"]