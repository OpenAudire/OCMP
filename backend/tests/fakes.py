"""Test doubles shared across tests."""

from app.services.email import EmailMessage


class FakeEmailSender:
    """Collects emails instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
