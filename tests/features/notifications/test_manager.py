"""Unit tests for NotificationManager — routing, filtering, error handling."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from foundry.features.notifications.manager import NotificationManager


@pytest.fixture
def manager() -> NotificationManager:
    return NotificationManager()


class TestNotificationManager:
    """NotificationManager — routed dispatch based on event type + severity."""

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def test_register_defaults_to_wildcard(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.return_value = True
        manager.register_channel(ch)

        assert manager.route_count == 1
        await manager.send("any_event", "any message", severity="info")
        ch.send.assert_awaited_once()

    async def test_register_with_event_filter(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.return_value = True
        manager.register_channel(ch, event_types="nightly")

        await manager.send("guardrail", "msg", severity="info")
        ch.send.assert_not_called()

        await manager.send("nightly", "msg", severity="info")
        ch.send.assert_awaited_once()

    async def test_register_with_severity_filter(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.return_value = True
        manager.register_channel(ch, severities=["error", "critical"])

        await manager.send("any", "msg", severity="info")
        ch.send.assert_not_called()

        await manager.send("any", "msg", severity="error")
        ch.send.assert_awaited_once()

    async def test_register_with_both_filters(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.return_value = True
        manager.register_channel(ch, event_types="nightly", severities="critical")

        await manager.send("nightly", "msg", severity="error")
        ch.send.assert_not_called()

        await manager.send("guardrail", "msg", severity="critical")
        ch.send.assert_not_called()

        await manager.send("nightly", "msg", severity="critical")
        ch.send.assert_awaited_once()

    async def test_register_multiple_channels(self, manager: NotificationManager) -> None:
        ch1 = AsyncMock()
        ch1.send.return_value = True
        ch2 = AsyncMock()
        ch2.send.return_value = True

        manager.register_channel(ch1, event_types="nightly")
        manager.register_channel(ch2, severities="critical")

        await manager.send("nightly", "msg", severity="info")
        ch1.send.assert_awaited_once()
        ch2.send.assert_not_called()

        await manager.send("guardrail", "msg", severity="critical")
        ch1.send.assert_awaited_once()  # still one call
        ch2.send.assert_awaited_once()

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def test_send_returns_success_count(self, manager: NotificationManager) -> None:
        ch_ok = AsyncMock()
        ch_ok.send.return_value = True
        ch_fail = AsyncMock()
        ch_fail.send.return_value = False

        manager.register_channel(ch_ok)
        manager.register_channel(ch_fail)

        count = await manager.send("test", "msg", severity="info")
        assert count == 1

    async def test_send_handles_channel_exception(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.side_effect = RuntimeError("boom")

        manager.register_channel(ch)

        # Exception should be caught and logged, not propagated
        count = await manager.send("test", "msg", severity="info")
        assert count == 0

    async def test_send_matches_case_insensitively(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        ch.send.return_value = True
        manager.register_channel(ch, event_types="Nightly", severities="ERROR")

        count = await manager.send("NIGHTLY", "msg", severity="ERROR")
        assert count == 1
        ch.send.assert_awaited_once_with(
            message="msg",
            severity="error",
            event_type="nightly",
        )

    async def test_send_with_no_routes(self, manager: NotificationManager) -> None:
        count = await manager.send("test", "msg", severity="info")
        assert count == 0

    def test_clear_removes_all_routes(self, manager: NotificationManager) -> None:
        ch = AsyncMock()
        manager.register_channel(ch)
        assert manager.route_count == 1
        manager.clear()
        assert manager.route_count == 0

    # ------------------------------------------------------------------
    # Use-case scenarios (nightly, guardrail, eval)
    # ------------------------------------------------------------------

    async def test_nightly_failure_routing(self, manager: NotificationManager) -> None:
        slack = AsyncMock()
        slack.send.return_value = True
        email = AsyncMock()
        email.send.return_value = True

        # Nightly failures → Slack (errors only)
        manager.register_channel(slack, event_types="nightly", severities="error")
        # Any critical issue → email
        manager.register_channel(email, severities="critical")

        await manager.send("nightly", "Build failed: tests broken", severity="error")
        slack.send.assert_awaited_once()
        email.send.assert_not_called()

        await manager.send("nightly", "Disk space low", severity="warning")
        slack.send.assert_awaited_once()  # no additional call
        email.send.assert_not_called()

    async def test_guardrail_breach_notification(self, manager: NotificationManager) -> None:
        slack = AsyncMock()
        slack.send.return_value = True
        email = AsyncMock()
        email.send.return_value = True

        # Guardrail breaches → Slack (any severity), email (critical only)
        manager.register_channel(slack, event_types="guardrail")
        manager.register_channel(email, event_types="guardrail", severities="critical")

        await manager.send("guardrail", "Prompt injection detected", severity="critical")
        slack.send.assert_awaited_once()
        email.send.assert_awaited_once()

        await manager.send("guardrail", "Mild policy hint", severity="info")
        assert slack.send.await_count == 2
        assert email.send.await_count == 1  # not called for info

    async def test_eval_regression_notification(self, manager: NotificationManager) -> None:
        webhook = AsyncMock()
        webhook.send.return_value = True

        # Eval regressions → custom webhook, warning+
        manager.register_channel(
            webhook,
            event_types="eval_regression",
            severities=["warning", "error", "critical"],
        )

        await manager.send("eval_regression", "Score dropped 15%", severity="warning")
        webhook.send.assert_awaited_once()

        await manager.send("eval_regression", "Minor drift", severity="info")
        webhook.send.assert_awaited_once()  # no additional call
