from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace() -> AsyncIterator[Path]:
    """Create a temporary workspace with standard subdirectories."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "data").mkdir()
        (root / "graphs").mkdir()
        (root / "config").mkdir()
        (root / ".opencode").mkdir()
        yield root


@pytest.fixture
def sample_phase_graph() -> dict:
    return {
        "phases": ["Chatting", "Specs", "Planning", "Coding", "Review", "Testing", "Done"],
        "transitions": [
            {"from": "Chatting", "to": "Specs"},
            {"from": "Specs", "to": "Planning"},
            {"from": "Planning", "to": "Coding"},
            {"from": "Coding", "to": "Review"},
            {"from": "Review", "to": "Coding"},
            {"from": "Review", "to": "Testing"},
            {"from": "Testing", "to": "Done"},
        ],
    }


@pytest.fixture
def sample_model_routing() -> dict:
    return {
        "phases": {
            "Specs": {"model": "qwen3:4b", "edit": "deny", "bash": "deny"},
            "Planning": {"model": "qwen3:4b", "edit": "deny", "bash": "deny"},
            "Coding": {"model": "qwen2.5-coder:3b", "edit": "allow", "bash": "allow"},
            "Review": {"model": "qwen2.5-coder:7b", "edit": "deny", "bash": "deny"},
            "Testing": {"model": "qwen3:4b", "edit": "allow", "bash": "allow"},
        },
    }


@pytest.fixture
def sample_budget_policy() -> dict:
    return {
        "feature": {
            "max_total_tokens": 100_000,
            "max_review_cycles": 8,
            "max_debate_rounds": 3,
            "max_runtime_minutes": 60,
        },
        "bugfix": {
            "max_total_tokens": 50_000,
            "max_review_cycles": 4,
            "max_debate_rounds": 0,
            "max_runtime_minutes": 30,
        },
    }


@pytest.fixture
def mock_store_backend():
    """In-memory mock for StoreBackend (Phase 1 will define the ABC)."""

    class MockStore:
        def __init__(self) -> None:
            self.tasks: dict[str, dict] = {}
            self.checkpoints: dict[str, dict] = {}

        async def create_task(self, task: dict) -> dict:
            self.tasks[task["task_id"]] = task
            return task

        async def get_task(self, task_id: str) -> dict | None:
            return self.tasks.get(task_id)

        async def save_phase_output(self, task_id: str, phase: str, output: str) -> None:
            if task_id in self.tasks:
                if "history" not in self.tasks[task_id]:
                    self.tasks[task_id]["history"] = []
                self.tasks[task_id]["history"].append({"phase": phase, "output": output})

        async def save_checkpoint(self, task_id: str, checkpoint: dict) -> None:
            self.checkpoints[task_id] = checkpoint

        async def restore_checkpoint(self, task_id: str) -> dict | None:
            return self.checkpoints.get(task_id)

        async def close(self) -> None:
            pass

    return MockStore()


@pytest.fixture
def mock_settings_env(monkeypatch):
    monkeypatch.setenv("SDLC_DB_PATH", ":memory:")
    monkeypatch.setenv("SDLC_LOG_PATH", "/dev/null")
    monkeypatch.setenv("SDLC_DEBUG", "true")
