"""Unit tests for EmailNotifier — mocked SMTP."""
from __future__ import annotations

import email.policy
from unittest.mock import MagicMock, patch

import pytest

from foundry.features.notifications.channels.email import EmailNotifier


@pytest.fixture
def notifier() -> EmailNotifier:
    return EmailNotifier(
        host="smtp.example.com",
        port=587,
        username="bot@example.com",
        password="sekret",
        from_addr="bot@example.com",
        to_addrs="ops@example.com",
    )


class TestEmailNotifier:
    """EmailNotifier — SMTP is stubbed via ``run_in_executor``."""

    @patch("smtplib.SMTP")
    async def test_send_success(self, mock_smtp_cls: MagicMock, notifier: EmailNotifier) -> None:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        mock_server.sendmail.return_value = {}  # empty = all delivered

        # The notifier runs SMTP in a thread; we patch run_in_executor to
        # call the sync method directly.
        result = await notifier.send("Test message", severity="info", event_type="nightly")

        assert result is True
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "bot@example.com"
        assert args[1] == ["ops@example.com"]

        # Parse the MIME message to verify content (body may be base64).
        msg = email.message_from_string(args[2], policy=email.policy.compat32)
        assert msg.get_payload(decode=True).decode("utf-8") == "Test message"

    @patch("smtplib.SMTP")
    async def test_send_failure(self, mock_smtp_cls: MagicMock, notifier: EmailNotifier) -> None:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        # non-empty dict = some recipients rejected
        mock_server.sendmail.return_value = {"ops@example.com": (550, "mailbox unavailable")}

        result = await notifier.send("Test", severity="error")

        assert result is False

    @patch("smtplib.SMTP")
    async def test_credentials_flow(self, mock_smtp_cls: MagicMock, notifier: EmailNotifier) -> None:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        mock_server.sendmail.return_value = {}

        await notifier.send("hello", severity="warning", event_type="guardrail")

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("bot@example.com", "sekret")

    @patch("smtplib.SMTP")
    async def test_subject_format(self, mock_smtp_cls: MagicMock, notifier: EmailNotifier) -> None:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        mock_server.sendmail.return_value = {}

        await notifier.send("msg", severity="critical", event_type="eval_regression")

        msg_str = mock_server.sendmail.call_args[0][2]
        msg = email.message_from_string(msg_str, policy=email.policy.compat32)
        assert msg["Subject"] == "[CRIT] [eval_regression] Foundry Notification"

    async def test_no_auth_when_credentials_omitted(self) -> None:
        anon = EmailNotifier(
            host="localhost",
            port=25,
            username=None,
            password=None,
            from_addr="test@local",
            to_addrs="local@local",
            use_tls=False,
        )

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            mock_server.sendmail.return_value = {}

            ok = await anon.send("no auth", severity="info", event_type="test")
            assert ok is True
            mock_server.login.assert_not_called()
            mock_server.starttls.assert_not_called()

    async def test_multiple_recipients(self) -> None:
        multi = EmailNotifier(
            host="smtp.example.com",
            port=587,
            username="u",
            password="p",
            from_addr="from@example.com",
            to_addrs=["a@example.com", "b@example.com"],
        )
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server
            mock_server.sendmail.return_value = {}

            ok = await multi.send("multi", severity="info", event_type="test")
            assert ok is True
            args = mock_server.sendmail.call_args[0]
            assert args[1] == ["a@example.com", "b@example.com"]

    async def test_from_env_missing_host(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="FOUNDRY_SMTP_HOST"):
                EmailNotifier.from_env()
