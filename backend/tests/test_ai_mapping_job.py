"""Tests for the background job that runs an AI mapping run (ADR 045)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.jobs import mapping as job
from app.models import AIRun
from app.models.mapping import AIRunStatus
from app.services import ai_mapping
from tests.mapping_helpers import Library, make_library, turn_ai_on
from tests.test_ai_mapping import a_user
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture


@pytest.fixture
def job_session(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    @asynccontextmanager
    async def resources(_settings: Settings) -> AsyncIterator[tuple[AsyncSession, Redis | None]]:
        yield db_session, None

    monkeypatch.setattr(job, "job_resources", resources)
    return db_session


class TestJobBody:
    async def test_it_commits_as_it_goes_and_leaves_the_run_in_a_final_state(
        self,
        job_session: AsyncSession,
        test_settings: Settings,
        world: World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        library: Library = await make_library(job_session)
        await turn_ai_on(job_session, world, test_settings)
        run = await ai_mapping.start_run(
            job_session,
            test_settings,
            actor_id=await a_user(job_session),
            version=world.draft,
            framework=library.framework,
        )
        commits = 0
        original = job_session.commit

        async def counting_commit() -> None:
            nonlocal commits
            commits += 1
            await original()

        monkeypatch.setattr(job_session, "commit", counting_commit)
        # AI is turned off before the job runs, so the run ends in a clear failed state
        # without any network call (the pipeline itself is tested with a mock provider).
        await turn_ai_on(job_session, world, test_settings, active_provider="null")

        done = await job.run_ai_mapping_job(test_settings, str(run.id))

        assert done.status is AIRunStatus.FAILED and done.error_message
        assert (await job_session.get(AIRun, run.id)).status is AIRunStatus.FAILED  # type: ignore[union-attr]
        # Once when it starts running and once at the end, at least.
        assert commits >= 2

    async def test_the_actor_is_registered_without_retries(self) -> None:
        # A retry would call a paid provider again for objectives already done.
        assert job.run_ai_mapping.actor_name == "run_ai_mapping"
        assert job.run_ai_mapping.options["max_retries"] == 0
