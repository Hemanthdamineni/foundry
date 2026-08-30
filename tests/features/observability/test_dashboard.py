"""Integration tests for the dashboard FastAPI app.

These tests create a real FastAPI test client wired to an in-memory store
so endpoints can be exercised end-to-end.

Note: the SQLite connection uses ``check_same_thread=False`` because
``TestClient`` runs requests in a separate httpx worker thread.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from foundry.core.guardrails import BudgetTracker, GuardrailConfig
from foundry.core.store.ensure_initialized import StoreBackend
from foundry.features.observability.dashboard.app import create_app


# ======================================================================
# Fixtures
# ======================================================================


def _make_memory_store() -> StoreBackend:
    """Build an in-memory StoreBackend with ``check_same_thread=False``."""
    store = StoreBackend(":memory:")
    store._conn = sqlite3.connect(":memory:", timeout=5.0, check_same_thread=False)
    store._conn.row_factory = sqlite3.Row
    store._conn.execute("PRAGMA journal_mode=WAL")
    store._conn.execute("PRAGMA busy_timeout=5000")
    store._create_tables()
    return store


@pytest.fixture
def memory_store() -> StoreBackend:
    return _make_memory_store()


@pytest.fixture
def client(memory_store: StoreBackend) -> TestClient:
    cfg = GuardrailConfig(max_tokens=10_000, max_steps=20, max_cost=5.0)
    tracker = BudgetTracker(config=cfg, store=memory_store)
    tracker.record_dispatch(actual_cost=500, monetary_cost=0.5)
    app = create_app(store=memory_store, budget_tracker=tracker)
    return TestClient(app)


@pytest.fixture
def seeded_store() -> StoreBackend:
    store = _make_memory_store()
    conn = store.conn
    conn.execute(
        "INSERT INTO tasks (task_id, data, created_at, updated_at) VALUES "
        "('t1', '{\"description\": \"Feature X\"}', '2026-07-17T10:00:00', '2026-07-17T11:00:00')"
    )
    conn.execute(
        "INSERT INTO phase_history (task_id, phase, output, created_at) VALUES "
        "('t1', 'Chatting', 'spec', '2026-07-17T10:05:00'),"
        "('t1', 'Planning', 'design', '2026-07-17T10:30:00')"
    )
    conn.execute(
        "INSERT INTO debate_logs (id, task_id, round_num, agent_role, content, verdict, created_at) VALUES "
        "('dl1', 't1', 1, 'coding', 'looks good', 'passed', '2026-07-17T10:06:00')"
    )
    conn.execute(
        "INSERT INTO checkpoints (task_id, data, created_at) VALUES "
        "('t1', '{\"phase\":\"Planning\"}', '2026-07-17T10:30:00')"
    )
    conn.commit()
    return store


@pytest.fixture
def seeded_client(seeded_store: StoreBackend) -> TestClient:
    cfg = GuardrailConfig(max_tokens=10_000, max_steps=20, max_cost=5.0)
    tracker = BudgetTracker(config=cfg, store=seeded_store)
    app = create_app(store=seeded_store, budget_tracker=tracker)
    return TestClient(app)


# ======================================================================
# Tests — HTML index
# ======================================================================


class TestDashboardIndex:
    def test_returns_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Foundry Dashboard" in resp.text

    def test_title_customizable(self, memory_store: StoreBackend) -> None:
        app = create_app(store=memory_store, title="My Dashboard")
        tc = TestClient(app)
        resp = tc.get("/")
        assert "My Dashboard" in resp.text


# ======================================================================
# Tests — API endpoints
# ======================================================================


class TestAPITransitions:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/transitions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] == 0
        assert data["transitions"] == []

    def test_with_data(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/transitions")
        data = resp.json()
        assert data["count"] == 2

    def test_limit_param(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/transitions?limit=1")
        data = resp.json()
        assert data["count"] == 1


class TestAPIDebates:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/debates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["debate_log_count"] == 0

    def test_with_data(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/debates")
        data = resp.json()
        assert data["debate_log_count"] == 1
        assert data["debate_logs"][0]["agent_role"] == "coding"


class TestAPIApprovals:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0


class TestAPIGuardrails:
    def test_returns_budget(self, client: TestClient) -> None:
        resp = client.get("/api/guardrails")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        g = data["guardrails"]
        assert g["configured"] is True
        assert g["tokens_used"] == 500
        assert g["steps_used"] == 1
        assert g["cost_incurred"] == 0.5
        assert g["budget_exhausted"] is False

    def test_without_tracker(self, memory_store: StoreBackend) -> None:
        app = create_app(store=memory_store, budget_tracker=None)
        tc = TestClient(app)
        resp = tc.get("/api/guardrails")
        data = resp.json()
        assert data["guardrails"]["configured"] is False


class TestAPICheckpoints:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_with_data(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/checkpoints")
        data = resp.json()
        assert data["count"] == 1
        assert data["checkpoints"][0]["task_id"] == "t1"


class TestAPITasks:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_with_data(self, seeded_client: TestClient) -> None:
        resp = seeded_client.get("/api/tasks")
        data = resp.json()
        assert data["count"] == 1
