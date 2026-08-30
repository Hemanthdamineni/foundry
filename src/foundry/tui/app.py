"""HelixTUI — Textual-based 5-column terminal interface for Helix.

Architecture reference:
    L3 Agent Interaction — "5-column layout"

Column layout:
    ┌────────────────┬────────────────┬────────────────┬────────────────┬────────────────┐
    │   Workspace    │     Tasks      │    Context     │   Terminal     │     Logs       │
    │   Workspace 1  │  T-001 running │ project/       │ $ _            │ 10:30:15 INFO  │
    │   Workspace 2  │  T-002 pending │ └── src/       │                 │ 10:30:16 DEBUG │
    │   ...          │  T-003 done    │    └── main.py │                 │ 10:30:17 ERROR │
    └────────────────┴────────────────┴────────────────┴────────────────┴────────────────┘
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Tree,
)


# --------------------------------------------------------------------------- #
#  Custom panels
# --------------------------------------------------------------------------- #


class WorkspacePanel(Static):
    """Column 1: Workspace list and management."""

    def compose(self) -> ComposeResult:
        yield Label("📁 Workspaces", classes="panel-title")
        yield ListView(id="workspace-list")
        yield Input(placeholder=":new workspace...", id="workspace-input")
        yield Button("Create", id="ws-create-btn", variant="primary")


class TaskPanel(Static):
    """Column 2: Task queue and status."""

    def compose(self) -> ComposeResult:
        yield Label("📋 Tasks", classes="panel-title")
        yield DataTable(id="task-table", cursor_type="row")
        yield Input(placeholder=":new task...", id="task-input")
        yield Button("Run", id="task-run-btn", variant="primary")


class ContextPanel(Static):
    """Column 3: Context graph / file explorer."""

    def compose(self) -> ComposeResult:
        yield Label("🔍 Context", classes="panel-title")
        yield Tree("Project", id="context-tree")
        yield Label("Symbols", classes="panel-title")
        yield DataTable(id="symbol-table", cursor_type="row")


class TerminalPanel(Static):
    """Column 4: Terminal / command output."""

    def compose(self) -> ComposeResult:
        yield Label("⚡ Terminal", classes="panel-title")
        yield Static("$ _", id="terminal-out")
        yield Input(placeholder=":command...", id="terminal-input")


class LogPanel(Static):
    """Column 5: Event log stream."""

    def compose(self) -> ComposeResult:
        yield Label("📜 Events", classes="panel-title")
        yield DataTable(id="log-table", cursor_type="row")


# --------------------------------------------------------------------------- #
#  Main App
# --------------------------------------------------------------------------- #


class HelixTUI(App):
    """Helix 5-column terminal interface."""

    TITLE = "Helix"
    SUB_TITLE = "Autonomous Engineering Platform"

    CSS = """
    .panel-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
        margin-bottom: 1;
    }

    Horizontal > Static {
        width: 1fr;
        border: solid $surface;
        margin: 0 1;
    }

    #task-table, #symbol-table, #log-table {
        height: 1fr;
    }

    #terminal-out {
        height: 1fr;
        background: $surface;
        color: $text;
        padding: 1;
    }

    Input {
        margin: 1;
    }

    Button {
        margin: 0 1 1 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "focus_terminal", "Terminal"),
        Binding("w", "focus_workspace", "Workspaces"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            WorkspacePanel(),
            TaskPanel(),
            ContextPanel(),
            TerminalPanel(),
            LogPanel(),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Populate initial data."""
        self._populate_workspaces()
        self._populate_tasks()
        self._populate_context()
        self._populate_logs()

    def _populate_workspaces(self) -> None:
        ws_list = self.query_one("#workspace-list", ListView)
        for name, path in [("main", "/proj/main"), ("feature", "/proj/feature")]:
            ws_list.append(ListItem(Static(f"{name}  [{path}]")))

    def _populate_tasks(self) -> None:
        t = self.query_one("#task-table", DataTable)
        t.add_columns("ID", "Description", "Status")
        t.add_row("T1", "Implement auth", "running")
        t.add_row("T2", "Add tests", "pending")

    def _populate_context(self) -> None:
        tr = self.query_one("#context-tree", Tree)
        tr.root.expand()
        tr.root.add("src/").add("foundry/").add("core/")

        sym = self.query_one("#symbol-table", DataTable)
        sym.add_columns("Name", "Kind")
        sym.add_row("WorkspaceManager", "class")
        sym.add_row("SessionManager", "class")

    def _populate_logs(self) -> None:
        t = self.query_one("#log-table", DataTable)
        t.add_columns("Time", "Event")
        t.add_row("10:30:15", "Task T1 started")
        t.add_row("10:30:17", "Planner turn")

    def action_refresh(self) -> None:
        self.notify("Refreshing panels...")

    def action_focus_terminal(self) -> None:
        self.query_one("#terminal-input", Input).focus()

    def action_focus_workspace(self) -> None:
        self.query_one("#workspace-input", Input).focus()
