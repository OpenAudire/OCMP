"""Tests for finding framework items by meaning, with a words-only fallback (ADR 044)."""

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY
from app.ai.errors import ProviderError
from app.core.config import Settings
from app.models import FrameworkItem
from app.models.embedding import EmbeddedType, Embedding
from app.models.framework import FrameworkStatus
from app.services.retrieval import (
    EmbeddingsState,
    Mode,
    Notice,
    embeddings_state,
    keyword_query,
    similar_framework_items,
)
from tests.factories import FrameworkFactory
from tests.fakes import FakeEmbeddingProvider, angled


class AtAngle:
    """A provider that answers every text with the vector at one angle."""

    name = "angled"

    def __init__(self, degrees: float) -> None:
        self.degrees = degrees

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [angled(self.degrees) for _ in texts]


@pytest.fixture
def on(test_settings: Settings) -> Settings:
    return test_settings.model_copy(update={"embeddings_local": True})


class TestKeywordQuery:
    def test_distinct_words_of_four_letters_or_more_joined_with_or(self) -> None:
        assert keyword_query("Explain the Communication skills; explain skills!") == (
            "explain | communication | skills"
        )

    def test_stop_words_numbers_and_short_words_are_left_out(self) -> None:
        assert keyword_query("The 2026 use of die en van TB") is None

    def test_afrikaans_and_isixhosa_words_are_kept_as_they_are(self) -> None:
        assert keyword_query("Beskryf gemeenskapsgesondheidswerkers") == (
            "beskryf | gemeenskapsgesondheidswerkers"
        )
        assert keyword_query("Chaza indima yabasebenzi bezempilo") == (
            "chaza | indima | yabasebenzi | bezempilo"
        )

    def test_syntax_characters_cannot_reach_the_query(self) -> None:
        assert keyword_query("Ignore'); DROP TABLE x; -- & | ! (clinical)") == (
            "ignore | drop | table | clinical"
        )

    def test_at_most_thirty_words(self) -> None:
        text = " ".join(f"word{n:02d}" for n in range(50))

        assert keyword_query(text).count("|") == 29  # type: ignore[union-attr]


class TestState:
    async def test_off_when_not_turned_on(self, test_settings: Settings) -> None:
        assert await embeddings_state(test_settings) is EmbeddingsState.OFF

    async def test_ready_when_the_server_answers_its_health_check(self, on: Settings) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(200))

        assert await embeddings_state(on, transport=transport) is EmbeddingsState.READY

    async def test_unreachable_when_it_does_not(self, on: Settings) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(503))

        assert await embeddings_state(on, transport=transport) is EmbeddingsState.UNREACHABLE

    async def test_an_address_that_is_not_local_counts_as_unreachable(
        self, test_settings: Settings
    ) -> None:
        settings = test_settings.model_copy(
            update={"embeddings_local": True, "embeddings_local_url": "https://api.example.com"}
        )

        assert await embeddings_state(settings) is EmbeddingsState.UNREACHABLE

    async def test_the_answer_is_remembered_for_a_short_while(
        self, on: Settings, redis_client: FakeAsyncRedis
    ) -> None:
        calls: list[int] = []

        def health(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200)

        transport = httpx.MockTransport(health)

        first = await embeddings_state(on, redis_client, transport)
        second = await embeddings_state(on, redis_client, transport)

        assert first is second is EmbeddingsState.READY
        assert len(calls) == 1
        assert 0 < await redis_client.ttl("embeddings:ready") <= 30


async def make_items(db: AsyncSession) -> tuple[FrameworkItem, FrameworkItem, FrameworkItem]:
    framework = FrameworkFactory(status=FrameworkStatus.ACTIVE)
    other = FrameworkFactory(status=FrameworkStatus.ACTIVE)
    db.add_all([framework, other])
    await db.flush()
    communication = FrameworkItem(
        framework_id=framework.id,
        code="C1",
        title="Communication with patients",
        description="Explains clearly.",
    )
    hygiene = FrameworkItem(framework_id=framework.id, code="C2", title="Hand hygiene")
    elsewhere = FrameworkItem(framework_id=other.id, code="X1", title="Communication skills")
    db.add_all([communication, hygiene, elsewhere])
    await db.flush()
    return communication, hygiene, elsewhere


