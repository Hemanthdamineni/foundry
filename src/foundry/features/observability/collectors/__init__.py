"""Collectors — data-gathering adapters for observability sources.

Each collector wraps a single external subsystem and returns plain dicts
suitable for JSON serialization.  Collectors are *non-blocking*: they
catch and log errors rather than propagating them, so a failure in one
source never brings down the dashboard.
"""

from foundry.features.observability.collectors.event_collector import EventCollector

__all__ = [
    "EventCollector",
]
