"""Notification manager — route events to configured alerting channels."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Channel protocol (duck-type interface)
# ---------------------------------------------------------------------------


class NotificationChannel(Protocol):
    """Minimal interface every channel must satisfy.

    Any object with an ``async send(message, severity, event_type)``
    method that returns ``bool`` is accepted.
    """

    async def send(
        self,
        message: str,
        severity: str = "info",
        event_type: str = "generic",
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Routing rule
# ---------------------------------------------------------------------------


@dataclass
class _Route:
    """A channel and the set of events/severities it handles."""

    channel: NotificationChannel
    event_types: set[str] = field(default_factory=lambda: {"*"})
    severities: set[str] = field(default_factory=lambda: {"*"})

    def matches(self, event_type: str, severity: str) -> bool:
        """Check whether this route applies to *event_type* + *severity*."""
        return (("*" in self.event_types or event_type in self.event_types)
                and ("*" in self.severities or severity in self.severities))


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class NotificationManager:
    """Route alert messages to registered channels based on event type and severity.

    Typical usage::

        manager = NotificationManager()
        manager.register_channel(slack_channel, event_types="nightly", severities="error")
        manager.register_channel(email_channel, event_types="*", severities="critical")
        await manager.send("nightly", "Nightly build failed", "error")

    Intended consumers
    ------------------
    * **Nightly failures**  → ``send("nightly", ...)``
    * **Guardrail breaches** → ``send("guardrail", ...)``
    * **Eval regressions**  → ``send("eval_regression", ...)``
    """

    def __init__(self) -> None:
        self._routes: list[_Route] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def register_channel(
        self,
        channel: NotificationChannel,
        *,
        event_types: str | Sequence[str] | None = None,
        severities: str | Sequence[str] | None = None,
    ) -> None:
        """Register *channel* to receive notifications matching the filters.

        Parameters
        ----------
        channel:
            Any object whose ``send(message, severity, event_type)``
            returns ``bool``.
        event_types:
            One or more event types this channel handles.  ``"*"`` or
            ``None`` means all events.
        severities:
            One or more severity levels this channel handles.  ``"*"`` or
            ``None`` means all severities.
        """
        self._routes.append(
            _Route(
                channel=channel,
                event_types=_normalise_set(event_types, {"*"}),
                severities=_normalise_set(severities, {"*"}),
            )
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def send(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        **kwargs: Any,
    ) -> int:
        """Send *message* to every matching registered channel.

        Parameters
        ----------
        event_type:
            Event category (e.g. ``"nightly"``, ``"guardrail"``,
            ``"eval_regression"``).
        message:
            Notification body.
        severity:
            Severity label.  Standard values: ``"debug"``, ``"info"``,
            ``"warning"``, ``"error"``, ``"critical"``.
        **kwargs:
            Forwarded to each channel's ``send()`` method as extra
            keyword arguments.

        Returns
        -------
        int
            Number of channels that were successfully notified.
        """
        # Normalise once so downstream channels don't have to.
        severity = severity.lower()
        event_type = event_type.lower()

        successes = 0
        for route in self._routes:
            if not route.matches(event_type, severity):
                continue
            try:
                ok = await route.channel.send(
                    message=message,
                    severity=severity,
                    event_type=event_type,
                    **kwargs,
                )
                if ok:
                    successes += 1
                else:
                    logger.warning(
                        "Channel %s returned failure for %s/%s",
                        type(route.channel).__name__,
                        event_type,
                        severity,
                    )
            except Exception:
                logger.exception(
                    "Channel %s raised for %s/%s",
                    type(route.channel).__name__,
                    event_type,
                    severity,
                )
        return successes

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def route_count(self) -> int:
        """Number of registered routes."""
        return len(self._routes)

    def clear(self) -> None:
        """Remove all registered routes."""
        self._routes.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_set(
    value: str | Sequence[str] | None,
    default: set[str],
) -> set[str]:
    if value is None:
        return default
    if isinstance(value, str):
        return {value.lower()}
    return {v.lower() for v in value}
