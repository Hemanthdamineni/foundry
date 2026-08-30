"""Unit tests for foundry.core.logging."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from unittest import mock

import pytest

from foundry.core.logging import JsonFormatter, LoggingConfig, bootstrap_logging, get_logger, setup_logging


# ======================================================================
# get_logger
# ======================================================================


class TestGetLogger:
    def test_default_namespace(self) -> None:
        logger = get_logger("my.module")
        assert logger.name == "foundry.my.module"

    def test_custom_namespace(self) -> None:
        logger = get_logger("my.module", namespace="sdlc")
        assert logger.name == "sdlc.my.module"

    def test_root_level(self) -> None:
        logger = get_logger("")
        assert logger.name == "foundry."

    def test_returns_logger_instance(self) -> None:
        logger = get_logger("x")
        assert isinstance(logger, logging.Logger)

    def test_same_logger_cached(self) -> None:
        a = get_logger("cached")
        b = get_logger("cached")
        assert a is b


# ======================================================================
# LoggingConfig
# ======================================================================


class TestLoggingConfig:
    def test_defaults(self) -> None:
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.json_format is True
        assert cfg.path is None
        assert cfg.name == "foundry"
        assert cfg.use_stderr is True

    def test_valid_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = LoggingConfig(level=level)  # type: ignore[arg-type]
            assert cfg.level == level

    def test_lowercase_level_normalized(self) -> None:
        cfg = LoggingConfig(level="debug")  # type: ignore[arg-type]
        assert cfg.level == "DEBUG"

    def test_invalid_level(self) -> None:
        with pytest.raises(ValueError, match="Invalid log level"):
            LoggingConfig(level="TRACE")  # type: ignore[arg-type]


# ======================================================================
# setup_logging
# ======================================================================


class TestSetupLogging:
    def _clean_handler(self) -> None:
        """Ensure tests don't pollute each other across modules."""
        logging.getLogger("foundry").handlers.clear()
        logging.getLogger("sdlc").handlers.clear()

    def test_default_config_creates_stream_handler(self) -> None:
        self._clean_handler()
        logger = setup_logging()
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_overwrites_existing_handlers(self) -> None:
        self._clean_handler()
        logger = logging.getLogger("foundry")
        logger.addHandler(logging.NullHandler())
        before_types = {type(h) for h in logger.handlers}

        logger = setup_logging()
        assert len(logger.handlers) == 1  # cleared and replaced
        after_types = {type(h) for h in logger.handlers}
        # The handler type should have changed (NullHandler -> StreamHandler)
        assert before_types != after_types
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_sets_level(self) -> None:
        self._clean_handler()
        logger = setup_logging(LoggingConfig(level="DEBUG"))  # type: ignore[arg-type]
        assert logger.level == logging.DEBUG

    def test_text_formatter_when_json_false(self) -> None:
        self._clean_handler()
        logger = setup_logging(LoggingConfig(json_format=False))
        fmt = logger.handlers[0].formatter
        assert isinstance(fmt, logging.Formatter)
        assert "%(asctime)s" in fmt._fmt  # type: ignore[attr-defined]

    def test_json_formatter_when_json_true(self) -> None:
        self._clean_handler()
        logger = setup_logging(LoggingConfig(json_format=True))
        assert isinstance(logger.handlers[0].formatter, JsonFormatter)

    def test_none_config_uses_defaults(self) -> None:
        self._clean_handler()
        logger = setup_logging(None)
        assert logger.name == "foundry"
        assert logger.level == logging.INFO

    def test_stdout_via_use_stderr_false(self) -> None:
        self._clean_handler()
        import sys

        logger = setup_logging(LoggingConfig(use_stderr=False))
        assert logger.handlers[0].stream is sys.stdout

    def test_stderr_by_default(self) -> None:
        self._clean_handler()
        import sys

        logger = setup_logging()
        assert logger.handlers[0].stream is sys.stderr

    def test_file_handler_added_when_path_set(self) -> None:
        self._clean_handler()
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            tmp = f.name
        try:
            cfg = LoggingConfig(path=tmp)
            logger = setup_logging(cfg)
            # Stream + file = 2 handlers
            assert len(logger.handlers) == 2

            # Verify file was written
            msg = "file handler test"
            logger.info(msg)
            logger.handlers[1].flush()
            with open(tmp) as fh:
                content = fh.read()
            assert msg in content
        finally:
            os.unlink(tmp)

    def test_file_handler_parent_dir_created(self) -> None:
        self._clean_handler()
        tmpdir = tempfile.mkdtemp()
        nested = os.path.join(tmpdir, "subdir", "test.log")
        try:
            cfg = LoggingConfig(path=nested)
            logger = setup_logging(cfg)
            assert os.path.isdir(os.path.dirname(nested))
            assert len(logger.handlers) == 2
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_file_handler_json_format(self) -> None:
        self._clean_handler()
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            tmp = f.name
        try:
            cfg = LoggingConfig(path=tmp, json_format=True)
            logger = setup_logging(cfg)
            assert isinstance(logger.handlers[1].formatter, JsonFormatter)

            logger.info("json file test")
            logger.handlers[1].flush()
            with open(tmp) as fh:
                content = fh.read()
            parsed = json.loads(content)
            assert parsed["message"] == "json file test"
            assert "timestamp" in parsed
            assert "level" in parsed
        finally:
            os.unlink(tmp)


# ======================================================================
# bootstrap_logging (backward compatibility wrapper)
# ======================================================================


