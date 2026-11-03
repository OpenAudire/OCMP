"""Test doubles shared across tests."""

import hashlib
import math
from collections.abc import Sequence

from app.ai.embeddings import DIMENSIONS
from app.ai.errors import ProviderError
from app.services.email import EmailMessage


class FakeEmailSender:
    """Collects emails instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FakeEmbeddingProvider:
    """An embedding provider for tests: one fixed vector per text, no network."""

    name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise ProviderError("The embeddings server could not be reached (test).")
        return [one_hot(text) for text in texts]

    @property
    def texts_sent(self) -> list[str]:
        return [text for call in self.calls for text in call]


def one_hot(text: str) -> list[float]:
    """A unit vector whose one non-zero place comes from the text (equal texts, equal vectors)."""
    place = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % DIMENSIONS
    vector = [0.0] * DIMENSIONS
    vector[place] = 1.0
    return vector


def angled(degrees: float) -> list[float]:
    """A unit vector at an angle to ``angled(0)``: the cosine of the two is ``cos(degrees)``."""
    radians = math.radians(degrees)
    vector = [0.0] * DIMENSIONS
    vector[0], vector[1] = math.cos(radians), math.sin(radians)
    return vector
