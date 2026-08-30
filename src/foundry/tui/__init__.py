"""TUI package — terminal interface for Helix.

Provides a terminal-based dashboard and interaction surface for monitoring
and managing Foundry operations.

Key architectural reference:
    L3 Agent Interaction — "5-column dashboard"
"""

from foundry.core.health import HealthChecker, HealthReport

# Lazy import HelixTUI to avoid importing textual at package level
__all__ = ["HelixTUI", "launch_dashboard", "launch_tui"]


def __getattr__(name: str):
    if name == "HelixTUI":
        from foundry.tui.app import HelixTUI
        return HelixTUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def launch_dashboard(
    *,
    port: int = 8050,
    health_checker: HealthChecker | None = None,
) -> None:
    """Launch the Helix TUI dashboard (legacy dashboard mode).

    Parameters
    ----------
    port:
        Network port for the dashboard server.
    health_checker:
        Optional HealthChecker instance for system status.
    """
    try:
        import rich
    except ImportError as e:
        raise ImportError(
            "The rich package is required for the TUI dashboard. "
            "Install it with: pip install rich"
        ) from e

    from foundry.tui.views.dashboard import Dashboard

    # Run dashboard
    dashboard = Dashboard(port, health_checker or HealthChecker())
    dashboard.run()


def launch_tui() -> None:
    """Launch the Helix Textual TUI (5-column interface)."""
    from foundry.tui.app import HelixTUI

    app = HelixTUI()
    app.run()