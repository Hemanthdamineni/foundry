"""Generic webhook notification channel."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 15

# A payload builder receives the canonical parameters and returns a
# serialisable dict (or a raw string when content_type is not JSON).
PayloadBuilder = Callable[[str, str, str], dict[str, Any] | str]


def _default_payload_builder(
    message: str,
    severity: str,
    event_type: str,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class GenericWebhookNotifier:
    """Send notifications to an arbitrary HTTP endpoint.

    Parameters
    ----------
    url:
        Target URL.
    headers:
        Optional HTTP headers to include on every request
        (e.g. ``{"Authorization": "Bearer ..."}``).
    content_type:
        Media type for the payload.  ``"application/json"`` (default)
        serialises the dict from *payload_builder* as JSON.
        ``"application/x-www-form-urlencoded"`` sends the payload as-is
        (expected to be a string).
    payload_builder:
        Callable ``(message, severity, event_type) -> dict | str`` that
        constructs the outgoing payload.  Defaults to a simple dict with
        ``event_type``, ``severity``, ``message``, and ``timestamp``.
        Ignored when *payload_template* is provided.
    payload_template:
        Optional template string with ``{message}``, ``{severity}``,
        ``{event_type}`` placeholders.  When set, *payload_builder* is
        ignored.
    timeout_s:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content_type: str = "application/json",
        payload_builder: PayloadBuilder | None = None,
        payload_template: str | None = None,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._content_type = content_type
        self._payload_builder = payload_builder or _default_payload_builder
        self._payload_template = payload_template
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(
        self,
        message: str,
        severity: str = "info",
        event_type: str = "generic",
    ) -> bool:
        """POST a notification to the configured webhook URL.

        Parameters
        ----------
        message:
            Notification body text.
        severity:
            Severity label (``"info"``, ``"warning"``, ``"error"``,
            ``"critical"``).
        event_type:
            Event category label.

        Returns
        -------
        bool
            ``True`` on a 2xx response, ``False`` otherwise.
        """
        payload = self._render_payload(message, severity, event_type)

        headers = self._headers.copy()
        data: str | bytes
        if self._content_type == "application/json":
            headers.setdefault("Content-Type", "application/json")
            data = json.dumps(payload, default=str)
        else:
            headers.setdefault("Content-Type", self._content_type)
            data = payload if isinstance(payload, str) else json.dumps(payload, default=str)

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            try:
                resp = await client.post(self._url, content=data, headers=headers)
                if resp.is_success:
                    return True

                logger.error(
                    "Webhook %s returned %s: %s",
                    self._url,
                    resp.status_code,
                    resp.text[:300],
                )
                return False
            except httpx.RequestError as exc:
                logger.error("Webhook %s request failed: %s", self._url, exc)
                return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_payload(
        self,
        message: str,
        severity: str,
        event_type: str,
    ) -> dict[str, Any] | str:
        if self._payload_template:
            return self._payload_template.format(
                message=message,
                severity=severity,
                event_type=event_type,
            )
        return self._payload_builder(message, severity, event_type)
