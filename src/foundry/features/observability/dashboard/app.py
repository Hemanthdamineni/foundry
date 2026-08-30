"""Dashboard FastAPI app — the single admin dashboard for Foundry.

Creates a FastAPI application with HTML and JSON endpoints that surface
system state from the store, guardrails, event bus, and approval gate.

Usage::

    from foundry.features.observability.dashboard.app import create_app

    app = create_app(store=store, budget_tracker=tracker)
    # then ``uvicorn app.run(...)`` or use the ``foundry dashboard`` CLI
"""

from __future__ import annotations

import logging
import textwrap
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from foundry.core.logging import get_logger
from foundry.features.observability.collectors.event_collector import EventCollector

if TYPE_CHECKING:
    from foundry.core.guardrails import BudgetTracker
    from foundry.core.store.ensure_initialized import StoreBackend

logger = get_logger("observability.dashboard")

# ──────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────


def create_app(
    store: StoreBackend | None = None,
    budget_tracker: BudgetTracker | None = None,
    title: str = "Foundry Dashboard",
) -> FastAPI:
    """Build and return a configured FastAPI application.

    Parameters
    ----------
    store:
        Initialised ``StoreBackend``.  May be ``None``; the dashboard
        will show empty data for store-backed endpoints.
    budget_tracker:
        Initialised ``BudgetTracker``.  May be ``None``; the dashboard
        will show placeholder budget information.
    title:
        HTML page title.
    """
    app = FastAPI(title=title)
    collector = EventCollector(store=store, budget_tracker=budget_tracker)

    # ── JSON API routes ──────────────────────────────────────────

    @app.get("/api/transitions")
    async def api_transitions(limit: int = 50) -> JSONResponse:
        """Phase-transition history from the store."""
        transitions = collector.poll_transitions(limit=limit)
        return JSONResponse({"ok": True, "count": len(transitions), "transitions": transitions})

    @app.get("/api/debates")
    async def api_debates(limit: int = 30) -> JSONResponse:
        """Live debate status — combines store debate_logs with event-bus events."""
        debate_logs = collector.poll_debate_logs(limit=limit)
        events = collector.poll_event_bus()
        return JSONResponse(
            {
                "ok": True,
                "debate_log_count": len(debate_logs),
                "debate_logs": debate_logs,
                "event_count": len(events),
                "events": events,
            }
        )

    @app.get("/api/approvals")
    async def api_approvals() -> JSONResponse:
        """Pending approval requests from the approval gate."""
        pending = collector.poll_approvals()
        return JSONResponse({"ok": True, "count": len(pending), "pending_approvals": pending})

    @app.get("/api/guardrails")
    async def api_guardrails() -> JSONResponse:
        """Budget and limit status from the guardrails module."""
        status = collector.poll_guardrails()
        return JSONResponse({"ok": True, "guardrails": status})

    @app.get("/api/checkpoints")
    async def api_checkpoints(limit: int = 20) -> JSONResponse:
        """Recent checkpoints from the store."""
        checkpoints = collector.poll_checkpoints(limit=limit)
        return JSONResponse({"ok": True, "count": len(checkpoints), "checkpoints": checkpoints})

    @app.get("/api/tasks")
    async def api_tasks(limit: int = 50) -> JSONResponse:
        """Recent tasks from the store."""
        tasks = collector.poll_tasks(limit=limit)
        return JSONResponse({"ok": True, "count": len(tasks), "tasks": tasks})

    # ── HTML dashboard ───────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_index(request: Request) -> str:
        """Main dashboard page — a single-page HTML app."""
        return _render_dashboard_html(title)

    return app


# ──────────────────────────────────────────────────────────────────
# Standalone runner (used by ``foundry dashboard`` CLI)
# ──────────────────────────────────────────────────────────────────


