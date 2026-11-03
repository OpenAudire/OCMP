"""Tests for the embeddings provider (ADR 044): the request it sends and what it refuses."""

import json

import httpx
import pytest

from app.ai.embeddings import (
    BATCH_SIZE,
    DIMENSIONS,
    MODEL_KEY,
    LocalEmbeddingProvider,
    NullEmbeddingProvider,
    get_embedding_provider,
    prepared_text,
    text_hash,
)
from app.ai.errors import ProviderError
from app.core.config import Settings

URL = "http://embeddings:8080"


def vector(seed: float = 0.1) -> list[float]:
    return [seed] * DIMENSIONS


def provider_with(
    handler: httpx.MockTransport, url: str = URL
) -> tuple[LocalEmbeddingProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler.handler(request)  # type: ignore[attr-defined,no-any-return]

    return LocalEmbeddingProvider(url, httpx.MockTransport(record)), seen


def echo_vectors(request: httpx.Request) -> httpx.Response:
    inputs = json.loads(request.content)["inputs"]
    return httpx.Response(200, json=[vector() for _ in inputs])


class TestRequest:
    async def test_sends_the_prefixed_text_to_embed(self) -> None:
        provider, seen = provider_with(httpx.MockTransport(echo_vectors))

        vectors = await provider.embed(["  Describe   the\nheart. "])

        assert len(vectors) == 1 and len(vectors[0]) == DIMENSIONS
        assert str(seen[0].url) == f"{URL}/embed"
        body = json.loads(seen[0].content)
        assert body["inputs"] == ["query: Describe the heart."]
        assert body["truncate"] is True
        assert body["normalize"] is True

    async def test_sends_no_credentials_and_follows_no_redirects(self) -> None:
        provider, seen = provider_with(httpx.MockTransport(echo_vectors))

        await provider.embed(["x"])

        assert "authorization" not in seen[0].headers
        redirecting, _ = provider_with(
            httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://x/"}))
        )
        with pytest.raises(ProviderError, match="status 302"):
            await redirecting.embed(["x"])

    async def test_splits_long_lists_into_server_sized_batches(self) -> None:
        provider, seen = provider_with(httpx.MockTransport(echo_vectors))
        texts = [f"Objective {n}" for n in range(BATCH_SIZE * 2 + 6)]

        vectors = await provider.embed(texts)

        assert len(vectors) == len(texts)
        assert [len(json.loads(r.content)["inputs"]) for r in seen] == [BATCH_SIZE, BATCH_SIZE, 6]

    async def test_nothing_is_sent_for_an_empty_list(self) -> None:
        provider, seen = provider_with(httpx.MockTransport(echo_vectors))

        assert await provider.embed([]) == []
        assert seen == []


class TestAnswers:
    @pytest.mark.parametrize(
        "answer",
        [
            [[0.1] * 10],  # wrong dimension
            [vector(), vector()],  # wrong number of vectors
            {"error": "no"},  # not a list
            [["a"] * DIMENSIONS],  # not numbers
            [[True] * DIMENSIONS],  # booleans are not numbers
        ],
    )
    async def test_bad_answers_are_refused(self, answer: object) -> None:
        provider, _ = provider_with(httpx.MockTransport(lambda r: httpx.Response(200, json=answer)))

        with pytest.raises(ProviderError):
            await provider.embed(["one text"])

    async def test_an_answer_that_is_not_json_is_refused(self) -> None:
        provider, _ = provider_with(
            httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>"))
        )

        with pytest.raises(ProviderError, match="not JSON"):
            await provider.embed(["x"])

    async def test_an_error_status_is_reported_with_its_code(self) -> None:
        provider, _ = provider_with(
            httpx.MockTransport(lambda r: httpx.Response(413, json={"error": "too large"}))
        )

        with pytest.raises(ProviderError, match="status 413") as raised:
            await provider.embed(["x"])

        assert raised.value.status_code == 413

    async def test_an_unreachable_server_is_a_provider_error(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        provider, _ = provider_with(httpx.MockTransport(refuse))

        with pytest.raises(ProviderError, match="could not be reached"):
            await provider.embed(["x"])


class TestAddress:
    @pytest.mark.parametrize(
        "url",
        [
            "http://embeddings:8080",
            "http://127.0.0.1:8080",
            "http://10.1.2.3:8080",
            "http://tei.lan",
        ],
    )
    def test_local_addresses_are_accepted(self, url: str) -> None:
        assert LocalEmbeddingProvider(url)

    @pytest.mark.parametrize(
        "url",
        ["https://embeddings.example.com", "http://8.8.8.8:8080", "ftp://embeddings", "not a url"],
    )
    def test_other_addresses_are_refused(self, url: str) -> None:
        with pytest.raises(ProviderError, match="private network"):
            LocalEmbeddingProvider(url)


class TestReady:
    async def test_a_healthy_server_is_ready(self) -> None:
        provider, seen = provider_with(httpx.MockTransport(lambda r: httpx.Response(200)))

        assert await provider.is_ready() is True
        assert str(seen[0].url) == f"{URL}/health"

    async def test_an_unhealthy_or_missing_server_is_not(self) -> None:
        unhealthy, _ = provider_with(httpx.MockTransport(lambda r: httpx.Response(503)))

        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        missing, _ = provider_with(httpx.MockTransport(refuse))

        assert await unhealthy.is_ready() is False
        assert await missing.is_ready() is False


class TestChoice:
    def test_embeddings_are_off_by_default(self, test_settings: Settings) -> None:
        assert isinstance(get_embedding_provider(test_settings), NullEmbeddingProvider)

    async def test_the_null_provider_has_no_network_code(self) -> None:
        with pytest.raises(ProviderError, match="not turned on"):
            await NullEmbeddingProvider().embed(["x"])

    def test_turned_on_the_local_server_is_used(self, test_settings: Settings) -> None:
        settings = test_settings.model_copy(update={"embeddings_local": True})

        assert isinstance(get_embedding_provider(settings), LocalEmbeddingProvider)

    def test_a_public_address_is_refused_even_when_turned_on(self, test_settings: Settings) -> None:
        settings = test_settings.model_copy(
            update={"embeddings_local": True, "embeddings_local_url": "https://api.example.com"}
        )

        with pytest.raises(ProviderError):
            get_embedding_provider(settings)


class TestTextHash:
    def test_the_prefix_is_part_of_what_is_sent_and_hashed(self) -> None:
        assert prepared_text("Name the bones.") == "query: Name the bones."
        assert text_hash("Name the bones.") != text_hash("Name the bone.")

    def test_spacing_does_not_change_the_hash(self) -> None:
        assert text_hash("Name   the\nbones. ") == text_hash("Name the bones.")

    def test_the_model_key_names_model_prefix_and_recipe(self) -> None:
        assert MODEL_KEY == "intfloat/multilingual-e5-small|query:|v1"
