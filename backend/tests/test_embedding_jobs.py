"""Tests for the embedding jobs and for when the API queues them (ADR 044)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.jobs import embeddings as jobs
from app.jobs.embeddings import (
    ObjectiveNotFoundYet,
    embed_one_objective,
    run_embed_objective,
    run_embed_pending,
)
from app.models import Objective
from app.models.embedding import Embedding, ObjectiveSimilarity
from app.services.curriculum import add_objective
from tests.conftest import EnqueuedJob
from tests.fakes import FakeEmbeddingProvider
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


class TestEmbedOneObjective:
    async def test_embeds_the_objective_and_finds_its_pairs(
        self, db_session: AsyncSession, world: World
    ) -> None:
        twin = await add_objective(db_session, world.lab, world.lecture_objective.text)
        provider = FakeEmbeddingProvider()
        # The twin was saved first and embedded; then the lecture objective is saved.
        await embed_one_objective(db_session, provider, twin.id)
        await embed_one_objective(db_session, provider, world.lecture_objective.id)

        vectors = await db_session.scalar(select(func.count()).select_from(Embedding))
        similarities = (await db_session.scalars(select(ObjectiveSimilarity))).all()

        assert vectors == 2
        assert len(similarities) == 1
        assert similarities[0].similarity == pytest.approx(1.0)

    async def test_an_objective_the_job_cannot_see_yet_is_retried(
        self, db_session: AsyncSession
    ) -> None:
        import uuid

        with pytest.raises(ObjectiveNotFoundYet):
            await embed_one_objective(db_session, FakeEmbeddingProvider(), uuid.uuid4())

    async def test_a_deleted_objective_loses_its_vector_and_pairs(
        self, db_session: AsyncSession, world: World
    ) -> None:
        provider = FakeEmbeddingProvider()
        await embed_one_objective(db_session, provider, world.lecture_objective.id)
        world.lecture_objective.soft_delete()
        await db_session.flush()

        await embed_one_objective(db_session, provider, world.lecture_objective.id)

        assert await db_session.scalar(select(func.count()).select_from(Embedding)) == 0

    async def test_a_server_failure_is_raised_so_the_job_is_retried(
        self, db_session: AsyncSession, world: World
    ) -> None:
        from app.ai.errors import ProviderError

        with pytest.raises(ProviderError):
            await embed_one_objective(
                db_session, FakeEmbeddingProvider(fail=True), world.lecture_objective.id
            )


@pytest.fixture
def job_session(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> FakeEmbeddingProvider:
    """Run the job bodies against the test session and a fake embeddings server."""
    provider = FakeEmbeddingProvider()

    @asynccontextmanager
    async def resources(_settings: Settings) -> AsyncIterator[tuple[AsyncSession, None]]:
        yield db_session, None

    monkeypatch.setattr(jobs, "job_resources", resources)
    monkeypatch.setattr(jobs, "get_embedding_provider", lambda _settings: provider)
    return provider


class TestJobBodies:
    async def test_embed_objective_does_nothing_while_embeddings_are_off(
        self,
        test_settings: Settings,
        job_session: FakeEmbeddingProvider,
        world: World,
    ) -> None:
        await run_embed_objective(test_settings, str(world.lecture_objective.id))

        assert job_session.calls == []

    async def test_embed_objective_embeds_when_on(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        job_session: FakeEmbeddingProvider,
        world: World,
    ) -> None:
        settings = test_settings.model_copy(update={"embeddings_local": True})

        await run_embed_objective(settings, str(world.lecture_objective.id))

        assert job_session.texts_sent == [world.lecture_objective.text]
        assert await db_session.scalar(select(func.count()).select_from(Embedding)) == 1

    async def test_embed_pending_sweeps_a_type_and_reports_counts(
        self,
        test_settings: Settings,
        job_session: FakeEmbeddingProvider,
        world: World,
    ) -> None:
        settings = test_settings.model_copy(update={"embeddings_local": True})

        off = await run_embed_pending(test_settings, "objective")
        done = await run_embed_pending(settings, "objective")

        assert off.embedded == 0 and job_session.calls == [job_session.texts_sent]
        assert done.embedded == 5


@pytest.fixture
def embeddings_on(api_app: FastAPI, test_settings: Settings) -> Settings:
    settings = test_settings.model_copy(update={"embeddings_local": True})
    api_app.dependency_overrides[get_settings] = lambda: settings
    return settings


def names(jobs: list[EnqueuedJob]) -> list[str]:
    return [job.actor for job in jobs]


class TestQueueing:
    async def test_nothing_is_queued_while_embeddings_are_off(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

        created = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives", json={"text": "Palpate a pulse."}
        )

        assert created.status_code == 201
        assert [n for n in names(enqueued_jobs) if n.startswith("embed")] == []

    async def test_create_update_and_delete_each_queue_one_job_for_the_objective(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        enqueued_jobs: list[EnqueuedJob],
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, embeddings_on, "programme_director", programme_scope(world)
        )

        created = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives", json={"text": "Palpate a pulse."}
        )
        objective_id = created.json()["id"]
        await api_client.patch(f"{API}/objectives/{objective_id}", json={"text": "Take a pulse."})
        await api_client.delete(f"{API}/objectives/{objective_id}")

        queued = [j for j in enqueued_jobs if j.actor == "embed_objective"]
        assert [j.args for j in queued] == [(objective_id,)] * 3

    async def test_module_and_programme_outcomes_are_queued_too(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        enqueued_jobs: list[EnqueuedJob],
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, embeddings_on, "programme_director", programme_scope(world)
        )

        await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes", json={"text": "Interpret a pulse."}
        )
        await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcomes", json={"text": "Care safely."}
        )

        assert names(enqueued_jobs).count("embed_objective") == 2

    async def test_copy_forward_queues_a_sweep_of_objectives(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        enqueued_jobs: list[EnqueuedJob],
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, embeddings_on, "programme_director", programme_scope(world)
        )

        response = await api_client.post(
            f"{API}/curriculum-versions/{world.published.id}/copy-forward",
            json={"academic_year": 2030},
        )

        assert response.status_code == 201
        sweeps = [j for j in enqueued_jobs if j.actor == "embed_pending"]
        assert [j.args for j in sweeps] == [("objective",)]

    async def test_a_refused_save_queues_nothing(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        enqueued_jobs: list[EnqueuedJob],
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, embeddings_on, "programme_director", programme_scope(world)
        )

        refused = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives", json={"text": "   "}
        )

        assert refused.status_code == 422
        assert names(enqueued_jobs).count("embed_objective") == 0
        assert await db_session.scalar(select(func.count()).select_from(Objective)) >= 5
