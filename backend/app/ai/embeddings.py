"""Embedding providers (ADR 044): ``embed(texts)`` for the local embeddings server.

Only a server on this machine or a private network is supported in Phase 1. Curriculum text
is sent to it, never personal data by design, but the text still never leaves the
installation. A future cloud embedding provider must go through the privacy guard first.

Documentation read on 2026-11-03: Hugging Face Text Embeddings Inference 1.9
(``huggingface.co/docs/text-embeddings-inference``: ``quick_tour``, ``cli_arguments``) and the
model card of ``intfloat/multilingual-e5-small``. The request and response shapes were also
checked against a running ``cpu-1.9`` container (see ADR 044).
"""

import hashlib
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.ai.errors import ProviderError
from app.ai.locality import is_local_host
from app.ai.providers.base import client_for, post_json
from app.core.config import Settings

MODEL_NAME = "intfloat/multilingual-e5-small"
DIMENSIONS = 384
# E5 models are trained with a prefix on every input; "query: " is the one the model card
# gives for symmetric tasks (similarity, paraphrase retrieval). Changing it changes the key.
PROMPT_PREFIX = "query: "
# Bump when the way vectors are made changes (prefix, normalisation, truncation).
RECIPE_VERSION = 1
MODEL_KEY = f"{MODEL_NAME}|{PROMPT_PREFIX.strip()}|v{RECIPE_VERSION}"
# TEI refuses more inputs than this in one request (``--max-client-batch-size``, default 32).
BATCH_SIZE = 32


def prepared_text(text: str) -> str:
    """Exactly what is sent to the model for ``text``: the prefix, then the wording."""
    return PROMPT_PREFIX + " ".join(text.split())


def text_hash(text: str) -> str:
    """SHA-256 of the prepared text. Re-embedding happens only when this changes."""
    return hashlib.sha256(prepared_text(text).encode("utf-8")).hexdigest()


class EmbeddingProvider(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector of ``DIMENSIONS`` numbers per text, in order."""
        ...


class NullEmbeddingProvider:
    """Embeddings are off. It has no network code at all."""

    name = "null"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise ProviderError("Embeddings are not turned on.")


class LocalEmbeddingProvider:
    """The ``embeddings`` compose service: Text Embeddings Inference serving e5-small."""

    name = "local"

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        url = httpx.URL(base_url)
        if url.scheme not in ("http", "https") or not url.host or not is_local_host(url.host):
            raise ProviderError(
                "The embeddings server must be on this server or a private network."
            )
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with client_for(self._transport) as client:
            for start in range(0, len(texts), BATCH_SIZE):
                batch = [prepared_text(t) for t in texts[start : start + BATCH_SIZE]]
                response = await post_json(
                    client,
                    f"{self._base_url}/embed",
                    headers={"content-type": "application/json"},
                    body={"inputs": batch, "truncate": True, "normalize": True},
                    api_key=None,
                )
                data = _vectors(response, expected=len(batch))
                vectors.extend(data)
        return vectors

    async def is_ready(self) -> bool:
        """Whether the server answers its health check."""
        try:
            async with client_for(self._transport) as client:
                response = await client.get(f"{self._base_url}/health", timeout=3.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200


def _vectors(response: httpx.Response, *, expected: int) -> list[list[float]]:
    try:
        data = response.json()
    except ValueError:
        raise ProviderError("The embeddings server's answer was not JSON.") from None
    if not isinstance(data, list) or len(data) != expected:
        raise ProviderError("The embeddings server returned an unexpected number of vectors.")
    vectors: list[list[float]] = []
    for item in data:
        if (
            not isinstance(item, list)
            or len(item) != DIMENSIONS
            or not all(isinstance(x, int | float) and not isinstance(x, bool) for x in item)
        ):
            raise ProviderError(
                f"The embeddings server returned a vector that is not {DIMENSIONS} numbers."
            )
        vectors.append([float(x) for x in item])
    return vectors


def embeddings_enabled(settings: Settings) -> bool:
    return settings.embeddings_local


def get_embedding_provider(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> EmbeddingProvider:
    """The provider for these settings; the Null provider while embeddings are off."""
    if not settings.embeddings_local:
        return NullEmbeddingProvider()
    return LocalEmbeddingProvider(settings.embeddings_local_url, transport)


__all__ = [
    "BATCH_SIZE",
    "DIMENSIONS",
    "MODEL_KEY",
    "MODEL_NAME",
    "PROMPT_PREFIX",
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
    "NullEmbeddingProvider",
    "embeddings_enabled",
    "get_embedding_provider",
    "prepared_text",
    "text_hash",
]
