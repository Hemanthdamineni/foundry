"""Rich-based dashboard for TUI."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from foundry.core.health import HealthChecker, HealthStatus


class Dashboard:
    """Rich-based TUI dashboard for Foundry system monitoring."""

    def __init__(
        self,
        port: int = 8050,
        health_checker: HealthChecker | None = None,
    ) -> None:
        self.port = port
        self.health_checker = health_checker or HealthChecker()
        self.console = Console()

    def run(self) -> None:
        """Run the dashboard."""
        self.console.clear()
        self.console.print("[bold blue]Helix Dashboard[/bold blue]")
        self.console.print("[dim]Running on port[/dim] [green]":self.port[/green]")
        self.console.print("=" * 60)
        self.console.print("[yellow]Dashboard mode active. Press Ctrl+C to exit.[/yellow]")