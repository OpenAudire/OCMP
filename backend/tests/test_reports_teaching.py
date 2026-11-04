"""Tests for the teaching reports (ADR 053): formats and hours, relationship, role balance,
assessment methods."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    LearningEvent,
    Objective,
    TagValue,
)
from app.models.tagging import TagListKind
from app.services.curriculum import add_objective, link_objectives
from app.services.institution_settings import get_institution
from app.services.tagging import add_tag_value
from tests.factories import LearningEventFactory, PhaseFactory, TagListFactory
from tests.test_coverage_report import Library, accept
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def url(world: World, key: str) -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/reports/{key}"


def section(body: dict, start: str) -> dict:  # type: ignore[type-arg]
    return next(s for s in body["sections"] if s["title"].startswith(start))


async def values(db: AsyncSession, kind: TagListKind, *labels: str) -> list[TagValue]:
    tag_list = TagListFactory(kind=kind)
    db.add(tag_list)
    await db.flush()
    return [await add_tag_value(db, tag_list, label, position=i) for i, label in enumerate(labels)]


async def session(
    db: AsyncSession,
    module: object,
    title: str,
    *,
    contact: int = 60,
    study: int = 0,
    fmt: TagValue | None = None,
) -> LearningEvent:
    event: LearningEvent = LearningEventFactory(
        module=module, title=title, contact_minutes=contact, self_study_minutes=study
    )
    if fmt is not None:
        event.format_value_id = fmt.id
    db.add(event)
    await db.flush()
    return event


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


async def get(api_client: AsyncClient, world: World, key: str, **params: str) -> dict:  # type: ignore[type-arg]
    response = await api_client.get(url(world, key), params=params)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


@pytest.mark.usefixtures("admin")
class TestFormats:
    async def test_adds_up_hours_by_format_and_gives_each_its_share(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        lecture, lab = await values(db_session, TagListKind.TEACHING_METHOD, "Lecture", "Lab")
        await session(db_session, world.cardio, "A", contact=90, study=30, fmt=lecture)
        await session(db_session, world.cardio, "B", contact=90, fmt=lecture)
        await session(db_session, world.anatomy, "C", contact=60, fmt=lab)
        await session(db_session, world.anatomy, "D", contact=30)

        body = await get(api_client, world, "formats")

        rows = {r[0]: r for r in section(body, "By teaching format")["rows"]}
        assert rows["Lecture"][1:4] == [2, 3.0, 0.5]
        assert rows["Lab"][1:3] == [1, 1.0]
        assert rows["No format set"][2] > 0
        total = rows["All formats"]
        assert total[4] == 1.0
        assert rows["Lecture"][4] == pytest.approx(rows["Lecture"][2] / total[2], abs=0.01)
        by_module = {r[0]: r for r in section(body, "By module")["rows"]}
        assert by_module["HSC201"][4] >= 3.0
        assert body["method"]

    async def test_a_phase_filter_keeps_only_that_phase(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        phase = PhaseFactory(version=world.draft, name="Year 1")
        db_session.add(phase)
        await db_session.flush()
        world.anatomy.phase_id = phase.id
        await session(db_session, world.anatomy, "Only here", contact=120)
        await db_session.flush()

        body = await get(api_client, world, "formats", phase_id=str(phase.id))

        modules = section(body, "By module")["rows"]
        assert [r[0] for r in modules] == ["HSC101"]


@pytest.mark.usefixtures("admin")
class TestRelationship:
    async def test_one_row_per_session_and_objective_and_one_for_a_bare_session(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        (lecture,) = await values(db_session, TagListKind.TEACHING_METHOD, "Lecture")
        event = await session(db_session, world.cardio, "Heart", fmt=lecture)
        await add_objective(db_session, event, "Describe the heart.")
        await add_objective(db_session, event, "Explain blood flow.")
        await session(db_session, world.cardio, "Bare")

        body = await get(api_client, world, "relationship")

        rows = section(body, "Sessions")["rows"]
        heart = [r for r in rows if r[3] == "Heart"]
        assert sorted(r[6] for r in heart) == ["Describe the heart.", "Explain blood flow."]
        assert all(r[4] == "Lecture" for r in heart)
        [bare] = [r for r in rows if r[3] == "Bare"]
        assert bare[6] is None and bare[4] == "No format set"


@pytest.mark.usefixtures("admin")
class TestRoleBalance:
    async def test_refused_unless_the_health_profile_is_on(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        response = await api_client.get(
            url(world, "role-balance"), params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 422

    async def test_a_sessions_time_is_shared_equally_between_the_groups_it_touches(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        institution = await get_institution(db_session)
        assert institution is not None
        institution.settings = {**institution.settings, "profiles": ["core", "health"]}
        await db_session.flush()
        shared = await session(db_session, world.cardio, "Shared", contact=120)
        one = await add_objective(db_session, shared, "Do the first thing.")
        two = await add_objective(db_session, shared, "Do the second thing.")
        await accept(db_session, one, library.one)  # group G1
        await accept(db_session, two, library.other)  # group G2
        await session(db_session, world.cardio, "Unmapped", contact=60)

        body = await get(api_client, world, "role-balance", framework_id=str(library.framework.id))

        time = {r[1]: r for r in section(body, "Teaching time")["rows"]}
        g1 = next(r for k, r in time.items() if k.startswith("G1 "))
        g2 = next(r for k, r in time.items() if k.startswith("G2 "))
        assert g1[2] == g2[2] == 1.0  # 120 minutes split in two
        assert time["Not mapped to this framework"][2] >= 1.0
        count = {r[1]: r for r in section(body, "Objectives")["rows"]}
        assert next(r for k, r in count.items() if k.startswith("G1 "))[2] == 1

    async def test_an_objective_with_no_link_is_estimated_from_the_outcome_it_links_up_to(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        institution = await get_institution(db_session)
        assert institution is not None
        institution.settings = {**institution.settings, "profiles": ["core", "health"]}
        await db_session.flush()
        # A module outcome of anatomy mapped to G2 (a different group from the session's own).
        outcome = world.anatomy_outcome
        await accept(db_session, outcome, library.other)
        event = await session(db_session, world.anatomy, "Mixed", contact=120)
        own = await add_objective(db_session, event, "Has its own link.")
        estimated = await add_objective(db_session, event, "Has none of its own.")
        await accept(db_session, own, library.one)  # G1
        await link_objectives(db_session, estimated, outcome)  # up to the outcome (G2)

        body = await get(api_client, world, "role-balance", framework_id=str(library.framework.id))

        time = {r[1]: r for r in section(body, "Teaching time")["rows"]}
        g1 = next(r for k, r in time.items() if k.startswith("G1 "))
        g2 = next(r for k, r in time.items() if k.startswith("G2 "))
        # 120 minutes over two objectives: 60 to G1 (its own), 60 to G2 (estimated).
        assert g1[2] >= 1.0 and g2[2] >= 1.0
        # G2's hours are all estimated (the world's other anatomy sessions, which have no
        # objective, fall back to the module's outcomes and add to them).
        assert g2[3] >= 1.0 and g2[3] == g2[2]
        assert g1[3] == 0.0
        assert "estimated" in section(body, "Teaching time")["note"]


@pytest.mark.usefixtures("admin")
class TestAssessments:
    async def test_counts_assessments_assessed_objectives_and_lists_those_with_no_method(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        exam, _portfolio = await values(
            db_session, TagListKind.ASSESSMENT_METHOD, "Exam", "Portfolio"
        )
        event = await session(db_session, world.cardio, "Heart")
        assessed: Objective = await add_objective(db_session, event, "Assessed by exam.")
        await add_objective(db_session, event, "Nothing assesses this one.")
        assessment = Assessment(module_id=world.cardio.id, name="Final", method_value_id=exam.id)
        db_session.add(assessment)
        await db_session.flush()
        item = AssessmentItem(assessment_id=assessment.id, label="Q1")
        db_session.add(item)
        await db_session.flush()
        db_session.add(AssessmentItemObjective(item_id=item.id, objective_id=assessed.id))
        await db_session.flush()

        body = await get(api_client, world, "assessments")

        rows = {r[0].split(": ")[1]: r for r in section(body, "By assessment method")["rows"]}
        assert rows["Exam"][1:4] == [1, 1, 1]
        assert rows["Portfolio"][1:4] == [0, 0, 0]
        missing = [r[3] for r in section(body, "Objectives with no")["rows"]]
        assert "Nothing assesses this one." in missing
        assert "Assessed by exam." not in missing
