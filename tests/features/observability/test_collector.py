"""Tests for the EventCollector — observability data aggregation.

Uses a real in-memory SQLite store to verify polling works end-to-end.
Optional dependencies (event_bus, approval_gate) are tested via mock
patches rather than requiring those modules to be installed.
"""

from __future__ import annotations

import sys
import types as _types
import sqlite3
from unittest.mock import MagicMock, PropertyMock

import pytest

from foundry.core.guardrails import BudgetTracker, GuardrailConfig
from foundry.core.store.ensure_initialized import StoreBackend
from foundry.features.observability.collectors.event_collector import EventCollector


# ======================================================================
# Helper: mock a dotted module path in sys.modules
# ======================================================================

# Tracks mock module keys added by _install_mock_module so teardown
# can remove them from sys.modules without affecting other tests.
_mock_module_keys: set[str] = set()


def _install_mock_module(dotted_path: str) -> MagicMock:
    """Install a hierarchy of mock packages for *dotted_path*.

    Parent packages are real ``types.ModuleType`` instances so Python's
    import machinery can traverse attributes correctly.  The leaf module
    is a ``MagicMock`` so test code can set arbitrary attributes on it.

    All added keys are tracked and cleaned up by ``_cleanup_mock_modules``.
    """
    parts = dotted_path.split(".")
    prev_module: _types.ModuleType | MagicMock | None = None
    leaf: MagicMock | None = None

    for i, part in enumerate(parts):
        key = ".".join(parts[: i + 1])
        _mock_module_keys.add(key)
        if key not in sys.modules:
            if i == len(parts) - 1:
                # Leaf: allow arbitrary attribute assignment
                m: MagicMock = MagicMock()
                leaf = m
            else:
                # Parent: real module so attribute traversal works
                m = _types.ModuleType(part)
                m.__path__ = []  # type: ignore[attr-defined]
                m.__package__ = key  # type: ignore[attr-defined]
            sys.modules[key] = m
            if prev_module is not None:
                setattr(prev_module, part, m)
        else:
            pass  # already installed by an earlier test
        prev_module = sys.modules[key]

    assert leaf is not None, f"empty dotted_path: {dotted_path!r}"
    return leaf


@pytest.fixture(autouse=True)
def _cleanup_mock_modules() -> None:
    """Remove mock module entries from ``sys.modules`` after each test."""
    yield
    for key in list(_mock_module_keys):
        sys.modules.pop(key, None)
    _mock_module_keys.clear()


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def memory_store() -> StoreBackend:
    """Return a StoreBackend backed by :memory: SQLite."""
    store = StoreBackend(":memory:")
    store._conn = sqlite3.connect(":memory:", timeout=5.0, check_same_thread=False)
    store._conn.row_factory = sqlite3.Row
    store._conn.execute("PRAGMA journal_mode=WAL")
    store._conn.execute("PRAGMA busy_timeout=5000")
    store._create_tables()
    return store


@pytest.fixture
def collector(memory_store: StoreBackend) -> EventCollector:
    """EventCollector wired to the in-memory store."""
    cfg = GuardrailConfig(max_tokens=1000, max_steps=5, max_cost=10.0)
    tracker = BudgetTracker(config=cfg, store=memory_store)
    return EventCollector(store=memory_store, budget_tracker=tracker)


@pytest.fixture
def seeded_store(memory_store: StoreBackend) -> StoreBackend:
    """Store pre-populated with test data."""
    conn = memory_store.conn

    conn.execute(
        "INSERT INTO tasks (task_id, data, created_at, updated_at) VALUES "
        "('t1', '{\"description\": \"Task one\", \"status\": \"done\"}', '2026-07-17T10:00:00', '2026-07-17T11:00:00'),"
        "('t2', '{\"description\": \"Task two\", \"status\": \"active\"}', '2026-07-17T10:30:00', '2026-07-17T11:30:00')"
    )
    conn.execute(
        "INSERT INTO phase_history (task_id, phase, output, created_at) VALUES "
        "('t1', 'Chatting', 'initial spec', '2026-07-17T10:05:00'),"
        "('t1', 'Planning', 'design doc', '2026-07-17T10:30:00'),"
        "('t2', 'Chatting', 'requirements', '2026-07-17T10:35:00')"
    )
    conn.execute(
        "INSERT INTO checkpoints (task_id, data, created_at) VALUES "
        "('t1', '{\"phase\":\"Planning\",\"iteration\":2}', '2026-07-17T10:30:00')"
    )
    conn.execute(
        "INSERT INTO traces (id, task_id, phase, action, status, verdict, created_at) VALUES "
        "('tr1', 't1', 'Chatting', 'dispatch', 'ok', 'passed', '2026-07-17T10:05:00')"
    )
    conn.execute(
        "INSERT INTO debate_logs (id, task_id, round_num, agent_role, content, verdict, created_at) VALUES "
        "('dl1', 't1', 1, 'specs', 'approve', 'passed', '2026-07-17T10:06:00')"
    )
    conn.commit()
    return memory_store


@pytest.fixture
def seeded_collector(seeded_store: StoreBackend) -> EventCollector:
    """Collector wired to the seeded store."""
    cfg = GuardrailConfig(max_tokens=1000, max_steps=5, max_cost=10.0)
    tracker = BudgetTracker(config=cfg, store=seeded_store)
    return EventCollector(store=seeded_store, budget_tracker=tracker)


# ======================================================================
# Tests — store-backed polls
# ======================================================================


