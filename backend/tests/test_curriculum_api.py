"""Tests for the curriculum read API and who sees what."""

from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    CurriculumVersion,
    Faculty,
    LearningEvent,
    Module,
    Objective,
    Phase,
    Programme,
    QualificationType,
)
from app.models.curriculum import ObjectiveDomain, VersionStatus
from app.models.tagging import TagListKind
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.tagging import add_tag_value, set_teaching_format
from app.services.users import create_local_user
from tests.authz_helpers import grant
from tests.factories import (
    CurriculumVersionFactory,
    FacultyFactory,
    LearningEventFactory,
    ModuleFactory,
    PhaseFactory,
    ProgrammeFactory,
    TagListFactory,
)

PASSWORD = "a long enough passphrase"


@dataclass
class World:
    faculty: Faculty
    programme: Programme
    published: CurriculumVersion  # 2026
    draft: CurriculumVersion  # 2027
    year1: Phase
    year2: Phase
    anatomy: Module  # Year 1
    cardio: Module  # Year 2
    research: Module  # longitudinal, no phase
    lecture: LearningEvent  # cardio
    lab: LearningEvent  # cardio
    seminar: LearningEvent  # research
    deleted_module: Module
    outcome: Objective
    module_outcome: Objective
    event_objective: Objective
    other_programme: Programme


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


@pytest.fixture
async def world(db_session: AsyncSession, system_roles: None) -> World:
    """A faculty with a programme (2026 published, 2027 draft) and another programme."""
    db = db_session
    faculty = FacultyFactory()
    programme = ProgrammeFactory(faculty=faculty, name="BSc Health Sciences", code="BHS")
    other = ProgrammeFactory(faculty=FacultyFactory(), name="Another programme", code="OTH")
    published = CurriculumVersionFactory(
        programme=programme, academic_year=2026, status=VersionStatus.PUBLISHED
    )
    draft = CurriculumVersionFactory(programme=programme, academic_year=2027)
    other_version = CurriculumVersionFactory(programme=other, academic_year=2027)
    await save(db, faculty, programme, other, published, draft, other_version)

    year1 = PhaseFactory(version=draft, name="Year 1", position=0)
    year2 = PhaseFactory(version=draft, name="Year 2", position=1)
    empty_phase = PhaseFactory(version=draft, name="Year 3", position=2)
    deleted_phase = PhaseFactory(version=draft, name="Old year", position=3)
    await save(db, year1, year2, empty_phase, deleted_phase)
    deleted_phase.soft_delete()

    anatomy = ModuleFactory(version=draft, phase_id=year1.id, code="HSC101", position=0)
    cardio = ModuleFactory(
        version=draft, phase_id=year2.id, code="HSC201", name="Cardiovascular", position=1
    )
    research = ModuleFactory(version=draft, phase_id=None, code="HSC300", position=2)
    deleted_module = ModuleFactory(version=draft, phase_id=year2.id, code="HSC299", position=3)
    published_module = ModuleFactory(version=published, code="HSC201")
    await save(db, anatomy, cardio, research, deleted_module, published_module)
    deleted_module.soft_delete()

    lecture = LearningEventFactory(module=cardio, title="Cardiac cycle", position=1, week=4)
    lab = LearningEventFactory(module=cardio, title="Skills lab", position=0)
    deleted_event = LearningEventFactory(module=cardio, title="Gone", position=2)
    seminar = LearningEventFactory(module=research, title="Research seminar")
    await save(db, lecture, lab, deleted_event, seminar)
    deleted_event.soft_delete()

    methods = TagListFactory(key="teaching", kind=TagListKind.TEACHING_METHOD)
    await save(db, methods)
    await set_teaching_format(db, lecture, await add_tag_value(db, methods, "Lecture"))

    outcome = await add_objective(db, draft, "Apply clinical reasoning.")
    module_outcome = await add_objective(
        db, cardio, "Interpret cardiac investigations.", domain=ObjectiveDomain.SKILL
    )
    event_objective = await add_objective(db, lecture, "Describe the cardiac cycle.", position=1)
    removed = await add_objective(db, lecture, "Removed objective.", position=0)
    removed.soft_delete()
    await link_objectives(db, module_outcome, outcome)
    await link_objectives(db, event_objective, module_outcome)
    await db.flush()
    return World(
        faculty=faculty,
        programme=programme,
        published=published,
        draft=draft,
        year1=year1,
        year2=year2,
        anatomy=anatomy,
        cardio=cardio,
        research=research,
        lecture=lecture,
        lab=lab,
        seminar=seminar,
        deleted_module=deleted_module,
        outcome=outcome,
        module_outcome=module_outcome,
        event_objective=event_objective,
        other_programme=other,
    )


async def sign_in(
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    role_key: str | None = None,
    scope: ScopeRef = INSTANCE,
) -> None:
    email = f"{role_key or 'nobody'}@example.org"
    user = await create_local_user(
        db, settings, email=email, display_name="Reader", password=PASSWORD
    )
    if role_key:
        await grant(db, user, role_key, scope)
    client.cookies.clear()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200


