"""Unit tests for SlackNotifier — mocked HTTP."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from foundry.features.notifications.channels.slack import SlackNotifier


@pytest.fixture
def notifier() -> SlackNotifier:
    return SlackNotifier(
        webhook_url="https://hooks.slack.com/services/T00/B00/fake",
        default_channel="#alerts",
    )


class TestSlackNotifier:
    """SlackNotifier — HTTP mocking with patched httpx.AsyncClient."""

    @patch("httpx.AsyncClient")
    async def test_send_success(self, mock_client_cls: AsyncMock, notifier: SlackNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        result = await notifier.send("Everything is fine", severity="info", event_type="nightly")

        assert result is True
        mock_client.post.assert_awaited_once()

        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["channel"] == "#alerts"
        assert payload["attachments"][0]["fields"][0]["value"] == "nightly"

    @patch("httpx.AsyncClient")
    async def test_send_http_failure(self, mock_client_cls: AsyncMock, notifier: SlackNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        mock_resp = AsyncMock()
        mock_resp.is_success = False
        mock_resp.status_code = 403
        mock_resp.text = "invalid_token"
        mock_client.post.return_value = mock_resp

        result = await notifier.send("Alert", severity="error")

        assert result is False

    @patch("httpx.AsyncClient")
    async def test_send_network_error(self, mock_client_cls: AsyncMock, notifier: SlackNotifier) -> None:
        from httpx import RequestError

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        mock_client.post.side_effect = RequestError("connection refused")

        result = await notifier.send("Down", severity="critical")

        assert result is False

    @patch("httpx.AsyncClient")
    async def test_severity_colours(self, mock_client_cls: AsyncMock, notifier: SlackNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        severity_colour = [
            ("debug", "#808080"),
            ("info", "#36a64f"),
            ("warning", "#daa038"),
            ("error", "#d32f2f"),
            ("critical", "#b71c1c"),
        ]
        for sev, expected_colour in severity_colour:
            mock_client.post.reset_mock()
            mock_client.post.return_value = mock_resp

            await notifier.send("test", severity=sev)
            payload = mock_client.post.call_args[1]["json"]
            assert payload["attachments"][0]["color"] == expected_colour, f"mismatch for {sev}"

    @patch("httpx.AsyncClient")
    async def test_channel_override(self, mock_client_cls: AsyncMock, notifier: SlackNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        await notifier.send("test", channel="#incidents")
        payload = mock_client.post.call_args[1]["json"]
        assert payload["channel"] == "#incidents"

    async def test_from_env_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="FOUNDRY_SLACK_WEBHOOK_URL"):
                SlackNotifier.from_env()
