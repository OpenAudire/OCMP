"""Tests for the SMTP email sender."""

from email.message import EmailMessage as MimeMessage
from typing import Any, ClassVar

import pytest

from app.core.config import Settings
from app.services import email as email_module
from app.services.email import EmailMessage, SmtpEmailSender, get_email_sender

MESSAGE = EmailMessage(to="lecturer@example.org", subject="Hello", body="Body text\n")


class FakeSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL, recording what was done."""

    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.sent: list[MimeMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message: MimeMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTP)


def smtp_settings(test_settings: Settings, **overrides: Any) -> Settings:
    values = {
        "smtp_host": "smtp.example.org",
        "smtp_port": 587,
        "smtp_from_email": "noreply@example.org",
        "smtp_from_name": "OCMP Demo",
        **overrides,
    }
    return test_settings.model_copy(update=values)


def test_not_configured_means_no_sender(test_settings: Settings) -> None:
    assert get_email_sender(test_settings) is None
    with pytest.raises(ValueError, match="not configured"):
        SmtpEmailSender(test_settings)


def test_starttls_with_login(test_settings: Settings) -> None:
    settings = smtp_settings(test_settings, smtp_user="mailer", smtp_password="secret")
    sender = get_email_sender(settings)
    assert sender is not None

    sender.send(MESSAGE)

    (smtp,) = FakeSMTP.instances
    assert (smtp.host, smtp.port) == ("smtp.example.org", 587)
    assert smtp.calls == ["starttls", "login:mailer", "quit"]
    (sent,) = smtp.sent
    assert sent["To"] == "lecturer@example.org"
    assert sent["From"] == "OCMP Demo <noreply@example.org>"
    assert sent["Subject"] == "Hello"
    assert sent["Message-ID"].endswith("@example.org>")
    assert sent.get_content() == "Body text\n"


def test_plain_smtp_without_credentials(test_settings: Settings) -> None:
    SmtpEmailSender(smtp_settings(test_settings, smtp_tls=False)).send(MESSAGE)

    assert FakeSMTP.instances[0].calls == ["quit"]


def test_implicit_tls(test_settings: Settings) -> None:
    SmtpEmailSender(smtp_settings(test_settings, smtp_ssl=True, smtp_port=465)).send(MESSAGE)

    (smtp,) = FakeSMTP.instances
    assert "context" in smtp.kwargs
    assert "starttls" not in smtp.calls


def test_header_injection_is_rejected(test_settings: Settings) -> None:
    bad = EmailMessage(to="a@example.org\nBcc: victim@example.org", subject="x", body="x")

    with pytest.raises(ValueError):
        SmtpEmailSender(smtp_settings(test_settings)).send(bad)
