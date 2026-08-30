"""Custom log formatters, primarily JSON."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Standard extra fields captured by JsonFormatter when present on a LogRecord.
EXTRA_FIELDS = frozenset({
    "task_id",
    "phase",
    "duration_ms",
    "trace_id",
    "span_id",
    "parent_span_id",
    "model",
})

# Standard attributes that every LogRecord carries — never emit them as
# ad-hoc "extra" keys since they are already in the top-level entry or
# are internal plumbing.
_STD_RECORD_ATTRS: frozenset[str] = frozenset({
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
    "message",
})


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Picks up a fixed set of *extra* kwargs (``task_id``, ``phase``,
    ``duration_ms``, ``trace_id``, ``span_id``, ``parent_span_id``,
    ``model``) when the caller passes them via ``logger.info(..., extra=...)``.

    Any *extra* key that is not in the predefined set is still included
    in the output under the ``"extra"`` sub-dictionary.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Sprinkle well-known extra fields directly into the top-level dict.
        for field in EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Collect caller-provided extras that are not standard record attrs
        # and not already surfaced in the top-level entry.
        top_level = {"timestamp", "level", "logger", "message"} | EXTRA_FIELDS
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STD_RECORD_ATTRS
            and k not in top_level
            and not k.startswith("_")
        }
        if extras:
            entry["extra"] = extras

        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str, sort_keys=False)