def run_dashboard(
    store: StoreBackend | None = None,
    budget_tracker: BudgetTracker | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 3000,
    title: str = "Foundry Dashboard",
) -> None:
    """Start the dashboard server (blocking).

    Parameters
    ----------
    store:
        Initialised ``StoreBackend``.
    budget_tracker:
        Initialised ``BudgetTracker``.
    host:
        Bind address (default ``127.0.0.1``).
    port:
        Bind port (default ``3000``).
    title:
        HTML page title.
    """
    import uvicorn  # type: ignore[import-untyped]  # noqa: PLC0415

    app = create_app(store=store, budget_tracker=budget_tracker, title=title)
    logger.info("Starting dashboard on http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


# ──────────────────────────────────────────────────────────────────
# Dashboard HTML template
# ──────────────────────────────────────────────────────────────────

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --green: #3fb950;
    --yellow: #d29922;
    --red: #f85149;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); padding: 1.5rem;
  }}
  h1 {{ font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }}
  h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 1rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; }}
  .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
  .badge {{ font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 12px; background: var(--border); }}
  .badge.ok {{ background: var(--green); color: #000; }}
  .badge.warn {{ background: var(--yellow); color: #000; }}
  .badge.err {{ background: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; }}
  tr:hover td {{ background: rgba(88,166,255,0.05); }}
  .mono {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 0.8rem; }}
  .muted {{ color: var(--muted); }}
  .flex {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .stat {{ text-align: center; flex: 1; min-width: 80px; }}
  .stat-value {{ font-size: 1.5rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.75rem; color: var(--muted); }}
  .error-state {{ color: var(--red); font-style: italic; }}
  .loading {{ color: var(--muted); }}
  .refresh-btn {{
    float: right; background: var(--border); color: var(--text);
    border: none; border-radius: 4px; padding: 0.25rem 0.75rem;
    cursor: pointer; font-size: 0.8rem;
  }}
  .refresh-btn:hover {{ background: var(--accent); color: #000; }}
</style>
</head>
<body>

<h1>__TITLE__</h1>

<div class="grid">

  <!-- Guardrails / Budget card -->
  <div class="card" id="card-guardrails">
    <div class="card-header">
      <h2>Budget &amp; Limits</h2>
      <span class="badge" id="guardrails-badge">loading</span>
    </div>
    <div class="flex" id="guardrails-stats"></div>
    <div class="flex" id="guardrails-limits" style="margin-top:0.5rem;"></div>
  </div>

  <!-- Phase transitions card -->
  <div class="card" id="card-transitions">
    <div class="card-header">
      <h2>Phase Transitions</h2>
      <button class="refresh-btn" onclick="loadTransitions()">refresh</button>
    </div>
    <div id="transitions-content"><p class="loading">Loading...</p></div>
  </div>

  <!-- Debates card -->
  <div class="card" id="card-debates">
    <div class="card-header">
      <h2>Debates &amp; Events</h2>
      <button class="refresh-btn" onclick="loadDebates()">refresh</button>
    </div>
    <div id="debates-content"><p class="loading">Loading...</p></div>
  </div>

  <!-- Approvals card -->
  <div class="card" id="card-approvals">
    <div class="card-header">
      <h2>Pending Approvals</h2>
      <button class="refresh-btn" onclick="loadApprovals()">refresh</button>
    </div>
    <div id="approvals-content"><p class="loading">Loading...</p></div>
  </div>

</div>

<script>
async function fetchJSON(url) {{
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}}

function escapeHTML(s) {{
  if (s == null) return '<span class="muted">--</span>';
  const d = document.createElement('div');
  d.textContent = String(s).slice(0, 120);
  return d.innerHTML;
}}

// ── Guardrails ─────────────────────────────────────────────────
async function loadGuardrails() {{
  const el = document.getElementById('guardrails-stats');
  const badge = document.getElementById('guardrails-badge');
  const limitsEl = document.getElementById('guardrails-limits');
  try {{
    const d = await fetchJSON('/api/guardrails');
    const g = d.guardrails || {{}};
    const exhausted = g.budget_exhausted;
    badge.textContent = exhausted ? 'EXHAUSTED' : 'OK';
    badge.className = 'badge ' + (exhausted ? 'err' : 'ok');
    el.innerHTML = `
      <div class="stat"><div class="stat-value">${escapeHTML(g.tokens_used)}</div><div class="stat-label">Tokens</div></div>
      <div class="stat"><div class="stat-value">${escapeHTML(g.steps_used)}</div><div class="stat-label">Steps</div></div>
      <div class="stat"><div class="stat-value">${escapeHTML(g.cost_incurred)}</div><div class="stat-label">Cost</div></div>
    `;
    if (g.limits) {{
      const L = g.limits;
      limitsEl.innerHTML = `
        <div class="stat"><div class="stat-value">${L.max_tokens || '&#8734;'}</div><div class="stat-label">Max tokens</div></div>
        <div class="stat"><div class="stat-value">${L.max_steps || '&#8734;'}</div><div class="stat-label">Max steps</div></div>
        <div class="stat"><div class="stat-value">${L.max_cost || '&#8734;'}</div><div class="stat-label">Max cost</div></div>
      `;
    }}
  }} catch(e) {{
    badge.textContent = 'ERR';
    badge.className = 'badge err';
    el.innerHTML = `<p class="error-state">Failed to load: ${escapeHTML(e.message)}</p>`;
  }}
}}

// ── Transitions ────────────────────────────────────────────────
async function loadTransitions() {{
  const el = document.getElementById('transitions-content');
  try {{
    const d = await fetchJSON('/api/transitions?limit=20');
    if (d.count === 0) {{ el.innerHTML = '<p class="muted">No transitions recorded yet.</p>'; return; }}
    let html = '<table><thead><tr><th>Task</th><th>Phase</th><th>When</th></tr></thead><tbody>';
    for (const t of d.transitions) {{
      html += `<tr><td class="mono">${escapeHTML(t.task_id)}</td><td>${escapeHTML(t.phase)}</td><td class="mono">${escapeHTML(t.transitioned_at)}</td></tr>`;
    }}
    html += '</tbody></table>';
    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = `<p class="error-state">Failed to load: ${escapeHTML(e.message)}</p>`;
  }}
}}

// ── Debates ────────────────────────────────────────────────────
async function loadDebates() {{
  const el = document.getElementById('debates-content');
  try {{
    const d = await fetchJSON('/api/debates?limit=15');
    if (d.debate_log_count === 0 && d.event_count === 0) {{
      el.innerHTML = '<p class="muted">No debate activity yet.</p>';
      return;
    }}
    let html = '<table><thead><tr><th>Agent</th><th>Round</th><th>Verdict</th><th>When</th></tr></thead><tbody>';
    for (const log of d.debate_logs.slice(0, 15)) {{
      html += `<tr><td>${escapeHTML(log.agent_role)}</td><td>${escapeHTML(log.round_num)}</td><td>${escapeHTML(log.verdict)}</td><td class="mono">${escapeHTML(log.created_at)}</td></tr>`;
    }}
    html += '</tbody></table>';
    if (d.event_count > 0) {{
      html += `<p class="muted" style="margin-top:0.5rem">${d.event_count} live event-bus event(s)</p>`;
    }}
    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = `<p class="error-state">Failed to load: ${escapeHTML(e.message)}</p>`;
  }}
}}

// ── Approvals ──────────────────────────────────────────────────
async function loadApprovals() {{
  const el = document.getElementById('approvals-content');
  try {{
    const d = await fetchJSON('/api/approvals');
    if (d.count === 0) {{ el.innerHTML = '<p class="muted">No pending approvals.</p>'; return; }}
    let html = '<table><thead><tr><th>Session</th><th>Command</th><th>Status</th></tr></thead><tbody>';
    for (const a of d.pending_approvals) {{
      html += `<tr><td class="mono">${escapeHTML(a.session_key)}</td><td class="mono">${escapeHTML(a.command)}</td><td><span class="badge warn">${escapeHTML(a.status)}</span></td></tr>`;
    }}
    html += '</tbody></table>';
    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = `<p class="error-state">Failed to load: ${escapeHTML(e.message)}</p>`;
  }}
}}

// ── Initial load ───────────────────────────────────────────────
loadGuardrails();
loadTransitions();
loadDebates();
loadApprovals();
// Auto-refresh every 10 s
setInterval(loadGuardrails, 10000);
setInterval(loadTransitions, 15000);
setInterval(loadDebates, 15000);
setInterval(loadApprovals, 10000);
</script>
</body>
</html>
"""


def _render_dashboard_html(title: str) -> str:
    """Fill in the HTML template with the given title."""
    return _DASHBOARD_HTML.replace("__TITLE__", title)
