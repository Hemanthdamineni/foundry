from __future__ import annotations

from sdlc import FailureType, SDLCError, Task
from sdlc.config import Settings
from sdlc.exceptions import ConfigError, StoreError
from sdlc.log import bootstrap_logging, get_logger
from sdlc.models import (
    BudgetPolicy,
    Checkpoint,
    Decision,
    DecisionAction,
    ExecutionSnapshot,
    PhaseRecord,
    PhaseStatus,
    TaskStatus,
    WriteOp,
)


class TestModels:
    def test_task_defaults(self) -> None:
        task = Task(task_id="t1", description="test task")
        assert task.task_id == "t1"
        assert task.status == TaskStatus.ACTIVE
        assert task.current_phase == "Chatting"
        assert task.iteration_count == 0
        assert task.retry_count == 0
        assert task.last_failure_reason is None
        assert task.last_failure_type is None
        assert task.history == []

    def test_task_with_budget(self) -> None:
        budget = BudgetPolicy(max_total_tokens=50_000, max_review_cycles=4)
        task = Task(task_id="t2", description="bugfix", budget=budget)
        assert task.budget.max_total_tokens == 50_000
        assert task.budget.max_review_cycles == 4

    def test_task_retry_metadata_defaults(self) -> None:
        task = Task(task_id="t3", description="retry test")
        assert task.retry_count == 0
        assert task.last_failure_reason is None
        assert task.last_failure_type is None

    def test_task_retry_metadata_roundtrip(self) -> None:
        task = Task(
            task_id="t4",
            description="retry test",
            retry_count=3,
            last_failure_reason="lint failed",
            last_failure_type="permanent",
        )
        data = task.model_dump(mode="json")
        restored = Task(**data)
        assert restored.retry_count == 3
        assert restored.last_failure_reason == "lint failed"
        assert restored.last_failure_type == "permanent"

    def test_phase_record_defaults(self) -> None:
        rec = PhaseRecord(phase="Coding")
        assert rec.phase == "Coding"
        assert rec.status == PhaseStatus.PENDING
        assert rec.output is None
        assert rec.iteration_count == 0

    def test_phase_record_with_output(self) -> None:
        rec = PhaseRecord(phase="Specs", output="## Requirements\n- item 1", model_used="qwen3:4b")
        assert rec.status == PhaseStatus.PENDING
        assert rec.output is not None

    def test_checkpoint_roundtrip(self) -> None:
        cp = Checkpoint(task_id="t1", phase="Coding", history=[], iteration_count=2)
        assert cp.task_id == "t1"
        assert cp.phase == "Coding"
        assert cp.iteration_count == 2

    def test_execution_snapshot(self) -> None:
        snap = ExecutionSnapshot(
            snapshot_id="snap1",
            created_at=__import__("datetime").datetime.now(),
            graph_template="feature",
            graph_hash="abc123",
            prompt_hashes={"code.txt": "def456"},
            model_routing_hash="ghi789",
        )
        assert snap.graph_template == "feature"
        assert snap.prompt_hashes["code.txt"] == "def456"

    def test_decision_proceed(self) -> None:
        d = Decision(action=DecisionAction.PROCEED, reason="budget OK")
        assert d.action == DecisionAction.PROCEED
        assert d.retry_after_s is None

    def test_decision_abort(self) -> None:
        d = Decision(
            action=DecisionAction.ABORT,
            reason="budget exhausted",
            failure_type="limit_reached",  # type: ignore[arg-type]
        )
        assert d.action == DecisionAction.ABORT
        assert d.failure_type == "limit_reached"

    def test_write_op(self) -> None:
        op = WriteOp(
            target="task", action="create", payload={"task_id": "t1"}, source_span="span_0x1"
        )
        assert op.target == "task"
        assert op.action == "create"

    def test_failure_type_enum(self) -> None:
        assert FailureType.TERMINAL_VALIDATION == "validation_failed"
        assert FailureType.RETRYABLE_MODEL == "model_timeout"

    def test_task_status_enum(self) -> None:
        assert TaskStatus.ACTIVE == "active"
        assert TaskStatus.DONE == "done"

    def test_phase_status_enum(self) -> None:
        assert PhaseStatus.ACCEPTED == "accepted"
        assert PhaseStatus.REJECTED == "rejected"


class TestExceptions:
    def test_sdlc_error_base(self) -> None:
        err = SDLCError("something broke", failure_type="infra_transient")
        assert str(err) == "something broke"
        assert err.failure_type == "infra_transient"

    def test_config_error(self) -> None:
        err = ConfigError("config not found")
        assert isinstance(err, SDLCError)

    def test_store_error(self) -> None:
        err = StoreError("db locked")
        assert isinstance(err, SDLCError)

    def test_exception_inheritance(self) -> None:
        from sdlc.exceptions import (
            CheckpointError,
            DebateError,
            JudgeError,
            ModelError,
            PhaseError,
            PolicyError,
            SandboxError,
            ToolError,
        )

        assert issubclass(CheckpointError, SDLCError)
        assert issubclass(DebateError, SDLCError)
        assert issubclass(JudgeError, SDLCError)
        assert issubclass(ModelError, SDLCError)
        assert issubclass(PhaseError, SDLCError)
        assert issubclass(PolicyError, SDLCError)
        assert issubclass(SandboxError, SDLCError)
        assert issubclass(ToolError, SDLCError)


class TestLogging:
    def test_bootstrap_logging(self) -> None:
        logger = bootstrap_logging(level="DEBUG", json_format=False)
        assert logger.name == "sdlc"
        assert logger.level == 10  # DEBUG

    def test_get_logger(self) -> None:
        logger = get_logger("test")
        assert logger.name == "sdlc.test"

    def test_bootstrap_with_path(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        bootstrap_logging(level="INFO", json_format=True, path=str(log_file))
        logger = get_logger("file_test")
        logger.info("hello world")
        assert log_file.exists()


class TestConfig:
    def test_settings_defaults(self) -> None:
        settings = Settings()
        assert settings.max_iterations == 8
        assert settings.llm.default_provider == "ollama"
        assert settings.llm.default_model == "qwen3:8b"
        assert settings.store.busy_timeout_ms == 5000

    def test_settings_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("SDLC_MAX_ITERATIONS", "5")
        monkeypatch.setenv("SDLC_LLM__DEFAULT_MODEL", "deepseek-v4")
        settings = Settings()
        assert settings.max_iterations == 5
        assert settings.llm.default_model == "deepseek-v4"

    def test_settings_debug_flag(self, monkeypatch) -> None:
        monkeypatch.setenv("SDLC_DEBUG", "true")
        settings = Settings()
        assert settings.debug is True

    def test_ensure_dirs(self, tmp_path) -> None:
        settings = Settings(db_path=str(tmp_path / "db" / "test.db"))
        settings.ensure_dirs()
        assert (tmp_path / "db").exists()
