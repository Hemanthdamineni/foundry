"""Unit tests for GenericWebhookNotifier — mocked HTTP."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from foundry.features.notifications.channels.webhook import GenericWebhookNotifier


@pytest.fixture
def notifier() -> GenericWebhookNotifier:
    return GenericWebhookNotifier(
        url="https://hooks.example.com/alert",
        headers={"X-Token": "abc123"},
    )


class TestGenericWebhookNotifier:
    """GenericWebhookNotifier — HTTP mocking with patched httpx.AsyncClient."""

    @patch("httpx.AsyncClient")
    async def test_send_success(self, mock_client_cls: AsyncMock, notifier: GenericWebhookNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        result = await notifier.send("System OK", severity="info", event_type="heartbeat")

        assert result is True
        mock_client.post.assert_awaited_once()

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["headers"]["X-Token"] == "abc123"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

        import json
        payload = json.loads(call_kwargs["content"])
        assert payload["event_type"] == "heartbeat"
        assert payload["severity"] == "info"
        assert payload["message"] == "System OK"
        assert payload["timestamp"].endswith("Z")

    @patch("httpx.AsyncClient")
    async def test_send_http_failure(self, mock_client_cls: AsyncMock, notifier: GenericWebhookNotifier) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_client.post.return_value = mock_resp

        result = await notifier.send("fail", severity="error", event_type="test")

        assert result is False

    @patch("httpx.AsyncClient")
    async def test_send_network_error(self, mock_client_cls: AsyncMock, notifier: GenericWebhookNotifier) -> None:
        from httpx import RequestError

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = RequestError("timeout")

        result = await notifier.send("timeout", severity="warning", event_type="test")

        assert result is False

    @patch("httpx.AsyncClient")
    async def test_payload_template(self, mock_client_cls: AsyncMock) -> None:
        templated = GenericWebhookNotifier(
            url="https://hooks.example.com/notify",
            payload_template="[M: {message}] [S: {severity}] [E: {event_type}]",
            content_type="text/plain",
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        ok = await templated.send("hello", severity="info", event_type="test")
        assert ok is True

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["content"] == "[M: hello] [S: info] [E: test]"
        assert call_kwargs["headers"]["Content-Type"] == "text/plain"

    @patch("httpx.AsyncClient")
    async def test_custom_payload_builder(self, mock_client_cls: AsyncMock) -> None:
        custom = GenericWebhookNotifier(
            url="https://hooks.example.com/custom",
            payload_builder=lambda msg, sev, evt: {"msg": msg, "level": sev.upper()},
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_resp = AsyncMock()
        mock_resp.is_success = True
        mock_client.post.return_value = mock_resp

        ok = await custom.send("alert", severity="critical", event_type="nightly")
        assert ok is True

        import json
        payload = json.loads(mock_client.post.call_args[1]["content"])
        assert payload == {"msg": "alert", "level": "CRITICAL"}
