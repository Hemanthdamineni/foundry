"""foundry sdlc <cmd> — SDLC runtime commands.

Wires into the sdlc_runtime engine for phase graph operations,
task management, and workflow execution.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("cli.sdlc")


def main(args: list[str] | None = None) -> None:
    """Run SDLC lifecycle commands.

    Parameters
    ----------
    args:
        CLI arguments (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(description="SDLC lifecycle commands")
    sub = parser.add_subparsers(dest="action", help="SDLC action")

    sub.add_parser("status", help="Show current SDLC runtime status")
    sub.add_parser("phases", help="List available phases and transitions")

    start_p = sub.add_parser("start", help="Start a new SDLC task")
    start_p.add_argument("--description", "-d", required=True, help="Task description")
    start_p.add_argument("--mode", "-m", default="feature",
                         choices=["feature", "bugfix", "refactor", "research", "docs"],
                         help="Workflow mode (default: feature)")

    list_p = sub.add_parser("list", help="List tasks")
    list_p.add_argument("--status", "-s", default=None, help="Filter by status")

    get_p = sub.add_parser("get", help="Get task details")
    get_p.add_argument("task_id", help="Task ID")

    cancel_p = sub.add_parser("cancel", help="Cancel a task")
    cancel_p.add_argument("task_id", help="Task ID")

    sub.add_parser("graph", help="Show the phase graph")

    parsed = parser.parse_args(args)

    match parsed.action:
        case "status":
            _cmd_status()
        case "phases":
            _cmd_phases()
        case "graph":
            _cmd_graph()
        case "start":
            asyncio.run(_cmd_start(parsed.description, parsed.mode))
        case "list":
            asyncio.run(_cmd_list(parsed.status))
        case "get":
            asyncio.run(_cmd_get(parsed.task_id))
        case "cancel":
            asyncio.run(_cmd_cancel(parsed.task_id))
        case _:
            parser.print_help()
            sys.exit(1)


def _cmd_status() -> None:
    """Show SDLC runtime status."""
    from foundry.core.orchestrator.phase_graph import PhaseGraph

    print("SDLC Runtime: available")
    # Check for SQLite store
    store_path = Path.cwd() / ".foundry" / "sdlc.db"
    if store_path.exists():
        size_kb = store_path.stat().st_size / 1024
        print(f"  Store:     {store_path} ({size_kb:.1f} KB)")
    else:
        print("  Store:     Not initialised (run 'foundry sdlc start' to create)")

    # Check config
    config_dir = Path.cwd() / "config"
    if config_dir.exists():
        yaml_files = list(config_dir.glob("*.yaml"))
        print(f"  Config:    {config_dir} ({len(yaml_files)} YAML files)")
    else:
        print("  Config:    Not found (run from project root with config/)")


def _cmd_phases() -> None:
    """List available phases."""
    print("SDLC Phases:")
    print()
    phases = [
        ("Chatting", "Initial requirements gathering and context discovery"),
        ("Specs", "Formal specification with requirements, scope, and constraints"),
        ("Planning", "Implementation plan with file changes and risk assessment"),
        ("Coding", "Implementation of the planned changes"),
        ("Review", "Quality assessment and review"),
        ("Done", "Task completed"),
    ]
    for name, desc in phases:
        print(f"  {name:12s} — {desc}")
    print()
    print("Transitions:")
    print("  Chatting → Specs, Done")
    print("  Specs    → Planning")
    print("  Planning → Coding")
    print("  Coding   → Review")
    print("  Review   → Coding, Done")
    print()


def _cmd_graph() -> None:
    """Print the current phase graph."""
    config_path = Path.cwd() / "config" / "phase_graph.yaml"
    if config_path.exists():
        import yaml

        data = yaml.safe_load(config_path.read_text()) or {}
        phases = data.get("phases", {})
        print("Phase Graph (from config/phase_graph.yaml):")
        for phase, targets in phases.items():
            targets_str = ", ".join(targets) if targets else "(terminal)"
            print(f"  {phase:12s} → {targets_str}")
    else:
        print("Phase Graph: using defaults (config/phase_graph.yaml not found)")
        print("  Chatting → Specs, Done")
        print("  Specs    → Planning")
        print("  Planning → Coding")
        print("  Coding   → Review")
        print("  Review   → Coding, Done")
        print("  Done     → (terminal)")


async def _cmd_start(description: str, mode: str = "feature") -> None:
    """Start a new SDLC task using the runtime engine."""
    import uuid

    from foundry.core.models import WriteOp
    from foundry.core.store import SqliteStore

    store_path = Path.cwd() / ".foundry" / "sdlc.db"
    store = SqliteStore(store_path)
    await store.initialize()

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()

    task: dict[str, Any] = {
        "task_id": task_id,
        "description": description,
        "mode": mode,
        "status": "queued",
        "current_phase": "Chatting",
        "history": [],
        "iteration_count": 0,
        "retry_count": 0,
        "locked_prompts": {},
        "created_at": now,
        "updated_at": now,
    }

    await store.create_task(task)

    print(f"SDLC task created:")
    print(f"  Task ID:     {task_id}")
    print(f"  Description: {description}")
    print(f"  Mode:        {mode}")
    print(f"  Status:      queued")
    print(f"  Phase:       Chatting")
    print()
    print(f"To advance: use 'foundry orchestrate --description \"{description}\"'")
    print(f"Or start the MCP server with 'foundry mcp' for full tool access.")

    await store.checkpoint()
    await store.close()


async def _cmd_list(status: str | None = None) -> None:
    """List tasks from the store."""
    from foundry.core.store import SqliteStore

    store_path = Path.cwd() / ".foundry" / "sdlc.db"
    if not store_path.exists():
        print("No tasks found — SDLC store not initialised.")
        print("Run 'foundry sdlc start' to create a task.")
        return

    store = SqliteStore(store_path)
    await store.initialize()
    tasks = await store.list_tasks(status=status)

    if not tasks:
        print("No tasks found.")
        if status:
            print(f"  (filtered by status: {status})")
        await store.close()
        return

    print(f"Tasks ({len(tasks)}):")
    for t in tasks:
        print(f"  {t.get('task_id', '?'):36s} | {t.get('status', '?'):10s} | "
              f"{t.get('current_phase', '?'):12s} | {t.get('description', '')[:50]}")

    await store.close()


async def _cmd_get(task_id: str) -> None:
    """Get details for a specific task."""
    from foundry.core.store import SqliteStore

    store_path = Path.cwd() / ".foundry" / "sdlc.db"
    store = SqliteStore(store_path)
    await store.initialize()

    task = await store.get_task(task_id)
    if task is None:
        print(f"Task not found: {task_id}")
        await store.close()
        return

    history = task.get("history", [])
    print(f"Task:          {task.get('task_id')}")
    print(f"Description:   {task.get('description', '')}")
    print(f"Mode:          {task.get('mode', 'feature')}")
    print(f"Status:        {task.get('status', 'unknown')}")
    print(f"Current Phase: {task.get('current_phase', '')}")
    print(f"Iterations:    {task.get('iteration_count', 0)}")
    print(f"Created:       {task.get('created_at', '')}")
    print(f"Updated:       {task.get('updated_at', '')}")
    print(f"History:       {len(history)} phase(s) recorded")
    for h in history:
        phase_name = h.get("phase", "?")
        phase_status = h.get("status", "?")
        output_preview = (h.get("output") or "")[:80]
        print(f"  - {phase_name:12s} [{phase_status}]: {output_preview!r}")

    await store.close()


async def _cmd_cancel(task_id: str) -> None:
    """Cancel a task."""
    from foundry.core.store import SqliteStore

    store_path = Path.cwd() / ".foundry" / "sdlc.db"
    store = SqliteStore(store_path)
    await store.initialize()

    task = await store.get_task(task_id)
    if task is None:
        print(f"Task not found: {task_id}")
        await store.close()
        return

    task["status"] = "cancelled"
    task["updated_at"] = datetime.now(UTC).isoformat()
    await store.update_task(task_id, task)

    print(f"Task {task_id} cancelled.")

    await store.close()
