"""Debug and introspection MCP tools for observability."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sdlc.runtime.tracing import Tracer


async def get_trace(
    tracer: Tracer,
    trace_id: str,
) -> dict[str, Any]:
    """Retrieve all spans for a given trace_id."""
    spans = tracer.read_trace(trace_id)
    if not spans:
        return {"error": f"Trace not found: {trace_id}", "trace_id": trace_id}
    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "spans": spans,
    }


async def list_traces(
    tracer: Tracer,
    task_id: str | None = None,
) -> dict[str, Any]:
    """List all available trace IDs, optionally filtered by task."""
    ids = tracer.list_trace_ids()
    if task_id:
        matching = []
        for tid in ids:
            spans = tracer.read_trace(tid)
            if any(s.get("task_id") == task_id for s in spans):
                matching.append(tid)
        ids = matching
    return {"trace_ids": ids, "count": len(ids)}


async def get_summaries(
    tracer: Tracer,
) -> dict[str, Any]:
    """Read all trace summaries."""
    summary_path = tracer.summary_path
    summaries: list[dict[str, Any]] = []
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    with contextlib.suppress(json.JSONDecodeError):
                        summaries.append(json.loads(line))
    return {"summaries": summaries, "count": len(summaries)}


async def enforce_retention(
    tracer: Tracer,
) -> dict[str, Any]:
    """Manually trigger trace retention enforcement."""
    result = tracer.enforce_retention()
    return {
        "retention_applied": True,
        "errors_kept": result["errors_kept"],
        "successful_deleted": result["successful_deleted"],
        "raw_spans_deleted": result["raw_spans_deleted"],
    }