def structure_codes(body: dict[str, object]) -> list[str]:
    """Module codes in tree order, each prefixed with its phase name (or "-")."""
    codes = []
    for phase in body["phases"]:  # type: ignore[attr-defined]
        codes += [f"{phase['name']}/{m['code']}" for m in phase["modules"]]
    codes += [f"-/{m['code']}" for m in body["modules_without_phase"]]  # type: ignore[attr-defined]
    return codes


class TestSignInRequired:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/programmes",
            "/api/v1/programmes/00000000-0000-0000-0000-000000000000",
            "/api/v1/curriculum-versions/00000000-0000-0000-0000-000000000000/structure",
            "/api/v1/curriculum-versions/00000000-0000-0000-0000-000000000000/outcomes",
            "/api/v1/modules/00000000-0000-0000-0000-000000000000",
            "/api/v1/learning-events/00000000-0000-0000-0000-000000000000",
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, path: str) -> None:
        assert (await api_client.get(path)).status_code == 401


class TestFullAccess:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "programme_director",
            ScopeRef(ScopeType.PROGRAMME, world.programme.id),
        )

    async def test_lists_own_programme_with_versions_newest_first(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get("/api/v1/programmes")

        assert response.status_code == 200
        [programme] = response.json()
        assert programme["code"] == "BHS"
        assert programme["faculty_name"] == world.faculty.name
        assert [(v["academic_year"], v["status"]) for v in programme["versions"]] == [
            (2027, "draft"),
            (2026, "published"),
        ]

    async def test_programme_details(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        world.programme.qualification_type_id = await db_session.scalar(
            select(QualificationType.id).where(QualificationType.key == "bachelors")
        )
        await db_session.flush()

        response = await api_client.get(f"/api/v1/programmes/{world.programme.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["qualification_type"]["key"] == "bachelors"
        assert body["nqf_exit_level"] == 7
        assert body["total_credits"] == 360
        assert body["che_accreditation_status"] == "not_applicable"
        assert len(body["versions"]) == 2

    async def test_other_programme_is_not_found(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(f"/api/v1/programmes/{world.other_programme.id}")

        assert response.status_code == 404

    async def test_structure_in_order_without_deleted_items(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(f"/api/v1/curriculum-versions/{world.draft.id}/structure")

        assert response.status_code == 200
        body = response.json()
        assert body["partial"] is False
        assert body["outcome_count"] == 1
        assert body["programme"]["code"] == "BHS"
        assert body["version"]["academic_year"] == 2027
        # Empty phases are part of the structure; the deleted phase and module are not.
        assert [p["name"] for p in body["phases"]] == ["Year 1", "Year 2", "Year 3"]
        assert structure_codes(body) == ["Year 1/HSC101", "Year 2/HSC201", "-/HSC300"]
        cardio = body["phases"][1]["modules"][0]
        assert cardio["context_only"] is False
        assert cardio["objective_count"] == 1
        assert [(e["title"], e["format"], e["objective_count"]) for e in cardio["events"]] == [
            ("Skills lab", None, 0),
            ("Cardiac cycle", "Lecture", 1),
        ]

    async def test_programme_outcomes(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(f"/api/v1/curriculum-versions/{world.draft.id}/outcomes")

        assert response.status_code == 200
        assert [o["text"] for o in response.json()] == ["Apply clinical reasoning."]

    async def test_module_details(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(f"/api/v1/modules/{world.cardio.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "HSC201"
        # Two live sessions of 90 contact and 120 self-study minutes each (factory values).
        assert (body["event_count"], body["contact_minutes"], body["self_study_minutes"]) == (
            2,
            180,
            240,
        )
        [outcome] = body["outcomes"]
        assert outcome["domain"] == "skill"
        assert outcome["parent_ids"] == [str(world.outcome.id)]

    async def test_learning_event_details(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(f"/api/v1/learning-events/{world.lecture.id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["format"], body["week"]) == ("Cardiac cycle", "Lecture", 4)
        assert [(o["text"], o["parent_ids"]) for o in body["objectives"]] == [
            ("Describe the cardiac cycle.", [str(world.module_outcome.id)])
        ]

    async def test_deleted_module_is_not_found(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(f"/api/v1/modules/{world.deleted_module.id}")

        assert response.status_code == 404

    async def test_deleted_version_is_hidden(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        world.published.soft_delete()
        await db_session.flush()

        [programme] = (await api_client.get("/api/v1/programmes")).json()
        structure = await api_client.get(
            f"/api/v1/curriculum-versions/{world.published.id}/structure"
        )

        assert [v["academic_year"] for v in programme["versions"]] == [2027]
        assert structure.status_code == 404


class TestBroaderScopes:
    async def test_platform_admin_sees_every_programme(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")

        names = [p["name"] for p in (await api_client.get("/api/v1/programmes")).json()]

        assert names == ["Another programme", "BSc Health Sciences"]

    async def test_curriculum_office_sees_its_faculty_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "curriculum_office",
            ScopeRef(ScopeType.FACULTY, world.faculty.id),
        )

        names = [p["name"] for p in (await api_client.get("/api/v1/programmes")).json()]

        assert names == ["BSc Health Sciences"]

    async def test_programme_of_deleted_faculty_is_hidden(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        world.faculty.soft_delete()
        await db_session.flush()

        names = [p["name"] for p in (await api_client.get("/api/v1/programmes")).json()]

        assert names == ["Another programme"]


class TestNoRoles:
    async def test_sees_nothing(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings)

        assert (await api_client.get("/api/v1/programmes")).json() == []
        for path in (
            f"/api/v1/programmes/{world.programme.id}",
            f"/api/v1/curriculum-versions/{world.published.id}/structure",
            f"/api/v1/modules/{world.cardio.id}",
            f"/api/v1/learning-events/{world.lecture.id}",
        ):
            assert (await api_client.get(path)).status_code == 404, path


class TestPublishedOnly:
    @pytest.fixture(autouse=True)
    async def student(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student")

    async def test_lists_published_versions_only(
        self, api_client: AsyncClient, world: World
    ) -> None:
        programmes = (await api_client.get("/api/v1/programmes")).json()

        # The other programme has only a draft, so it is not listed at all.
        assert [(p["code"], [v["academic_year"] for v in p["versions"]]) for p in programmes] == [
            ("BHS", [2026])
        ]

    async def test_draft_is_not_found(self, api_client: AsyncClient, world: World) -> None:
        for path in (
            f"/api/v1/curriculum-versions/{world.draft.id}/structure",
            f"/api/v1/curriculum-versions/{world.draft.id}/outcomes",
            f"/api/v1/modules/{world.cardio.id}",
            f"/api/v1/learning-events/{world.lecture.id}",
        ):
            assert (await api_client.get(path)).status_code == 404, path

    async def test_published_structure(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(
            f"/api/v1/curriculum-versions/{world.published.id}/structure"
        )

        assert response.status_code == 200
        assert response.json()["partial"] is False
        assert structure_codes(response.json()) == ["-/HSC201"]


class TestModuleScope:
    @pytest.fixture(autouse=True)
    async def coordinator(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.cardio.id),
        )

    async def test_lists_only_the_version_holding_the_module(
        self, api_client: AsyncClient, world: World
    ) -> None:
        [programme] = (await api_client.get("/api/v1/programmes")).json()

        assert [v["academic_year"] for v in programme["versions"]] == [2027]

    async def test_structure_shows_only_the_module(
        self, api_client: AsyncClient, world: World
    ) -> None:
        body = (
            await api_client.get(f"/api/v1/curriculum-versions/{world.draft.id}/structure")
        ).json()

        assert body["partial"] is True
        assert body["outcome_count"] is None
        assert structure_codes(body) == ["Year 2/HSC201"]
        module = body["phases"][0]["modules"][0]
        assert module["context_only"] is False
        assert [e["title"] for e in module["events"]] == ["Skills lab", "Cardiac cycle"]

    async def test_details_inside_the_module_only(
        self, api_client: AsyncClient, world: World
    ) -> None:
        assert (await api_client.get(f"/api/v1/modules/{world.cardio.id}")).status_code == 200
        assert (await api_client.get(f"/api/v1/learning-events/{world.lab.id}")).status_code == 200
        assert (await api_client.get(f"/api/v1/modules/{world.anatomy.id}")).status_code == 404
        assert (
            await api_client.get(f"/api/v1/learning-events/{world.seminar.id}")
        ).status_code == 404
        assert (
            await api_client.get(f"/api/v1/curriculum-versions/{world.draft.id}/outcomes")
        ).status_code == 404

    async def test_programme_details_are_visible(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(f"/api/v1/programmes/{world.programme.id}")

        assert response.status_code == 200
        assert [v["academic_year"] for v in response.json()["versions"]] == [2027]


class TestLearningEventScope:
    @pytest.fixture(autouse=True)
    async def lecturer(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lecture.id),
        )

    async def test_module_is_context_for_the_session(
        self, api_client: AsyncClient, world: World
    ) -> None:
        body = (
            await api_client.get(f"/api/v1/curriculum-versions/{world.draft.id}/structure")
        ).json()

        assert body["partial"] is True
        assert structure_codes(body) == ["Year 2/HSC201"]
        module = body["phases"][0]["modules"][0]
        assert module["context_only"] is True
        assert [e["title"] for e in module["events"]] == ["Cardiac cycle"]

    async def test_session_details_but_not_the_module(
        self, api_client: AsyncClient, world: World
    ) -> None:
        assert (
            await api_client.get(f"/api/v1/learning-events/{world.lecture.id}")
        ).status_code == 200
        assert (await api_client.get(f"/api/v1/learning-events/{world.lab.id}")).status_code == 404
        assert (await api_client.get(f"/api/v1/modules/{world.cardio.id}")).status_code == 404