class TestPollTransitions:
    def test_empty_when_no_store(self) -> None:
        c = EventCollector(store=None)
        assert c.poll_transitions() == []

    def test_returns_ordered_rows(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_transitions(limit=10)
        assert len(rows) >= 3
        assert rows[0]["phase"] is not None

    def test_respects_limit(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_transitions(limit=1)
        assert len(rows) == 1

    def test_handles_store_error(self, memory_store: StoreBackend) -> None:
        memory_store._conn.close()
        c = EventCollector(store=memory_store)
        assert c.poll_transitions() == []


class TestPollCheckpoints:
    def test_empty_when_no_store(self) -> None:
        assert EventCollector(store=None).poll_checkpoints() == []

    def test_returns_checkpoints(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_checkpoints()
        assert len(rows) == 1
        assert rows[0]["task_id"] == "t1"

    def test_respects_limit(self, seeded_collector: EventCollector) -> None:
        assert len(seeded_collector.poll_checkpoints(limit=0)) == 0


class TestPollTasks:
    def test_empty_when_no_store(self) -> None:
        assert EventCollector(store=None).poll_tasks() == []

    def test_returns_tasks(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_tasks()
        assert len(rows) == 2
        ids = {r["task_id"] for r in rows}
        assert ids == {"t1", "t2"}


class TestPollTraces:
    def test_empty_when_no_store(self) -> None:
        assert EventCollector(store=None).poll_traces() == []

    def test_returns_traces(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_traces()
        assert len(rows) == 1
        assert rows[0]["id"] == "tr1"


class TestPollDebateLogs:
    def test_empty_when_no_store(self) -> None:
        assert EventCollector(store=None).poll_debate_logs() == []

    def test_returns_debate_logs(self, seeded_collector: EventCollector) -> None:
        rows = seeded_collector.poll_debate_logs()
        assert len(rows) == 1
        assert rows[0]["agent_role"] == "specs"


# ======================================================================
# Tests — guardrails polling
# ======================================================================


class TestPollGuardrails:
    def test_unconfigured(self) -> None:
        result = EventCollector(store=None, budget_tracker=None).poll_guardrails()
        assert result["configured"] is False

    def test_returns_budget_state(self, collector: EventCollector) -> None:
        result = collector.poll_guardrails()
        assert result["configured"] is True
        assert result["tokens_used"] == 0
        assert result["budget_exhausted"] is False
        assert result["limits"]["max_tokens"] == 1000
        assert result["limits"]["max_steps"] == 5
        assert result["limits"]["max_cost"] == 10.0

    def test_reflects_usage(self, collector: EventCollector) -> None:
        collector._budget_tracker.record_dispatch(actual_cost=200, monetary_cost=1.0)
        result = collector.poll_guardrails()
        assert result["tokens_used"] == 200
        assert result["steps_used"] == 1
        assert result["cost_incurred"] == 1.0

    def test_budget_exhausted(self, collector: EventCollector) -> None:
        collector._budget_tracker.record_dispatch(actual_cost=1100)
        result = collector.poll_guardrails()
        assert result["budget_exhausted"] is True

    def test_handles_tracker_error(self) -> None:
        bad = MagicMock(spec=BudgetTracker)
        type(bad).config = PropertyMock(side_effect=RuntimeError("boom"))
        c = EventCollector(budget_tracker=bad)
        result = c.poll_guardrails()
        assert result["configured"] is True
        assert "error" in result


# ======================================================================
# Tests — event-bus polling (external dependency, mocked)
# ======================================================================


class TestPollEventBus:
    def test_no_event_bus_module(self) -> None:
        c = EventCollector()
        assert c.poll_event_bus() == []

    def test_with_scheduler_no_scheduled_tasks(self) -> None:
        """Mock the full import path so the try/except ImportError succeeds."""
        _install_mock_module("projects.ai_agent_server.src.event_bus")
        import projects.ai_agent_server.src.event_bus  # type: ignore[import-untyped]  # noqa: PLC0415

        projects.ai_agent_server.src.event_bus._task_scheduler = MagicMock()
        projects.ai_agent_server.src.event_bus._task_scheduler.scheduled_tasks = []
        c = EventCollector()
        assert c.poll_event_bus() == []

    def test_with_scheduled_tasks(self) -> None:
        _install_mock_module("projects.ai_agent_server.src.event_bus")
        import projects.ai_agent_server.src.event_bus  # type: ignore[import-untyped]  # noqa: PLC0415

        task_mock = MagicMock()
        task_mock.name = "test-task"
        task_mock.next_run = "2026-07-17T12:00:00"
        task_mock.trigger_counter = 3
        task_mock.trigger_type = "event"

        projects.ai_agent_server.src.event_bus._task_scheduler = MagicMock()
        projects.ai_agent_server.src.event_bus._task_scheduler.scheduled_tasks = [task_mock]
        c = EventCollector()
        events = c.poll_event_bus()
        assert len(events) == 1
        assert events[0]["task_name"] == "test-task"


# ======================================================================
# Tests — approval-gate polling (external dependency, mocked)
# ======================================================================


class TestPollApprovals:
    def test_no_approval_module(self) -> None:
        c = EventCollector()
        assert c.poll_approvals() == []

    def test_pending_present(self) -> None:
        _install_mock_module("hermes_cli.tools.approval")
        import hermes_cli.tools.approval  # type: ignore[import-untyped]  # noqa: PLC0415

        hermes_cli.tools.approval._pending = {
            "sess_1": {
                "command": "rm -rf /tmp/x",
                "description": "delete tmp",
                "pattern_key": "recursive_delete",
            }
        }
        hermes_cli.tools.approval._gateway_queues = {}
        c = EventCollector()
        pending = c.poll_approvals()
        assert len(pending) == 1
        assert pending[0]["session_key"] == "sess_1"
        assert pending[0]["status"] == "pending"
