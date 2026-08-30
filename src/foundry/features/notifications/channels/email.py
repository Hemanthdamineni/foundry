"""Email notification channel via SMTP."""

from __future__ import annotations

import email.mime.text
import logging
import smtplib
import ssl
from typing import Sequence

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send alert emails via an SMTP server.

    Parameters
    ----------
    host:
        SMTP server hostname.
    port:
        SMTP server port (default 587 for STARTTLS).
    username:
        SMTP login username.
    password:
        SMTP login password.
    from_addr:
        ``From`` header address.
    to_addrs:
        Recipient address(es).  A single string is accepted for
        convenience.
    use_tls:
        If ``True`` (default) wrap the connection with STARTTLS.
        Set to ``False`` for plain-text SMTP (e.g. local dev relay).
    timeout_s:
        Socket timeout in seconds.
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        *,
        username: str | None = None,
        password: str | None = None,
        from_addr: str,
        to_addrs: str | Sequence[str],
        use_tls: bool = True,
        timeout_s: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._to_addrs = [to_addrs] if isinstance(to_addrs, str) else list(to_addrs)
        self._use_tls = use_tls
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
        """Send an email notification.

        Parameters
        ----------
        message:
            Plain-text body of the email.
        severity:
            ``"info"``, ``"warning"``, ``"error"``, or ``"critical"``.
            Prepended to the subject line.
        event_type:
            Label included in the subject line.

        Returns
        -------
        bool
            ``True`` if the message was accepted by the server.
        """
        subject = _build_subject(severity, event_type)
        msg = email.mime.text.MIMEText(message, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = self._from_addr
        msg["To"] = ", ".join(self._to_addrs)

        try:
            return await self._send_smtp(msg)
        except Exception as exc:
            logger.error("Failed to send email notification: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_smtp(self, msg: email.mime.text.MIMEText) -> bool:
        """Deliver *msg* via the configured SMTP server.

        Runs in a thread executor because ``smtplib`` is synchronous.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._send_smtp_sync,
            msg,
        )

    def _send_smtp_sync(self, msg: email.mime.text.MIMEText) -> bool:
        """Synchronous SMTP delivery (runs in a thread)."""
        context: ssl.SSLContext | None = None
        if self._use_tls:
            context = ssl.create_default_context()

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as server:
            if self._use_tls:
                server.starttls(context=context)
            if self._username and self._password:
                server.login(self._username, self._password)

            # ``sendmail`` returns a dict of failures — empty dict means all OK.
            failures = server.sendmail(
                self._from_addr,
                self._to_addrs,
                msg.as_string(),
            )
            return len(failures) == 0

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> EmailNotifier:
        """Build an instance from environment variables.

        Reads: ``FOUNDRY_SMTP_HOST``, ``FOUNDRY_SMTP_PORT``,
        ``FOUNDRY_SMTP_USERNAME``, ``FOUNDRY_SMTP_PASSWORD``,
        ``FOUNDRY_SMTP_FROM``, ``FOUNDRY_SMTP_TO``.

        Raises ``ValueError`` if ``FOUNDRY_SMTP_HOST`` or
        ``FOUNDRY_SMTP_FROM`` is missing.
        """
        import os

        host = os.environ.get("FOUNDRY_SMTP_HOST")
        if not host:
            raise ValueError("FOUNDRY_SMTP_HOST is not set")

        return cls(
            host=host,
            port=int(os.environ.get("FOUNDRY_SMTP_PORT", "587")),
            username=os.environ.get("FOUNDRY_SMTP_USERNAME"),
            password=os.environ.get("FOUNDRY_SMTP_PASSWORD"),
            from_addr=os.environ["FOUNDRY_SMTP_FROM"],
            to_addrs=os.environ.get("FOUNDRY_SMTP_TO", "").split(",")
            if os.environ.get("FOUNDRY_SMTP_TO")
            else [],
        )


def _build_subject(severity: str, event_type: str) -> str:
    prefix = _SUBJECT_PREFIX.get(severity.lower(), "")
    return f"{prefix}[{event_type}] Foundry Notification"


_SUBJECT_PREFIX: dict[str, str] = {
    "info": "",
    "warning": "[WARN] ",
    "error": "[ERR] ",
    "critical": "[CRIT] ",
}
