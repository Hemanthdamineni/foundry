"""Debug and tracing tool functions for the MCP server.

Each function corresponds to an ``@app.tool()`` handler in ``runtime/app.py``
and exists here so the tool handlers stay thin — all real logic lives in these
standalone async functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from foundry.features.sdlc_runtime.runtime.tracing import Tracer


async def get_trace(tracer: Tracer, trace_id: str) -> dict[str, Any]:
    """Retrieve a single trace by ID.

    Parameters
    ----------
    tracer:
        The active tracer instance.
    trace_id:
        Unique trace identifier to look up.

    Returns
    -------
    dict
        Trace data keyed as ``{trace_id: …, spans: […]}`` or an error dict.
    """
    try:
        spans = tracer.read_trace(trace_id)
    except Exception as exc:
        return {"error": f"Failed to read trace: {exc}"}

    if not spans:
        return {"error": f"Trace not found: {trace_id}"}

    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "spans": spans,
    }


async def list_traces(
    tracer: Tracer,
    task_id: str | None = None,
) -> dict[str, Any]:
    """List available traces, optionally filtered by task.

    Note: tracer.list_trace_ids() does not support filtering by task_id
    at the storage level, so when task_id is provided we filter in-memory.

    Parameters
    ----------
    tracer:
        The active tracer instance.
    task_id:
        Optional task ID to filter on.

    Returns
    -------
    dict
        ``{trace_ids: […], total: N}`` or an error dict.
    """
    try:
        all_ids = tracer.list_trace_ids()
    except Exception as exc:
        return {"error": f"Failed to list traces: {exc}"}

    # Filter by task_id if provided — scan each trace's first span for a match
    if task_id:
        filtered: list[str] = []
        for tid in all_ids:
            spans = tracer.read_trace(tid)
            if any(s.get("task_id") == task_id for s in spans[:5]):
                filtered.append(tid)
        all_ids = filtered

    return {
        "trace_ids": all_ids,
        "total": len(all_ids),
    }


async def get_summaries(tracer: Tracer) -> dict[str, Any]:
    """Retrieve trace summary statistics from the summaries JSONL file.

    Parameters
    ----------
    tracer:
        The active tracer instance.

    Returns
    -------
    dict
        ``{summaries: […], total: N}`` or an error dict.
    """
    summary_path = tracer.summary_path
    if not summary_path.exists():
        return {"summaries": [], "total": 0}

    summaries: list[dict[str, Any]] = []
    try:
        with summary_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    summaries.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"Failed to read summaries: {exc}"}

    return {
        "summaries": summaries,
        "total": len(summaries),
    }


async def enforce_retention(tracer: Tracer) -> dict[str, Any]:
    """Enforce retention policy — purge expired traces.

    Parameters
    ----------
    tracer:
        The active tracer instance.

    Returns
    -------
    dict
        Status and count of purged traces.
    """
    try:
        result = tracer.enforce_retention()
    except Exception as exc:
        return {"error": f"Failed to enforce retention: {exc}"}

    return {
        "status": "ok",
        "purged_count": result.get("successful_deleted", 0) + result.get("raw_spans_deleted", 0),
        "details": result,
    }
