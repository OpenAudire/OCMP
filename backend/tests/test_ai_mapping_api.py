"""Tests for the AI mapping run endpoints (ADR 045): who may start one, and its state."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models.mapping import AIRunStatus
from app.services.authorization import INSTANCE, ScopeRef
from tests.conftest import EnqueuedJob
from tests.factories import ModuleFactory
from tests.mapping_helpers import Library, make_library, turn_ai_on
from tests.test_curriculum_edit_api import MISSING, sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


@pytest.fixture
async def ready(
    db_session: AsyncSession, test_settings: Settings, world: World, library: Library
) -> World:
    await turn_ai_on(db_session, world, test_settings)
    return world


def runs_url(world: World) -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/ai-mapping-runs"


def body(library: Library, **extra: object) -> dict[str, object]:
    return {"framework_id": str(library.framework.id), **extra}


async def as_director(
    client: AsyncClient, db: AsyncSession, settings: Settings, world: World
) -> None:
    await sign_in(client, db, settings, "programme_director", programme_scope(world))


class TestStarting:
    async def test_requires_sign_in(self, api_client: AsyncClient) -> None:
        for method, path in (
            ("POST", f"/curriculum-versions/{MISSING}/ai-mapping-runs"),
            ("GET", f"/curriculum-versions/{MISSING}/ai-mapping-runs"),
            ("GET", f"/ai-mapping-runs/{MISSING}"),
            ("POST", f"/ai-mapping-runs/{MISSING}/cancel"),
        ):
            response = await api_client.request(method, f"{API}{path}", json={})
            assert response.status_code == 401, path

    async def test_a_director_queues_a_run_and_a_job(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
        ready: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)

        response = await api_client.post(runs_url(ready), json=body(library, top_k=8))

        assert response.status_code == 202
        run = response.json()
        assert run["status"] == "queued"
        assert (run["total_items"], run["done_items"], run["links_created"]) == (4, 0, 0)
        assert run["top_k"] == 8 and run["module_id"] is None
        assert run["framework_id"] == str(library.framework.id)
        assert run["prompt_version"] == "mapping:1"
        jobs = [j for j in enqueued_jobs if j.actor == "run_ai_mapping"]
        assert [j.args for j in jobs] == [(run["id"],)]

    async def test_a_module_coordinator_may_run_their_module_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, ready.cardio.id),
        )

        own = await api_client.post(
            runs_url(ready), json=body(library, module_id=str(ready.cardio.id))
        )
        whole = await api_client.post(runs_url(ready), json=body(library))
        other = await api_client.post(
            runs_url(ready), json=body(library, module_id=str(ready.anatomy.id))
        )

        assert own.status_code == 202 and own.json()["total_items"] == 2
        assert whole.status_code == 403
        assert other.status_code in (403, 404)

    @pytest.mark.parametrize("role", ["mapper", "lecturer"])
    async def test_people_without_ai_run_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
        role: str,
    ) -> None:
        # A lecturer can only hold the role at a module or session.
        scope = (
            ScopeRef(ScopeType.MODULE, ready.cardio.id)
            if role == "lecturer"
            else programme_scope(ready)
        )
        await sign_in(api_client, db_session, test_settings, role, scope)

        response = await api_client.post(runs_url(ready), json=body(library))

        assert response.status_code == 403

    async def test_a_student_cannot_even_see_the_draft(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        response = await api_client.post(runs_url(ready), json=body(library))

        assert response.status_code == 404

    async def test_unknown_things_are_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)
        elsewhere = ModuleFactory(version=ready.published, code="HSC999")
        db_session.add(elsewhere)
        await db_session.flush()

        version = await api_client.post(
            f"{API}/curriculum-versions/{uuid.uuid4()}/ai-mapping-runs", json=body(library)
        )
        framework = await api_client.post(runs_url(ready), json={"framework_id": str(uuid.uuid4())})
        module = await api_client.post(
            runs_url(ready), json=body(library, module_id=str(elsewhere.id))
        )

        assert (version.status_code, framework.status_code, module.status_code) == (404, 404, 404)

    async def test_ai_that_is_off_is_a_conflict_with_the_reason(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, world)

        response = await api_client.post(runs_url(world), json=body(library))

        assert response.status_code == 409
        assert "off" in response.json()["detail"].lower()

    async def test_a_second_run_at_once_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)
        assert (await api_client.post(runs_url(ready), json=body(library))).status_code == 202

        again = await api_client.post(runs_url(ready), json=body(library))

        assert again.status_code == 409
        assert "already going" in again.json()["detail"]

    @pytest.mark.parametrize("k", [2, 21])
    async def test_the_shortlist_size_is_checked(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
        k: int,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)

        response = await api_client.post(runs_url(ready), json=body(library, top_k=k))

        assert response.status_code == 422


class TestFollowing:
    async def test_progress_list_and_cancel(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)
        first = (await api_client.post(runs_url(ready), json=body(library))).json()

        one = await api_client.get(f"{API}/ai-mapping-runs/{first['id']}")
        cancelled = await api_client.post(f"{API}/ai-mapping-runs/{first['id']}/cancel")
        second = (await api_client.post(runs_url(ready), json=body(library))).json()
        listing = await api_client.get(runs_url(ready))

        assert one.status_code == 200 and one.json()["status"] == "queued"
        assert cancelled.json()["status"] == AIRunStatus.CANCELLED.value
        assert cancelled.json()["finished_at"] is not None
        # Made in one test transaction, so they share a timestamp: compare as a set.
        assert {r["id"] for r in listing.json()} == {second["id"], first["id"]}

    async def test_a_stranger_does_not_see_the_run(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        library: Library,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)
        run = (await api_client.post(runs_url(ready), json=body(library))).json()
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        seen = await api_client.get(f"{API}/ai-mapping-runs/{run['id']}")
        cancel = await api_client.post(f"{API}/ai-mapping-runs/{run['id']}/cancel")

        assert seen.status_code == 404 and cancel.status_code == 404

    async def test_an_unknown_run_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        await as_director(api_client, db_session, test_settings, ready)

        response = await api_client.get(f"{API}/ai-mapping-runs/{uuid.uuid4()}")

        assert response.status_code == 404
