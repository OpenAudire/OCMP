"""Tests for editing the curriculum structure: phases, modules and learning events."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    AuditLog,
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    Phase,
    Programme,
    TagValue,
    User,
)
from app.models.curriculum import VersionStatus
from app.models.tagging import TagListKind
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum import add_objective
from app.services.tagging import add_tag_value
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
API = "/api/v1"
MISSING = "00000000-0000-0000-0000-000000000000"


@dataclass
class World:
    programme: Programme
    draft: CurriculumVersion  # 2027
    published: CurriculumVersion  # 2026
    archived: CurriculumVersion  # 2025
    year1: Phase
    year2: Phase
    other_phase: Phase  # in the published version
    anatomy: Module  # Year 1
    cardio: Module  # Year 2
    published_module: Module
    archived_module: Module
    lecture: LearningEvent  # cardio
    lab: LearningEvent  # cardio
    lecture_objective: Objective
    cardio_outcome: Objective
    lecture_format: TagValue
    theme: TagValue  # from a list that is not a teaching-method list
    other_version: CurriculumVersion


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


@pytest.fixture
async def world(db_session: AsyncSession, system_roles: None) -> World:
    db = db_session
    programme = ProgrammeFactory(faculty=FacultyFactory(), code="BHS")
    draft = CurriculumVersionFactory(programme=programme, academic_year=2027)
    published = CurriculumVersionFactory(
        programme=programme, academic_year=2026, status=VersionStatus.PUBLISHED
    )
    archived = CurriculumVersionFactory(
        programme=programme, academic_year=2025, status=VersionStatus.ARCHIVED
    )
    other_version = CurriculumVersionFactory(academic_year=2027)
    await save(db, programme, draft, published, archived, other_version)

    year1 = PhaseFactory(version=draft, name="Year 1", position=0)
    year2 = PhaseFactory(version=draft, name="Year 2", position=1)
    other_phase = PhaseFactory(version=published, name="Year 1", position=0)
    await save(db, year1, year2, other_phase)

    anatomy = ModuleFactory(version=draft, phase_id=year1.id, code="HSC101", position=0)
    cardio = ModuleFactory(version=draft, phase_id=year2.id, code="HSC201", position=1)
    published_module = ModuleFactory(version=published, code="HSC201")
    archived_module = ModuleFactory(version=archived, code="HSC201")
    await save(db, anatomy, cardio, published_module, archived_module)

    lecture = LearningEventFactory(module=cardio, title="Cardiac cycle", position=0)
    lab = LearningEventFactory(module=cardio, title="Skills lab", position=1)
    await save(db, lecture, lab)

    methods = TagListFactory(key="teaching", kind=TagListKind.TEACHING_METHOD, name="Methods")
    themes = TagListFactory(key="themes", kind=TagListKind.THEME)
    await save(db, methods, themes)
    lecture_format = await add_tag_value(db, methods, "Lecture")
    theme = await add_tag_value(db, themes, "Ethics")

    cardio_outcome = await add_objective(db, cardio, "Interpret cardiac investigations.")
    lecture_objective = await add_objective(db, lecture, "Describe the cardiac cycle.")
    return World(
        programme=programme,
        draft=draft,
        published=published,
        archived=archived,
        year1=year1,
        year2=year2,
        other_phase=other_phase,
        anatomy=anatomy,
        cardio=cardio,
        published_module=published_module,
        archived_module=archived_module,
        lecture=lecture,
        lab=lab,
        lecture_objective=lecture_objective,
        cardio_outcome=cardio_outcome,
        lecture_format=lecture_format,
        theme=theme,
        other_version=other_version,
    )


async def sign_in(
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    role_key: str | None,
    scope: ScopeRef = INSTANCE,
) -> User:
    email = f"{role_key or 'nobody'}@example.org"
    user = await create_local_user(
        db, settings, email=email, display_name="Editor", password=PASSWORD
    )
    if role_key:
        await grant(db, user, role_key, scope)
    client.cookies.clear()
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["ocmp_csrf"]
    return user


def programme_scope(world: World) -> ScopeRef:
    return ScopeRef(ScopeType.PROGRAMME, world.programme.id)


async def structure(client: AsyncClient, world: World) -> dict[str, Any]:
    response = await client.get(f"{API}/curriculum-versions/{world.draft.id}/structure")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", f"/curriculum-versions/{MISSING}/phases"),
            ("PATCH", f"/phases/{MISSING}"),
            ("DELETE", f"/phases/{MISSING}"),
            ("POST", f"/curriculum-versions/{MISSING}/modules"),
            ("PATCH", f"/modules/{MISSING}"),
            ("DELETE", f"/modules/{MISSING}"),
            ("POST", f"/modules/{MISSING}/learning-events"),
            ("PATCH", f"/learning-events/{MISSING}"),
            ("DELETE", f"/learning-events/{MISSING}"),
            ("GET", "/teaching-formats"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={})
        assert response.status_code == 401


class TestProgrammeDirector:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    async def test_structure_says_everything_is_editable(
        self, api_client: AsyncClient, world: World
    ) -> None:
        body = await structure(api_client, world)

        assert body["can_edit"] is True
        cardio = body["phases"][1]["modules"][0]
        assert cardio["can_edit"] is True
        assert all(event["can_edit"] for event in cardio["events"])

    async def test_adds_phase_at_the_end_and_audits_it(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/phases",
            json={"name": "  Year 3 ", "kind": "block"},
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["name"], body["kind"], body["position"]) == ("Year 3", "block", 2)
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "phases",
                AuditLog.action == "create",
                AuditLog.entity_id == uuid.UUID(body["id"]),
            )
        )
        assert entry is not None
        assert entry.context["operation"] == "curriculum.phase_create"
        assert entry.actor_id is not None
        assert [p["name"] for p in (await structure(api_client, world))["phases"]] == [
            "Year 1",
            "Year 2",
            "Year 3",
        ]

    async def test_renames_phase(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.patch(
            f"{API}/phases/{world.year1.id}", json={"name": "First year"}
        )

        assert response.status_code == 200
        assert (response.json()["name"], response.json()["kind"]) == ("First year", "year")

    async def test_blank_phase_name_is_refused(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.patch(f"{API}/phases/{world.year1.id}", json={"name": "  "})

        assert response.status_code == 422

    async def test_deletes_empty_phase_only(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        refused = await api_client.delete(f"{API}/phases/{world.year1.id}")
        assert refused.status_code == 409

        empty = PhaseFactory(version=world.draft, name="Year 3", position=2)
        await save(db_session, empty)
        response = await api_client.delete(f"{API}/phases/{empty.id}")

        assert response.status_code == 204
        assert empty.deleted_at is not None
        assert (await api_client.delete(f"{API}/phases/{empty.id}")).status_code == 404

    async def test_adds_module_to_phase_and_longitudinal(
        self, api_client: AsyncClient, world: World
    ) -> None:
        in_phase = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/modules",
            json={
                "code": "HSC102",
                "name": "Physiology",
                "phase_id": str(world.year1.id),
                "credits": "12.5",
                "nqf_level": 5,
                "external_lms_ref": "",
            },
        )
        longitudinal = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/modules",
            json={"code": "HSC300", "name": "Research"},
        )

        assert in_phase.status_code == 201
        body = in_phase.json()
        assert (body["credits"], body["position"], body["external_lms_ref"]) == ("12.5", 2, None)
        assert longitudinal.status_code == 201
        assert longitudinal.json()["phase_id"] is None
        tree = await structure(api_client, world)
        assert [m["code"] for m in tree["phases"][0]["modules"]] == ["HSC101", "HSC102"]
        assert [m["code"] for m in tree["modules_without_phase"]] == ["HSC300"]

    async def test_module_code_is_unique_in_the_version(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/modules",
            json={"code": "hsc101", "name": "Duplicate"},
        )
        renamed = await api_client.patch(
            f"{API}/modules/{world.cardio.id}", json={"code": "HSC101"}
        )

        assert response.status_code == 409
        assert renamed.status_code == 409

    async def test_module_phase_must_be_in_the_same_version(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/modules",
            json={"code": "HSC109", "name": "Wrong phase", "phase_id": str(world.other_phase.id)},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "body",
        [{"nqf_level": 11}, {"credits": "-1"}, {"credits": "1.25"}, {"name": None}, {"code": ""}],
    )
    async def test_module_values_are_validated(
        self, api_client: AsyncClient, world: World, body: dict[str, Any]
    ) -> None:
        response = await api_client.patch(f"{API}/modules/{world.cardio.id}", json=body)

        assert response.status_code == 422

    async def test_updates_module_and_clears_optional_fields(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/modules/{world.cardio.id}",
            json={
                "name": "Cardiovascular system",
                "credits": None,
                "description": "Heart and vessels.",
                "phase_id": None,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Cardiovascular system"
        assert body["credits"] is None
        assert body["nqf_level"] == 5  # not sent, unchanged
        assert body["phase_id"] is None
        tree = await structure(api_client, world)
        assert [m["code"] for m in tree["modules_without_phase"]] == ["HSC201"]

    async def test_deleting_module_removes_its_sessions_and_objectives(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        response = await api_client.delete(f"{API}/modules/{world.cardio.id}")

        assert response.status_code == 204
        for item in (world.cardio, world.lecture, world.lab):
            await db_session.refresh(item)
            assert item.deleted_at == world.cardio.deleted_at
        for objective in (world.cardio_outcome, world.lecture_objective):
            await db_session.refresh(objective)
            assert objective.deleted_at == world.cardio.deleted_at
        tree = await structure(api_client, world)
        assert tree["phases"][1]["modules"] == []
        assert (await api_client.get(f"{API}/learning-events/{world.lab.id}")).status_code == 404
        # The code is free again.
        again = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/modules",
            json={"code": "HSC201", "name": "Cardiovascular"},
        )
        assert again.status_code == 201

    async def test_adds_session_at_the_end_with_format(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/learning-events",
            json={
                "title": "ECG workshop",
                "format_value_id": str(world.lecture_format.id),
                "contact_minutes": 120,
                "week": 5,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["position"] == 2
        assert (body["contact_minutes"], body["self_study_minutes"]) == (120, 0)
        events = (await structure(api_client, world))["phases"][1]["modules"][0]["events"]
        assert [(e["title"], e["format"]) for e in events][-1] == ("ECG workshop", "Lecture")

    async def test_session_format_must_be_a_teaching_method(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/learning-events/{world.lab.id}",
            json={"format_value_id": str(world.theme.id)},
        )
        unknown = await api_client.patch(
            f"{API}/learning-events/{world.lab.id}", json={"format_value_id": MISSING}
        )

        assert response.status_code == 422
        assert unknown.status_code == 422

    async def test_updates_session(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.patch(
            f"{API}/learning-events/{world.lab.id}",
            json={
                "title": "Clinical skills lab",
                "format_value_id": str(world.lecture_format.id),
                "self_study_minutes": 30,
                "week": None,
            },
        )
        cleared = await api_client.patch(
            f"{API}/learning-events/{world.lab.id}", json={"format_value_id": None}
        )
        refused = await api_client.patch(
            f"{API}/learning-events/{world.lab.id}", json={"contact_minutes": None}
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["self_study_minutes"], body["week"]) == (
            "Clinical skills lab",
            30,
            None,
        )
        assert body["format_value_id"] == str(world.lecture_format.id)
        assert cleared.json()["format_value_id"] is None
        assert refused.status_code == 422

    async def test_deleting_session_removes_its_objectives(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        response = await api_client.delete(f"{API}/learning-events/{world.lecture.id}")

        assert response.status_code == 204
        await db_session.refresh(world.lecture_objective)
        assert world.lecture_objective.deleted_at is not None
        await db_session.refresh(world.cardio_outcome)
        assert world.cardio_outcome.deleted_at is None
        events = (await structure(api_client, world))["phases"][1]["modules"][0]["events"]
        assert [e["title"] for e in events] == ["Skills lab"]

    async def test_published_versions_stay_editable_until_publishing_rules(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/modules/{world.published_module.id}", json={"name": "Renamed"}
        )

        assert response.status_code == 200

    async def test_archived_versions_are_read_only(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/modules/{world.archived_module.id}", json={"name": "Renamed"}
        )
        added = await api_client.post(
            f"{API}/curriculum-versions/{world.archived.id}/phases", json={"name": "Year 1"}
        )
        tree = await api_client.get(f"{API}/curriculum-versions/{world.archived.id}/structure")

        assert response.status_code == 409
        assert added.status_code == 409
        assert tree.json()["can_edit"] is False
        assert tree.json()["modules_without_phase"][0]["can_edit"] is False

    async def test_other_programme_is_not_found(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.other_version.id}/phases", json={"name": "Year 1"}
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("PATCH", f"/phases/{MISSING}"),
            ("PATCH", f"/modules/{MISSING}"),
            ("PATCH", "/modules/not-a-uuid"),
            ("PATCH", f"/learning-events/{MISSING}"),
            ("POST", f"/modules/{MISSING}/learning-events"),
        ],
    )
    async def test_unknown_items_are_not_found(
        self, api_client: AsyncClient, method: str, path: str
    ) -> None:
        response = await api_client.request(method, f"{API}{path}", json={"name": "x"})

        assert response.status_code == 404

    async def test_teaching_formats(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(f"{API}/teaching-formats")

        assert response.status_code == 200
        assert response.json() == [
            {"id": str(world.lecture_format.id), "label": "Lecture", "list_name": "Methods"}
        ]


class TestModuleCoordinator:
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

    async def test_structure_flags(self, api_client: AsyncClient, world: World) -> None:
        body = await structure(api_client, world)

        assert body["can_edit"] is False
        [phase] = body["phases"]
        [cardio] = phase["modules"]
        assert cardio["can_edit"] is True
        assert all(event["can_edit"] for event in cardio["events"])

    async def test_edits_own_module(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.patch(
            f"{API}/modules/{world.cardio.id}",
            json={"name": "Cardiology", "phase_id": str(world.year2.id)},  # same phase
        )

        assert response.status_code == 200

    async def test_cannot_move_own_module_to_another_phase(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/modules/{world.cardio.id}", json={"phase_id": str(world.year1.id)}
        )

        assert response.status_code == 403

    async def test_adds_and_deletes_sessions_in_own_module(
        self, api_client: AsyncClient, world: World
    ) -> None:
        added = await api_client.post(
            f"{API}/modules/{world.cardio.id}/learning-events", json={"title": "Tutorial"}
        )
        changed = await api_client.patch(f"{API}/learning-events/{world.lab.id}", json={"week": 3})
        deleted = await api_client.delete(f"{API}/learning-events/{world.lab.id}")

        assert (added.status_code, changed.status_code, deleted.status_code) == (201, 200, 204)

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", "/curriculum-versions/{draft}/phases", {"name": "Year 3"}),
            ("PATCH", "/phases/{year2}", {"name": "Second year"}),
            ("DELETE", "/phases/{year2}", None),
            ("POST", "/curriculum-versions/{draft}/modules", {"code": "X1", "name": "X"}),
            ("DELETE", "/modules/{cardio}", None),
        ],
    )
    async def test_cannot_change_the_programme_structure(
        self,
        api_client: AsyncClient,
        world: World,
        method: str,
        path: str,
        body: dict[str, Any] | None,
    ) -> None:
        url = path.format(draft=world.draft.id, year2=world.year2.id, cardio=world.cardio.id)

        response = await api_client.request(method, f"{API}{url}", json=body)

        assert response.status_code == 403

    async def test_other_modules_are_not_found(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.patch(f"{API}/modules/{world.anatomy.id}", json={"name": "X"})

        assert response.status_code == 404


@pytest.mark.parametrize(
    ("role_key", "scope_of"),
    [
        ("lecturer", lambda w: ScopeRef(ScopeType.LEARNING_EVENT, w.lab.id)),
        ("mapper", lambda w: ScopeRef(ScopeType.PROGRAMME, w.programme.id)),
        ("student", lambda w: INSTANCE),
    ],
)
async def test_roles_without_curriculum_edit_cannot_edit(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,
    role_key: str,
    scope_of: Any,
) -> None:
    await sign_in(api_client, db_session, test_settings, role_key, scope_of(world))
    target = world.published_module if role_key == "student" else world.cardio

    response = await api_client.patch(f"{API}/modules/{target.id}", json={"name": "X"})
    session = await api_client.patch(f"{API}/learning-events/{world.lab.id}", json={"week": 1})

    if role_key == "lecturer":
        # The lecturer sees only their session: the module is not found, the session refused.
        assert response.status_code == 404
        assert session.status_code == 403
    elif role_key == "student":
        # Students see only published versions: drafts are not found.
        assert response.status_code == 403
        assert session.status_code == 404
    else:
        assert response.status_code == 403
        assert session.status_code == 403
