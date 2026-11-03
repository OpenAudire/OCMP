"""Tests for choosing the framework items an AI run asks about (ADR 045)."""

import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY
from app.core.config import Settings
from app.models import FrameworkItem, MappingLink, Objective
from app.models.embedding import EmbeddedType, Embedding
from app.models.framework import CrossRefType, FrameworkCrossRef
from app.models.mapping import MappingSource, MappingStatus
from app.services.mapping_shortlist import shortlist
from app.services.retrieval import Notice
from tests.fakes import angled
from tests.mapping_helpers import Library, make_library
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture


class AtAngle:
    name = "angled"

    def __init__(self, degrees: float) -> None:
        self.degrees = degrees

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [angled(self.degrees) for _ in texts]


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


@pytest.fixture
def on(test_settings: Settings) -> Settings:
    return test_settings.model_copy(update={"embeddings_local": True})


async def vector(db: AsyncSession, kind: EmbeddedType, entity: object, degrees: float) -> None:
    db.add(
        Embedding(
            entity_type=kind,
            entity_id=entity.id,  # type: ignore[attr-defined]
            model_key=MODEL_KEY,
            text_hash="x",
            vector=angled(degrees),
        )
    )
    await db.flush()


async def link(
    db: AsyncSession, objective: Objective, item: FrameworkItem, status: MappingStatus
) -> MappingLink:
    row = MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=MappingSource.HUMAN,
        status=status,
        coverage=3,
    )
    if status is MappingStatus.ACCEPTED:
        row.accept_method = "individual"  # type: ignore[assignment]
    db.add(row)
    await db.flush()
    return row


async def ready(redis: FakeAsyncRedis) -> None:
    await redis.set("embeddings:ready", "1", ex=30)


class TestWordsOnly:
    async def test_embeddings_off_gives_a_keyword_list_with_the_reason(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        found = await shortlist(
            db_session, test_settings, world.lecture_objective, library.framework.id
        )

        assert found.mode == "keyword"
        assert found.notice is Notice.EMBEDDINGS_OFF
        assert [c.item.code for c in found.candidates] == ["HRT1"]
        assert found.candidates[0].signals == ("words",)

    async def test_an_objective_with_no_shared_words_has_no_candidates(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        found = await shortlist(
            db_session, test_settings, world.anatomy_outcome, library.framework.id
        )

        assert found.candidates == []


class TestHybrid:
    async def test_meaning_words_and_precedent_are_combined_best_first(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        # The query vector is at 0 degrees. Heart: close in meaning and shares words.
        # Communication: close in meaning only. Hygiene: far away, but accepted for a similar
        # objective (precedent). Ethics: far away and nothing else.
        for item, degrees in (
            (library.heart, 4),
            (library.communication, 8),
            (library.hygiene, 70),
            (library.ethics, 80),
        ):
            await vector(db_session, EmbeddedType.FRAMEWORK_ITEM, item, degrees)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.lecture_objective, 0)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.published_outcome, 3)
        await link(db_session, world.published_outcome, library.hygiene, MappingStatus.ACCEPTED)
        await ready(redis_client)

        found = await shortlist(
            db_session,
            on,
            world.lecture_objective,
            library.framework.id,
            provider=AtAngle(0),
            redis=redis_client,
        )

        assert found.mode == "meaning" and found.notice is None
        codes = [c.item.code for c in found.candidates]
        assert codes[0] == "HRT1"
        assert set(found.candidates[0].signals) == {"meaning", "words"}
        by_code = {c.item.code: c for c in found.candidates}
        assert "precedent" in by_code["HYG1"].signals
        assert codes.index("COM1") < codes.index("HYG1") or by_code["HYG1"].score > 0
        assert "ETH1" not in codes
        scores = [c.score for c in found.candidates]
        assert scores == sorted(scores, reverse=True)

    async def test_items_already_linked_in_any_state_are_left_out(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        for item in (library.heart, library.communication):
            await vector(db_session, EmbeddedType.FRAMEWORK_ITEM, item, 5)
        await link(db_session, world.lecture_objective, library.heart, MappingStatus.REJECTED)
        await ready(redis_client)

        found = await shortlist(
            db_session,
            on,
            world.lecture_objective,
            library.framework.id,
            provider=AtAngle(0),
            redis=redis_client,
        )

        assert [c.item.code for c in found.candidates] == ["COM1"]

    async def test_cross_references_of_the_best_items_come_along(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        await vector(db_session, EmbeddedType.FRAMEWORK_ITEM, library.heart, 3)
        db_session.add(
            FrameworkCrossRef(
                from_item_id=library.ethics.id,
                to_item_id=library.heart.id,
                type=CrossRefType.RELATED,
            )
        )
        await db_session.flush()
        await ready(redis_client)

        found = await shortlist(
            db_session,
            on,
            world.lecture_objective,
            library.framework.id,
            provider=AtAngle(0),
            redis=redis_client,
        )

        by_code = {c.item.code: c for c in found.candidates}
        assert set(by_code) == {"HRT1", "ETH1"}
        assert by_code["ETH1"].signals == ("reference",)
        assert by_code["ETH1"].score == pytest.approx(0.5 * by_code["HRT1"].score)

    async def test_the_list_is_limited_to_k(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        for item in (library.heart, library.communication, library.hygiene, library.ethics):
            await vector(db_session, EmbeddedType.FRAMEWORK_ITEM, item, 5)
        await ready(redis_client)

        found = await shortlist(
            db_session,
            on,
            world.lecture_objective,
            library.framework.id,
            k=2,
            provider=AtAngle(0),
            redis=redis_client,
        )

        assert len(found.candidates) == 2

    async def test_a_server_that_is_down_falls_back_to_words_with_its_notice(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        await redis_client.set("embeddings:ready", "0", ex=30)

        found = await shortlist(
            db_session,
            on,
            world.lecture_objective,
            library.framework.id,
            redis=redis_client,
        )

        assert (found.mode, found.notice) == ("keyword", Notice.EMBEDDINGS_UNREACHABLE)
        assert [c.item.code for c in found.candidates] == ["HRT1"]