class TestBootstrapLogging:
    def test_defaults(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        logger = bootstrap_logging()
        assert logger.name == "foundry"
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1

    def test_custom_level(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        logger = bootstrap_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_text_format(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        logger = bootstrap_logging(json_format=False)
        assert isinstance(logger.handlers[0].formatter, logging.Formatter)
        assert not isinstance(logger.handlers[0].formatter, JsonFormatter)

    def test_custom_root_name(self) -> None:
        logging.getLogger("sdlc").handlers.clear()
        logger = bootstrap_logging(name="sdlc")
        assert logger.name == "sdlc"

    def test_with_file_path(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            tmp = f.name
        try:
            logger = bootstrap_logging(path=tmp)
            assert len(logger.handlers) == 2
            msg = "bootstrap test"
            logger.info(msg)
            logger.handlers[1].flush()
            with open(tmp) as fh:
                content = fh.read()
            assert msg in content
        finally:
            os.unlink(tmp)


# ======================================================================
# JsonFormatter
# ======================================================================


class TestJsonFormatter:
    _FORMATTER = JsonFormatter()

    def _record(
        self,
        msg: str = "test",
        level: int = logging.INFO,
        name: str = "test.logger",
        exc_info: tuple | None = None,
        extra: dict | None = None,
    ) -> logging.LogRecord:
        record = logging.LogRecord(name, level, "", 0, msg, None, exc_info)
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def _parse(self, record: logging.LogRecord) -> dict:
        return json.loads(self._FORMATTER.format(record))

    def test_basic_fields(self) -> None:
        parsed = self._parse(self._record("hello"))
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_timestamp_iso_format(self) -> None:
        parsed = self._parse(self._record())
        from datetime import datetime

        # Should parse as ISO8601
        datetime.fromisoformat(parsed["timestamp"])

    def test_level_name(self) -> None:
        parsed = self._parse(self._record(level=logging.WARNING))
        assert parsed["level"] == "WARNING"

        parsed = self._parse(self._record(level=logging.ERROR))
        assert parsed["level"] == "ERROR"

    def test_known_extra_fields_inline(self) -> None:
        parsed = self._parse(
            self._record(
                msg="task update",
                extra={
                    "task_id": "tid-001",
                    "phase": "review",
                    "duration_ms": 1234,
                    "trace_id": "trace-abc",
                    "span_id": "span-1",
                    "parent_span_id": "span-0",
                    "model": "gpt-4",
                },
            )
        )
        assert parsed["task_id"] == "tid-001"
        assert parsed["phase"] == "review"
        assert parsed["duration_ms"] == 1234
        assert parsed["trace_id"] == "trace-abc"
        assert parsed["span_id"] == "span-1"
        assert parsed["parent_span_id"] == "span-0"
        assert parsed["model"] == "gpt-4"

    def test_unknown_extra_in_extra_dict(self) -> None:
        parsed = self._parse(
            self._record(msg="custom", extra={"user_id": 42, "env": "prod"})
        )
        assert parsed["extra"]["user_id"] == 42
        assert parsed["extra"]["env"] == "prod"

    def test_known_and_unknown_extras(self) -> None:
        parsed = self._parse(
            self._record(
                msg="mixed",
                extra={
                    "task_id": "tid-002",
                    "custom_field": "hello",
                    "count": 99,
                },
            )
        )
        # Known goes top-level
        assert parsed["task_id"] == "tid-002"
        # Unknown goes under "extra"
        assert parsed["extra"]["custom_field"] == "hello"
        assert parsed["extra"]["count"] == 99
        # Standard attrs are NOT in extra
        assert "name" not in parsed.get("extra", {})
        assert "msg" not in parsed.get("extra", {})
        assert "levelname" not in parsed.get("extra", {})

    def test_no_extra_when_no_custom_attrs(self) -> None:
        parsed = self._parse(self._record("plain"))
        assert "extra" not in parsed

    def test_exception_info(self) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = self._record("failed", level=logging.ERROR, exc_info=sys.exc_info())  # type: ignore[arg-type]
        parsed = self._parse(record)
        assert "exception" in parsed
        assert "RuntimeError" in parsed["exception"]
        assert "boom" in parsed["exception"]

    def test_no_exception_in_output_when_no_exc_info(self) -> None:
        parsed = self._parse(self._record("no problem"))
        assert "exception" not in parsed

    def test_sort_keys_false_preserves_insertion_order(self) -> None:
        parsed = self._parse(self._record("order"))
        keys = list(parsed.keys())
        assert keys[0] == "timestamp"
        assert keys[1] == "level"
        assert keys[2] == "logger"
        assert keys[3] == "message"

    def test_non_string_default_repr(self) -> None:
        """Values that aren't JSON-serializable should use str()."""
        record = self._record("unserializable")
        record.bad_attr = object()  # type: ignore[assignment]
        parsed = self._parse(record)
        # object().__str__ is something like <object object at 0x...>
        assert parsed["extra"]["bad_attr"].startswith("<")

    def test_logger_with_custom_name(self) -> None:
        parsed = self._parse(self._record(name="foundry.engine.debate"))
        assert parsed["logger"] == "foundry.engine.debate"


# ======================================================================
# Integration: get_logger + setup_logging round-trip
# ======================================================================


class TestIntegration:
    def test_get_logger_after_setup(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        setup_logging(LoggingConfig(json_format=True))
        child = get_logger("integration.test")
        assert child.name == "foundry.integration.test"
        # Child level is NOTSET (0), meaning it inherits from parent at call time
        assert child.level == logging.NOTSET

    def test_logger_propagates_to_root(self) -> None:
        logging.getLogger("foundry").handlers.clear()
        logger = setup_logging(LoggingConfig(json_format=True))

        # Capture what the root handler emits
        root_handler = logger.handlers[0]
        with mock.patch.object(root_handler, "emit") as mock_emit:
            child = get_logger("propagation")
            child.info("should propagate")
            # The root handler's emit should have been called via propagation
            assert mock_emit.call_count >= 1