async def ready(redis: FakeAsyncRedis, is_ready: bool = True) -> None:
    await redis.set("embeddings:ready", "1" if is_ready else "0", ex=30)


class TestSimilarFrameworkItems:
    async def test_by_meaning_best_first_and_only_in_the_chosen_frameworks(
        self, db_session: AsyncSession, on: Settings, redis_client: FakeAsyncRedis
    ) -> None:
        communication, hygiene, elsewhere = await make_items(db_session)
        for item, degrees in ((communication, 5), (hygiene, 40), (elsewhere, 0)):
            db_session.add(
                Embedding(
                    entity_type=EmbeddedType.FRAMEWORK_ITEM,
                    entity_id=item.id,
                    model_key=MODEL_KEY,
                    text_hash="x",
                    vector=angled(degrees),
                )
            )
        await db_session.flush()
        await ready(redis_client)

        found = await similar_framework_items(
            db_session,
            on,
            "Talk to a patient clearly.",
            framework_ids=[communication.framework_id],
            provider=AtAngle(0),
            redis=redis_client,
        )

        assert (found.mode, found.notice) == (Mode.MEANING, None)
        assert [hit.item_id for hit in found.hits] == [communication.id, hygiene.id]
        assert found.hits[0].score == pytest.approx(0.9962, abs=1e-3)
        assert found.hits[0].score > found.hits[1].score

    async def test_off_falls_back_to_words_with_a_notice_not_an_error(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        communication, _, _ = await make_items(db_session)

        found = await similar_framework_items(
            db_session,
            test_settings,
            "Explain communication with a patient.",
            framework_ids=[communication.framework_id],
        )

        assert (found.mode, found.notice) == (Mode.KEYWORD, Notice.EMBEDDINGS_OFF)
        assert [hit.item_id for hit in found.hits] == [communication.id]
        assert found.hits[0].score == 1.0

    async def test_an_unreachable_server_falls_back_with_its_own_notice(
        self, db_session: AsyncSession, on: Settings, redis_client: FakeAsyncRedis
    ) -> None:
        communication, _, _ = await make_items(db_session)
        await ready(redis_client, is_ready=False)

        found = await similar_framework_items(
            db_session,
            on,
            "Communication with patients",
            framework_ids=[communication.framework_id],
            redis=redis_client,
        )

        assert (found.mode, found.notice) == (Mode.KEYWORD, Notice.EMBEDDINGS_UNREACHABLE)
        assert [hit.item_id for hit in found.hits] == [communication.id]

    async def test_a_server_that_fails_during_the_call_falls_back_too(
        self, db_session: AsyncSession, on: Settings, redis_client: FakeAsyncRedis
    ) -> None:
        communication, _, _ = await make_items(db_session)
        await ready(redis_client)

        found = await similar_framework_items(
            db_session,
            on,
            "Communication with patients",
            framework_ids=[communication.framework_id],
            provider=FakeEmbeddingProvider(fail=True),
            redis=redis_client,
        )

        assert (found.mode, found.notice) == (Mode.KEYWORD, Notice.EMBEDDINGS_UNREACHABLE)
        assert found.hits

    async def test_nothing_embedded_yet_falls_back_with_that_notice(
        self, db_session: AsyncSession, on: Settings, redis_client: FakeAsyncRedis
    ) -> None:
        communication, _, _ = await make_items(db_session)
        await ready(redis_client)

        found = await similar_framework_items(
            db_session,
            on,
            "Communication with patients",
            framework_ids=[communication.framework_id],
            provider=AtAngle(0),
            redis=redis_client,
        )

        assert (found.mode, found.notice) == (Mode.KEYWORD, Notice.NOT_EMBEDDED_YET)
        assert [hit.item_id for hit in found.hits] == [communication.id]

    async def test_words_that_match_nothing_give_an_empty_answer_not_an_error(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        communication, _, _ = await make_items(db_session)

        found = await similar_framework_items(
            db_session,
            test_settings,
            "Unrelated astronomy wording",
            framework_ids=[communication.framework_id],
        )

        assert found.hits == []
        assert found.notice is Notice.EMBEDDINGS_OFF

    async def test_no_frameworks_means_no_hits(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        found = await similar_framework_items(
            db_session, test_settings, "Communication", framework_ids=[]
        )

        assert found.hits == []


def test_the_provider_error_type_is_what_the_fallback_catches() -> None:
    assert issubclass(ProviderError, Exception)
