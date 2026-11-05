"""Tests for the curriculum explorer: published versions only, what a person sees, no mappings
(ADR 059)."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models.curriculum import ObjectiveStatus, VersionStatus
from app.services import assessments
from app.services.authorization import ScopeRef
from tests.test_coverage_report import Library, accept
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


@pytest.fixture
async def published(db_session: AsyncSession, world: World) -> World:
    """The 2027 version published, with weeks on the sessions and an assessment."""
    world.lecture.week = 1
    world.lab.week = 2
    world.anatomy_session.week = 1
    await db_session.flush()
    exam = await assessments.create_assessment(
        db_session,
        world.cardio,
        world.draft,
        assessments.AssessmentFields(name="Block test", weight=Decimal("40"), time_minutes=90),
    )
    await assessments.create_item(
        db_session,
        exam,
        world.cardio,
        world.draft,
        label="Question 1",
        marks=Decimal("10"),
        objective_ids=[world.cardio_outcome.id, world.lecture_objective.id],
    )
    await assessments.create_item(
        db_session,
        exam,
        world.cardio,
        world.draft,
        label="Question 2",
        marks=None,
        objective_ids=[world.lecture_objective.id],
    )
    world.draft.status = (
        VersionStatus.PUBLISHED
    )  # after the edits: a published version is read-only
    await db_session.flush()
    return world


@pytest.fixture
async def student(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, published: World
):  # type: ignore[no-untyped-def]
    return await sign_in(api_client, db_session, test_settings, "student")


@pytest.mark.usefixtures("student")
class TestModule:
    async def test_a_student_sees_outcomes_sessions_by_week_and_what_is_assessed(
        self, api_client: AsyncClient, published: World
    ) -> None:
        response = await api_client.get(f"{API}/modules/{published.cardio.id}/explorer")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == "HSC201"
        assert [o["text"] for o in body["outcomes"]] == [published.cardio_outcome.text]
        assert [(s["title"], s["week"]) for s in body["sessions"]] == [
            ("Cardiac cycle", 1),
            ("Skills lab", 2),
        ]
        lecture = body["sessions"][0]
        assert [o["text"] for o in lecture["objectives"]] == [published.lecture_objective.text]
        [test] = body["assessments"]
        assert test["name"] == "Block test" and test["weight"] == 40.0
        assert [i["label"] for i in test["items"]] == ["Question 1", "Question 2"]
        assert [o["text"] for o in test["items"][0]["objectives"]] == [
            published.cardio_outcome.text,
            published.lecture_objective.text,
        ]
        # What the test covers: each objective once, in the module's order.
        assert [o["text"] for o in test["covered"]] == [
            published.cardio_outcome.text,
            published.lecture_objective.text,
        ]

    async def test_retired_objectives_are_left_out(
        self, api_client: AsyncClient, db_session: AsyncSession, published: World
    ) -> None:
        published.lecture_objective.status = ObjectiveStatus.RETIRED
        await db_session.flush()

        body = (await api_client.get(f"{API}/modules/{published.cardio.id}/explorer")).json()

        assert body["sessions"][0]["objectives"] == []
        assert published.lecture_objective.text not in [
            o["text"] for o in body["assessments"][0]["covered"]
        ]

    async def test_mappings_are_never_part_of_the_answer(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        published: World,
        library: Library,
    ) -> None:
        await accept(db_session, published.lecture_objective, library.one)

        text = (await api_client.get(f"{API}/modules/{published.cardio.id}/explorer")).text

        assert "G1.1" not in text and "Skill 1" not in text and "framework" not in text.lower()

    async def test_a_module_of_an_unpublished_version_is_a_404(
        self, api_client: AsyncClient, db_session: AsyncSession, published: World
    ) -> None:
        published.draft.status = VersionStatus.DRAFT
        await db_session.flush()

        response = await api_client.get(f"{API}/modules/{published.cardio.id}/explorer")

        assert response.status_code == 404

    async def test_an_unknown_module_is_a_404(self, api_client: AsyncClient) -> None:
        response = await api_client.get(
            f"{API}/modules/00000000-0000-0000-0000-000000000000/explorer"
        )

        assert response.status_code == 404


@pytest.mark.usefixtures("student")
class TestWeek:
    async def test_a_week_lists_its_sessions_across_modules_in_order(
        self, api_client: AsyncClient, published: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{published.draft.id}/explorer/week", params={"week": 1}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["week"] == 1 and body["weeks"] == [1, 2] and body["academic_year"] == 2027
        assert [(s["module_code"], s["title"]) for s in body["sessions"]] == [
            ("HSC201", "Cardiac cycle"),
            ("HSC101", "Bones"),
        ]
        assert [o["text"] for o in body["sessions"][0]["objectives"]] == [
            published.lecture_objective.text
        ]

    async def test_an_empty_week_is_an_empty_list(
        self, api_client: AsyncClient, published: World
    ) -> None:
        body = (
            await api_client.get(
                f"{API}/curriculum-versions/{published.draft.id}/explorer/week",
                params={"week": 9},
            )
        ).json()

        assert body["sessions"] == [] and body["weeks"] == [1, 2]

    async def test_a_draft_version_is_a_404(
        self, api_client: AsyncClient, db_session: AsyncSession, published: World
    ) -> None:
        published.draft.status = VersionStatus.DRAFT
        await db_session.flush()

        response = await api_client.get(
            f"{API}/curriculum-versions/{published.draft.id}/explorer/week"
        )

        assert response.status_code == 404

    async def test_the_week_must_be_a_sensible_number(
        self, api_client: AsyncClient, published: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{published.draft.id}/explorer/week", params={"week": -1}
        )

        assert response.status_code == 422


class TestAccess:
    async def test_a_lecturer_of_one_module_sees_only_their_sessions(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        published: World,
    ) -> None:
        # A role at one module of a published version (not at the programme) narrows the view.
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.MODULE, published.anatomy.id),
        )

        body = (
            await api_client.get(
                f"{API}/curriculum-versions/{published.draft.id}/explorer/week",
                params={"week": 1},
            )
        ).json()

        assert {s["module_code"] for s in body["sessions"]} <= {"HSC101"}

    async def test_nobody_signed_out_reads_it(
        self, api_client: AsyncClient, published: World
    ) -> None:
        response = await api_client.get(f"{API}/modules/{published.cardio.id}/explorer")

        assert response.status_code in (401, 403)
