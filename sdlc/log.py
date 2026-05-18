"""Structured JSON logging for the SDLC server."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "task_id"):
            entry["task_id"] = record.task_id
        if hasattr(record, "phase"):
            entry["phase"] = record.phase
        if hasattr(record, "duration_ms"):
            entry["duration_ms"] = record.duration_ms
        if hasattr(record, "trace_id"):
            entry["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            entry["span_id"] = record.span_id
        if hasattr(record, "parent_span_id"):
            entry["parent_span_id"] = record.parent_span_id
        if hasattr(record, "model"):
            entry["model"] = record.model
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def bootstrap_logging(
    *, level: str = "INFO", json_format: bool = True, path: str | None = None,
) -> logging.Logger:
    """Configure and return the root SDLC logger."""
    root = logging.getLogger("sdlc")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    if json_format:
        handler: logging.Handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)

    if path:
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(JSONFormatter())
        root.addHandler(file_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger of the sdlc hierarchy."""
    return logging.getLogger(f"sdlc.{name}")
