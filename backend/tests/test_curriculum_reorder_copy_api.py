"""Tests for reordering and copying phases, modules and learning events."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    AuditLog,
    LearningEvent,
    MappingLink,
    Objective,
    ObjectiveLink,
    Phase,
    Tagging,
)
from app.models.mapping import MappingSource
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.frameworks import add_item
from app.services.mapping import create_link
from app.services.tagging import add_tag_value, tag_item
from tests.factories import (
    FrameworkFactory,
    LearningEventFactory,
    ModuleFactory,
    PhaseFactory,
    TagListFactory,
)
from tests.test_curriculum_edit_api import (
    API,
    MISSING,
    World,
    programme_scope,
    save,
    sign_in,
    structure,
    world,  # noqa: F401  (fixture)
)


def codes(modules: list[dict[str, Any]]) -> list[str]:
    return [module["code"] for module in modules]


def titles(module: dict[str, Any]) -> list[str]:
    return [event["title"] for event in module["events"]]


async def operations(db: AsyncSession, entity_type: str, operation: str) -> int:
    count = await db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.entity_type == entity_type,
            AuditLog.context["operation"].astext == operation,
        )
    )
    return count or 0


class TestSignInRequired:
    @pytest.mark.parametrize(
        "path",
        [
            f"/phases/{MISSING}/move",
            f"/phases/{MISSING}/copy",
            f"/modules/{MISSING}/move",
            f"/modules/{MISSING}/copy",
            f"/learning-events/{MISSING}/move",
            f"/learning-events/{MISSING}/copy",
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, path: str) -> None:
        response = await api_client.post(f"{API}{path}", json={})
        assert response.status_code == 401


class TestReorder:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    async def test_moves_phase_and_audits_it(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        year3 = PhaseFactory(version=world.draft, name="Year 3", position=2)
        await save(db_session, year3)

        response = await api_client.post(f"{API}/phases/{year3.id}/move", json={"position": 0})

        assert response.status_code == 200
        assert response.json()["position"] == 0
        tree = await structure(api_client, world)
        assert [p["name"] for p in tree["phases"]] == ["Year 3", "Year 1", "Year 2"]
        assert [p["position"] for p in tree["phases"]] == [0, 1, 2]
        assert await operations(db_session, "phases", "curriculum.phase_move") == 3

    async def test_position_must_be_in_range(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        too_far = await api_client.post(f"{API}/phases/{world.year1.id}/move", json={"position": 2})
        negative = await api_client.post(
            f"{API}/phases/{world.year1.id}/move", json={"position": -1}
        )

        assert too_far.status_code == 422
        assert negative.status_code == 422

    async def test_moves_module_within_its_phase_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        physiology = ModuleFactory(
            version=world.draft, phase_id=world.year1.id, code="HSC102", position=5
        )
        await save(db_session, physiology)

        response = await api_client.post(
            f"{API}/modules/{physiology.id}/move", json={"position": 0}
        )
        too_far = await api_client.post(
            f"{API}/modules/{world.cardio.id}/move", json={"position": 1}
        )

        assert response.status_code == 200
        tree = await structure(api_client, world)
        assert codes(tree["phases"][0]["modules"]) == ["HSC102", "HSC101"]
        assert codes(tree["phases"][1]["modules"]) == ["HSC201"]
        assert too_far.status_code == 422  # Year 2 holds one module

    async def test_moves_module_across_phases(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        research = ModuleFactory(version=world.draft, code="HSC300", position=7)
        ethics = ModuleFactory(version=world.draft, code="HSC301", position=8)
        await save(db_session, research, ethics)

        response = await api_client.post(f"{API}/modules/{ethics.id}/move", json={"position": 0})

        assert response.status_code == 200
        assert codes((await structure(api_client, world))["modules_without_phase"]) == [
            "HSC301",
            "HSC300",
        ]

    async def test_moves_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/move", json={"position": 0}
        )

        assert response.status_code == 200
        cardio = (await structure(api_client, world))["phases"][1]["modules"][0]
        assert titles(cardio) == ["Skills lab", "Cardiac cycle"]
        assert (
            await operations(db_session, "learning_events", "curriculum.learning_event_move") == 2
        )

    async def test_archived_version_is_read_only(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.archived_module.id}/move", json={"position": 0}
        )
        copy = await api_client.post(
            f"{API}/modules/{world.archived_module.id}/copy",
            json={"code": "HSC209", "name": "Copy"},
        )

        assert response.status_code == 409
        assert copy.status_code == 409


class TestCopy:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    @pytest.fixture
    async def linked(self, db_session: AsyncSession, world: World) -> Objective:  # noqa: F811
        """A programme outcome the cardio objectives link up to, a mapping, LMS refs
        and taggings (a module tag passed on to the lecture)."""
        db = db_session
        outcome = await add_objective(db, world.draft, "Practise safely.")
        await link_objectives(db, world.cardio_outcome, outcome)
        await link_objectives(db, world.lecture_objective, world.cardio_outcome)
        await link_objectives(db, world.lecture_objective, outcome)
        framework = FrameworkFactory()
        await save(db, framework)
        item = await add_item(db, framework, code="C1", title="Competency 1")
        await create_link(db, world.lecture_objective, item, source=MappingSource.IMPORT)
        world.cardio.external_lms_ref = "LMS-201"
        world.lecture.external_lms_ref = "LMS-201-1"
        world.lecture.format_value_id = world.lecture_format.id
        threads = TagListFactory(key="threads")
        await save(db, threads)
        thread = await add_tag_value(db, threads, "Ethics thread")
        direct = await tag_item(db, thread, world.cardio)
        await tag_item(db, thread, world.lecture, inherited_from=direct)
        await tag_item(db, thread, world.lecture_objective)
        await db.flush()
        return outcome

    async def test_copies_session_after_it_with_objectives(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
        linked: Objective,
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lecture.id}/copy", json={"title": " Cardiac cycle 2 "}
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["title"], body["position"], body["external_lms_ref"]) == (
            "Cardiac cycle 2",
            1,
            None,
        )
        assert body["format_value_id"] == str(world.lecture_format.id)
        cardio = (await structure(api_client, world))["phases"][1]["modules"][0]
        assert titles(cardio) == ["Cardiac cycle", "Cardiac cycle 2", "Skills lab"]
        assert cardio["events"][1]["objective_count"] == 1

        copy_id = uuid.UUID(body["id"])
        [objective] = list(
            await db_session.scalars(
                select(Objective).where(Objective.learning_event_id == copy_id)
            )
        )
        assert objective.text == world.lecture_objective.text
        parents = set(
            await db_session.scalars(
                select(ObjectiveLink.parent_id).where(ObjectiveLink.child_id == objective.id)
            )
        )
        # Same module: the links keep their parents.
        assert parents == {world.cardio_outcome.id, linked.id}
        mapped = await db_session.scalar(
            select(func.count(MappingLink.id)).where(MappingLink.objective_id == objective.id)
        )
        assert mapped == 0
        tagged = await db_session.scalar(
            select(func.count(Tagging.id)).where(
                (Tagging.learning_event_id == copy_id) | (Tagging.objective_id == objective.id)
            )
        )
        assert tagged == 2
        assert (
            await operations(db_session, "learning_events", "curriculum.learning_event_copy") >= 1
        )

    async def test_copies_module_with_sessions_and_remapped_links(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
        linked: Objective,
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy",
            json={"code": "HSC202", "name": "Cardiovascular II"},
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["phase_id"], body["external_lms_ref"]) == (str(world.year2.id), None)
        tree = await structure(api_client, world)
        year2 = tree["phases"][1]["modules"]
        assert codes(year2) == ["HSC201", "HSC202"]
        assert titles(year2[1]) == ["Cardiac cycle", "Skills lab"]
        assert year2[1]["objective_count"] == 1

        copy_id = uuid.UUID(body["id"])
        outcome = await db_session.scalar(select(Objective).where(Objective.module_id == copy_id))
        assert outcome is not None
        lecture = await db_session.scalar(
            select(LearningEvent).where(
                LearningEvent.module_id == copy_id, LearningEvent.title == "Cardiac cycle"
            )
        )
        assert lecture is not None
        objective = await db_session.scalar(
            select(Objective).where(Objective.learning_event_id == lecture.id)
        )
        assert objective is not None
        parents = set(
            await db_session.scalars(
                select(ObjectiveLink.parent_id).where(ObjectiveLink.child_id == objective.id)
            )
        )
        # The module outcome was copied too, so the link points to its copy.
        assert parents == {outcome.id, linked.id}

        module_tag = await db_session.scalar(select(Tagging).where(Tagging.module_id == copy_id))
        lecture_tag = await db_session.scalar(
            select(Tagging).where(Tagging.learning_event_id == lecture.id)
        )
        assert module_tag is not None and lecture_tag is not None
        assert lecture_tag.inherited_from_id == module_tag.id
        assert await operations(db_session, "modules", "curriculum.module_copy") >= 1

    async def test_copies_module_to_another_phase_or_across_phases(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        to_year1 = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy",
            json={"code": "HSC103", "name": "Heart basics", "phase_id": str(world.year1.id)},
        )
        across = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy",
            json={"code": "HSC390", "name": "Heart thread", "phase_id": None},
        )
        wrong = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy",
            json={"code": "HSC391", "name": "Wrong", "phase_id": str(world.other_phase.id)},
        )

        assert (to_year1.status_code, across.status_code, wrong.status_code) == (201, 201, 422)
        tree = await structure(api_client, world)
        assert codes(tree["phases"][0]["modules"]) == ["HSC101", "HSC103"]
        assert codes(tree["modules_without_phase"]) == ["HSC390"]

    async def test_module_copy_needs_a_free_code(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy", json={"code": "hsc101", "name": "Copy"}
        )
        blank = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy", json={"code": " ", "name": "Copy"}
        )

        assert response.status_code == 409
        assert blank.status_code == 422

    async def test_copies_phase_with_its_modules(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.post(
            f"{API}/phases/{world.year1.id}/copy",
            json={"name": "Year 1 (2)", "module_codes": {str(world.anatomy.id): "HSC101B"}},
        )

        assert response.status_code == 201
        assert response.json()["position"] == 1
        tree = await structure(api_client, world)
        assert [p["name"] for p in tree["phases"]] == ["Year 1", "Year 1 (2)", "Year 2"]
        [copied] = tree["phases"][1]["modules"]
        assert (copied["code"], copied["name"]) == ("HSC101B", world.anatomy.name)
        phase = await db_session.get(Phase, uuid.UUID(response.json()["id"]))
        assert phase is not None and phase.kind == world.year1.kind

    @pytest.mark.parametrize(
        ("codes_for", "expected"),
        [
            ({}, 422),  # a code is missing
            ({"anatomy": "HSC201"}, 409),  # taken
            ({"anatomy": "HSC101B", "extra": "HSC101C"}, 422),  # not a module of the phase
        ],
    )
    async def test_phase_copy_needs_one_free_code_per_module(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        codes_for: dict[str, str],
        expected: int,
    ) -> None:
        ids = {"anatomy": str(world.anatomy.id), "extra": str(world.cardio.id)}
        response = await api_client.post(
            f"{API}/phases/{world.year1.id}/copy",
            json={
                "name": "Copy",
                "module_codes": {ids[key]: code for key, code in codes_for.items()},
            },
        )

        assert response.status_code == expected

    async def test_phase_copy_codes_must_differ(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        physiology = ModuleFactory(version=world.draft, phase_id=world.year1.id, code="HSC102")
        await save(db_session, physiology)

        response = await api_client.post(
            f"{API}/phases/{world.year1.id}/copy",
            json={
                "name": "Copy",
                "module_codes": {str(world.anatomy.id): "X1", str(physiology.id): "x1"},
            },
        )

        assert response.status_code == 409

    async def test_deleted_rows_are_not_copied(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        gone = LearningEventFactory(module=world.cardio, title="Gone", position=2)
        await save(db_session, gone)
        gone.soft_delete()
        await db_session.flush()

        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy", json={"code": "HSC202", "name": "Copy"}
        )

        assert response.status_code == 201
        count = await db_session.scalar(
            select(func.count(LearningEvent.id)).where(
                LearningEvent.module_id == uuid.UUID(response.json()["id"])
            )
        )
        assert count == 2


class TestModuleCoordinator:
    @pytest.fixture(autouse=True)
    async def coordinator(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.cardio.id),
        )

    async def test_reorders_and_copies_own_sessions(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        moved = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/move", json={"position": 0}
        )
        copied = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/copy", json={"title": "Skills lab 2"}
        )

        assert (moved.status_code, copied.status_code) == (200, 201)
        [phase] = (await structure(api_client, world))["phases"]
        assert titles(phase["modules"][0]) == ["Skills lab", "Skills lab 2", "Cardiac cycle"]

    async def test_cannot_reorder_or_copy_the_structure(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        responses = [
            await api_client.post(f"{API}/modules/{world.cardio.id}/move", json={"position": 0}),
            await api_client.post(
                f"{API}/modules/{world.cardio.id}/copy", json={"code": "HSC202", "name": "Copy"}
            ),
            await api_client.post(f"{API}/phases/{world.year2.id}/move", json={"position": 0}),
            await api_client.post(f"{API}/phases/{world.year2.id}/copy", json={"name": "Copy"}),
        ]

        assert [r.status_code for r in responses] == [403, 403, 403, 403]

    async def test_other_modules_are_not_found(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.anatomy.id}/move", json={"position": 0}
        )

        assert response.status_code == 404


class TestLecturer:
    async def test_cannot_reorder_or_copy_own_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id),
        )

        moved = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/move", json={"position": 0}
        )
        copied = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/copy", json={"title": "Copy"}
        )

        assert (moved.status_code, copied.status_code) == (403, 403)
