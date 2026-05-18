"""Tracer — lightweight distributed tracing via JSONL files.

Propagates trace_id and span_id across tool calls, persists spans
as newline-delimited JSON, and provides retention enforcement.
"""

from __future__ import annotations

import contextlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdlc.log import get_logger

log = get_logger("tracing")

TRACE_DIR = "data/traces"
ERROR_DIR = "data/traces/errors"
SUMMARY_PATH = "data/traces/summaries.jsonl"

_RETENTION_SUCCESS_DAYS = 7
_RETENTION_RAW_SPAN_DAYS = 30


def _generate_id() -> str:
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TraceSpan:
    """A single span in a distributed trace."""

    def __init__(  # noqa: PLR0913
        self,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None = None,
        *,
        phase: str | None = None,
        tool: str | None = None,
        message: str | None = None,
        level: str = "info",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.phase = phase
        self.tool = tool
        self.message = message or ""
        self.level = level
        self.task_id = task_id
        self.metadata = metadata or {}
        self.timestamp = _now_iso()
        self.duration_ms: int | None = None
        self.error: str | None = None
        self._start_time: float | None = None

    def start(self) -> None:
        self._start_time = time.monotonic()

    def stop(self) -> None:
        if self._start_time is not None:
            self.duration_ms = int((time.monotonic() - self._start_time) * 1000)

    def set_error(self, error: str) -> None:
        self.error = error
        self.level = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "phase": self.phase,
            "tool": self.tool,
            "message": self.message,
            "level": self.level,
            "task_id": self.task_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class Tracer:
    """Creates, stores, and manages traces.

    Usage:
        tracer = Tracer(trace_dir="data/traces")
        span = tracer.start_span(trace_id="abc", phase="Coding", tool="submit_output")
        ... do work ...
        span.stop()
        await tracer.write_span(span)
    """

    def __init__(self, trace_dir: str | Path = TRACE_DIR) -> None:
        self._trace_dir = Path(trace_dir)
        self._error_dir = self._trace_dir / "errors"
        self._summary_path = self._trace_dir / "summaries.jsonl"
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._error_dir.mkdir(parents=True, exist_ok=True)

    def create_trace_id(self) -> str:
        return _generate_id()

    @property
    def summary_path(self) -> Path:
        return self._summary_path

    def start_span(  # noqa: PLR0913
        self,
        trace_id: str,
        *,
        parent_span_id: str | None = None,
        phase: str | None = None,
        tool: str | None = None,
        message: str | None = None,
        level: str = "info",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            trace_id=trace_id,
            span_id=_generate_id(),
            parent_span_id=parent_span_id,
            phase=phase,
            tool=tool,
            message=message,
            level=level,
            task_id=task_id,
            metadata=metadata,
        )
        span.start()
        return span

    async def write_span(self, span: TraceSpan) -> None:
        span.stop()
        line = json.dumps(span.to_dict(), default=str)
        trace_path = self._trace_dir / f"{span.trace_id}.jsonl"
        try:
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            log.warning("Failed to write trace span", extra={"error": str(exc)})

    async def record_span(  # noqa: PLR0913
        self,
        trace_id: str,
        *,
        parent_span_id: str | None = None,
        phase: str | None = None,
        tool: str | None = None,
        message: str | None = None,
        level: str = "info",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        span = self.start_span(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            phase=phase,
            tool=tool,
            message=message,
            level=level,
            task_id=task_id,
            metadata=metadata,
        )
        await self.write_span(span)
        return span

    def get_trace_path(self, trace_id: str) -> Path:
        return self._trace_dir / f"{trace_id}.jsonl"

    def trace_exists(self, trace_id: str) -> bool:
        return self.get_trace_path(trace_id).exists()

    def read_trace(self, trace_id: str) -> list[dict[str, Any]]:
        path = self.get_trace_path(trace_id)
        if not path.exists():
            return []
        spans: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    spans.append(json.loads(line))
        return spans

    def list_trace_ids(self) -> list[str]:
        return sorted(
            p.stem for p in self._trace_dir.glob("*.jsonl")
            if p.stem != "summaries"
        )

    async def write_summary(
        self,
        trace_id: str,
        task_id: str,
        phases: list[str],
        duration_s: float,
        token_estimate: int = 0,
    ) -> None:
        summary = {
            "trace_id": trace_id,
            "task_id": task_id,
            "phases": phases,
            "duration_s": round(duration_s, 1),
            "token_estimate": token_estimate,
            "timestamp": _now_iso(),
        }
        try:
            with self._summary_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(summary, default=str) + "\n")
        except OSError as exc:
            log.warning("Failed to write trace summary", extra={"error": str(exc)})

    def enforce_retention(self) -> dict[str, int]:  # noqa: C901
        """Enforce the trace retention policy.

        Returns a dict with counts of actions taken.
        """
        now = datetime.now(UTC)
        kept_errors = 0
        deleted_success = 0
        deleted_raw = 0

        for trace_path in self._trace_dir.glob("*.jsonl"):
            if trace_path.stem == "summaries":
                continue

            mtime = datetime.fromtimestamp(trace_path.stat().st_mtime, tz=UTC)
            age_days = (now - mtime).days

            is_error = False
            with trace_path.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    with contextlib.suppress(json.JSONDecodeError):
                        first_span = json.loads(first_line)
                        if first_span.get("level") == "error":
                            is_error = True

            if is_error:
                error_path = self._error_dir / trace_path.name
                if not error_path.exists():
                    with contextlib.suppress(OSError):
                        trace_path.rename(error_path)
                kept_errors += 1
                continue

            if age_days > _RETENTION_SUCCESS_DAYS:
                try:
                    trace_path.unlink()
                    deleted_success += 1
                except OSError:
                    pass
            elif age_days > _RETENTION_RAW_SPAN_DAYS:
                try:
                    trace_path.unlink()
                    deleted_raw += 1
                except OSError:
                    pass

        return {
            "errors_kept": kept_errors,
            "successful_deleted": deleted_success,
            "raw_spans_deleted": deleted_raw,
        }
