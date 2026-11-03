"""Tests for making and caching embeddings (ADR 044)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.ai.embeddings import MODEL_KEY
from app.ai.errors import ProviderError
from app.models import Framework, FrameworkItem, Objective
from app.models.curriculum import ObjectiveStatus
from app.models.embedding import EmbeddedType, Embedding
from app.models.framework import FrameworkStatus
from app.services.embeddings import coverage, framework_item_text, sweep, sync_embeddings
from tests.factories import FrameworkFactory
from tests.fakes import FakeEmbeddingProvider, one_hot
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

OBJECTIVE = EmbeddedType.OBJECTIVE
FRAMEWORK_ITEM = EmbeddedType.FRAMEWORK_ITEM


async def stored(db: AsyncSession, kind: EmbeddedType = OBJECTIVE) -> dict[object, Embedding]:
    rows = await db.scalars(select(Embedding).where(Embedding.entity_type == kind))
    return {row.entity_id: row for row in rows}


class TestObjectives:
    async def test_every_live_objective_gets_a_vector_once(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()

        first = await sync_embeddings(db_session, provider, OBJECTIVE)
        second = await sync_embeddings(db_session, provider, OBJECTIVE)

        # Five objectives in the world (the published version's outcome counts).
        assert (first.embedded, first.unchanged) == (5, 0)
        assert (second.embedded, second.unchanged) == (0, 5)
        assert len(provider.texts_sent) == 5
        rows = await stored(db_session)
        row = rows[world.lecture_objective.id]
        assert row.model_key == MODEL_KEY
        assert list(row.vector) == one_hot("Describe the cardiac cycle.")

    async def test_changed_wording_is_embedded_again_and_nothing_else(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()
        await sync_embeddings(db_session, provider, OBJECTIVE)
        provider.calls.clear()
        world.lecture_objective.text = "Explain the cardiac cycle."
        await db_session.flush()

        result = await sync_embeddings(db_session, provider, OBJECTIVE)

        assert result.embedded == 1
        assert result.changed_ids == (world.lecture_objective.id,)
        assert provider.texts_sent == ["Explain the cardiac cycle."]

    async def test_spacing_changes_alone_do_not_trigger_a_new_vector(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()
        await sync_embeddings(db_session, provider, OBJECTIVE)
        world.lecture_objective.text = "Describe  the cardiac\ncycle. "
        await db_session.flush()

        result = await sync_embeddings(db_session, provider, OBJECTIVE)

        assert result.embedded == 0

    async def test_deleted_and_retired_objectives_lose_their_vector(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()
        await sync_embeddings(db_session, provider, OBJECTIVE)
        world.anatomy_outcome.soft_delete()
        world.cardio_outcome.status = ObjectiveStatus.RETIRED
        await db_session.flush()

        result = await sync_embeddings(db_session, provider, OBJECTIVE)

        assert result.removed == 2
        assert world.anatomy_outcome.id not in await stored(db_session)
        assert world.cardio_outcome.id not in await stored(db_session)

    async def test_a_sync_of_listed_items_leaves_the_rest_alone(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()

        result = await sync_embeddings(
            db_session, provider, OBJECTIVE, ids=[world.lecture_objective.id]
        )

        assert result.embedded == 1
        assert list(await stored(db_session)) == [world.lecture_objective.id]

    async def test_vectors_of_an_older_recipe_are_replaced_by_a_full_sync_only(
        self, db_session: AsyncSession, world: World
    ) -> None:
        db_session.add(
            Embedding(
                entity_type=OBJECTIVE,
                entity_id=world.lecture_objective.id,
                model_key="old-model|query:|v0",
                text_hash="x",
                vector=one_hot("old"),
            )
        )
        await db_session.flush()
        provider = FakeEmbeddingProvider()

        await sync_embeddings(db_session, provider, OBJECTIVE, ids=[world.lecture_objective.id])
        kept = await db_session.scalar(
            select(func.count()).select_from(Embedding).where(Embedding.model_key != MODEL_KEY)
        )
        full = await sync_embeddings(db_session, provider, OBJECTIVE)
        left = await db_session.scalar(
            select(func.count()).select_from(Embedding).where(Embedding.model_key != MODEL_KEY)
        )

        assert kept == 1
        assert left == 0
        assert full.removed == 1

    async def test_a_server_failure_raises_and_stores_nothing(
        self, db_session: AsyncSession, world: World
    ) -> None:
        with pytest.raises(ProviderError):
            await sync_embeddings(db_session, FakeEmbeddingProvider(fail=True), OBJECTIVE)

        assert await stored(db_session) == {}


class TestFlaggedText:
    async def test_text_with_personal_information_is_still_embedded_and_counted(
        self, db_session: AsyncSession, world: World
    ) -> None:
        world.lecture_objective.text = "Write to jane.doe@example.org about the cardiac cycle."
        await db_session.flush()
        provider = FakeEmbeddingProvider()

        with capture_logs() as logs:
            result = await sync_embeddings(db_session, provider, OBJECTIVE)

        assert result.flagged == 1
        assert world.lecture_objective.id in await stored(db_session)
        # Counts only: neither the text nor what was found reaches the log.
        assert "jane.doe" not in repr(logs)
        done = next(entry for entry in logs if entry["event"] == "embeddings_synced")
        assert done["flagged"] == 1


class TestFrameworkItems:
    async def make(self, db: AsyncSession, status: FrameworkStatus) -> list[FrameworkItem]:
        framework = FrameworkFactory(status=status)
        db.add(framework)
        await db.flush()
        items = [
            FrameworkItem(
                framework_id=framework.id, code="A", title="Communication", description=""
            ),
            FrameworkItem(
                framework_id=framework.id,
                code="B",
                title="Professionalism",
                description="Acts ethically.",
            ),
        ]
        db.add_all(items)
        await db.flush()
        return items

    def test_title_then_description(self) -> None:
        assert framework_item_text("Professionalism ", " Acts ethically.") == (
            "Professionalism. Acts ethically."
        )
        assert framework_item_text("Communication", "") == "Communication"

    async def test_items_of_active_frameworks_are_embedded(self, db_session: AsyncSession) -> None:
        items = await self.make(db_session, FrameworkStatus.ACTIVE)
        provider = FakeEmbeddingProvider()

        result = await sync_embeddings(db_session, provider, FRAMEWORK_ITEM)

        assert result.embedded == 2
        assert sorted(provider.texts_sent) == ["Communication", "Professionalism. Acts ethically."]
        assert set(await stored(db_session, FRAMEWORK_ITEM)) == {i.id for i in items}

    async def test_drafts_and_deleted_frameworks_are_left_out(
        self, db_session: AsyncSession
    ) -> None:
        await self.make(db_session, FrameworkStatus.DRAFT)
        deleted = await self.make(db_session, FrameworkStatus.ACTIVE)
        framework = await db_session.get(Framework, deleted[0].framework_id)
        assert framework is not None
        framework.soft_delete()
        await db_session.flush()

        result = await sync_embeddings(db_session, FakeEmbeddingProvider(), FRAMEWORK_ITEM)

        assert result.embedded == 0


class TestSweepAndCoverage:
    async def test_coverage_counts_current_vectors(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await sync_embeddings(
            db_session, FakeEmbeddingProvider(), OBJECTIVE, ids=[world.lecture_objective.id]
        )

        found = {item.entity_type: item for item in await coverage(db_session)}

        assert (found[OBJECTIVE].live, found[OBJECTIVE].embedded) == (5, 1)
        assert found[FRAMEWORK_ITEM].live == 0

    async def test_a_sweep_refreshes_the_pairs_of_what_changed(
        self, db_session: AsyncSession, world: World
    ) -> None:
        twin = Objective(
            version_id=world.draft.id,
            level=world.lecture_objective.level,
            learning_event_id=world.lab.id,
            text=world.lecture_objective.text,
        )
        db_session.add(twin)
        await db_session.flush()

        result = await sweep(db_session, FakeEmbeddingProvider(), OBJECTIVE)

        assert twin.id in result.changed_ids
        from app.models.embedding import ObjectiveSimilarity

        pairs = (await db_session.scalars(select(ObjectiveSimilarity))).all()
        assert len(pairs) == 1
        assert pairs[0].similarity == pytest.approx(1.0)
