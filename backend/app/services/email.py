"""Outgoing email."""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class EmailMessage:
    """A plain-text email to one recipient."""

    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    """Something that can deliver an email (blocking)."""

    def send(self, message: EmailMessage) -> None: ...


class SmtpEmailSender:
    """Delivers email through the SMTP server in the settings."""

    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_configured:
            raise ValueError("SMTP is not configured (SMTP_HOST and SMTP_FROM_EMAIL).")
        self.settings = settings

    def _build(self, message: EmailMessage) -> MimeMessage:
        # email.message handles header encoding and rejects header injection.
        mime = MimeMessage()
        sender = self.settings.smtp_from_email
        assert sender is not None
        mime["From"] = formataddr((self.settings.smtp_from_name, sender))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
        mime.set_content(message.body)
        return mime

    def send(self, message: EmailMessage) -> None:
        s = self.settings
        assert s.smtp_host is not None
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_ssl:
            smtp = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=context
            )
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        with smtp:
            if not s.smtp_ssl and s.smtp_tls:
                smtp.starttls(context=context)
            if s.smtp_user and s.smtp_password:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(self._build(message))


def get_email_sender(settings: Settings) -> EmailSender | None:
    """The configured sender, or None when SMTP is not set up."""
    return SmtpEmailSender(settings) if settings.smtp_configured else None
