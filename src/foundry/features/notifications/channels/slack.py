"""Slack notification channel via Incoming Webhook."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 15


class SlackNotifier:
    """Send messages to a Slack workspace via an Incoming Webhook.

    Parameters
    ----------
    webhook_url:
        Full Slack Incoming Webhook URL
        (e.g. ``https://hooks.slack.com/services/T00/B00/xxx``).
    default_channel:
        Optional Slack channel or DM to target (overrides the webhook's
        default channel for every message).
    timeout_s:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        default_channel: str | None = None,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._webhook_url = webhook_url
        self._default_channel = default_channel
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(
        self,
        message: str,
        severity: str = "info",
        event_type: str = "generic",
        *,
        channel: str | None = None,
        **extra: Any,
    ) -> bool:
        """Post *message* to the configured Slack webhook.

        Parameters
        ----------
        message:
            Plain-text or Slack-markdown message body.
        severity:
            One of ``"debug"``, ``"info"``, ``"warning"``, ``"error"``,
            ``"critical"``.  Used to pick an emoji prefix and colour.
        event_type:
            Label for the kind of event (e.g. ``"nightly"``,
            ``"guardrail"``, ``"eval_regression"``).
        channel:
            Override the target Slack channel for this message only.
        **extra:
            Additional fields merged into the JSON payload (e.g.
            ``attachments``, ``blocks``).

        Returns
        -------
        bool
            ``True`` on a 2xx response, ``False`` otherwise.
        """
        payload = self._build_payload(message, severity, event_type, channel=channel, **extra)

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            try:
                resp = await client.post(self._webhook_url, json=payload)
                if resp.is_success:
                    return True

                logger.error(
                    "Slack webhook returned %s: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
            except httpx.RequestError as exc:
                logger.error("Slack webhook request failed: %s", exc)
                return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        message: str,
        severity: str,
        event_type: str,
        *,
        channel: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        severity = severity.lower()
        prefix, colour = _SEVERITY_MAP.get(severity, ("", "#808080"))

        payload: dict[str, Any] = {
            "text": f"{prefix} *[{event_type}]* {message}",
            "attachments": [
                {
                    "color": colour,
                    "fallback": message,
                    "fields": [
                        {"title": "Event", "value": event_type, "short": True},
                        {"title": "Severity", "value": severity, "short": True},
                    ],
                }
            ],
        }

        target = channel or self._default_channel
        if target:
            payload["channel"] = target

        # Merge any caller-supplied extras (attachments, blocks, etc.).
        if extra:
            payload.update(extra)

        return payload

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> SlackNotifier:
        """Build an instance from ``FOUNDRY_SLACK_WEBHOOK_URL``.

        Raises ``ValueError`` if the env var is not set.
        """
        import os

        url = os.environ.get("FOUNDRY_SLACK_WEBHOOK_URL")
        if not url:
            raise ValueError(
                "FOUNDRY_SLACK_WEBHOOK_URL is not set — cannot build SlackNotifier"
            )
        return cls(url)


_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    "debug": ("", "#808080"),
    "info": (":information_source:", "#36a64f"),
    "warning": (":warning:", "#daa038"),
    "error": (":x:", "#d32f2f"),
    "critical": (":rotating_light:", "#b71c1c"),
}
