"""Tests for the objective editor API: outcomes and objectives at each level, upward
links, domain and taxonomy level."""

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
    ObjectiveLink,
    Programme,
    TaxonomyLevel,
)
from app.models.curriculum import VersionStatus
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum import add_objective, link_objectives
from tests.factories import (
    CurriculumVersionFactory,
    FacultyFactory,
    LearningEventFactory,
    ModuleFactory,
    ProgrammeFactory,
    TaxonomyScaleFactory,
)
from tests.test_curriculum_edit_api import MISSING, sign_in

API = "/api/v1"


@dataclass
class World:
    programme: Programme
    draft: CurriculumVersion
    published: CurriculumVersion
    cardio: Module
    anatomy: Module
    lecture: LearningEvent  # cardio
    lab: LearningEvent  # cardio
    anatomy_session: LearningEvent
    programme_outcome: Objective
    cardio_outcome: Objective
    anatomy_outcome: Objective
    lecture_objective: Objective  # linked to cardio_outcome and programme_outcome
    published_outcome: Objective
    remember: TaxonomyLevel
    apply: TaxonomyLevel


@pytest.fixture
async def world(db_session: AsyncSession, system_roles: None) -> World:
    db = db_session
    programme = ProgrammeFactory(faculty=FacultyFactory(), code="BHS")
    draft = CurriculumVersionFactory(programme=programme, academic_year=2027)
    published = CurriculumVersionFactory(
        programme=programme, academic_year=2026, status=VersionStatus.PUBLISHED
    )
    db.add_all([programme, draft, published])
    await db.flush()
    cardio = ModuleFactory(version=draft, code="HSC201", position=0)
    anatomy = ModuleFactory(version=draft, code="HSC101", position=1)
    published_module = ModuleFactory(version=published, code="HSC201")
    db.add_all([cardio, anatomy, published_module])
    await db.flush()
    lecture = LearningEventFactory(module=cardio, title="Cardiac cycle", position=0)
    lab = LearningEventFactory(module=cardio, title="Skills lab", position=1)
    anatomy_session = LearningEventFactory(module=anatomy, title="Bones", position=0)
    db.add_all([lecture, lab, anatomy_session])
    await db.flush()

    programme_outcome = await add_objective(db, draft, "Practise safely.")
    cardio_outcome = await add_objective(db, cardio, "Interpret cardiac investigations.")
    anatomy_outcome = await add_objective(db, anatomy, "Name the bones.")
    lecture_objective = await add_objective(db, lecture, "Describe the cardiac cycle.")
    published_outcome = await add_objective(db, published, "Published outcome.")
    await link_objectives(db, lecture_objective, cardio_outcome)
    await link_objectives(db, lecture_objective, programme_outcome)

    scale = TaxonomyScaleFactory(key="bloom", name="Bloom")
    db.add(scale)
    await db.flush()
    remember = TaxonomyLevel(scale_id=scale.id, position=0, name="Remember")
    apply = TaxonomyLevel(scale_id=scale.id, position=1, name="Apply")
    db.add_all([remember, apply])
    await db.flush()
    return World(
        programme=programme,
        draft=draft,
        published=published,
        cardio=cardio,
        anatomy=anatomy,
        lecture=lecture,
        lab=lab,
        anatomy_session=anatomy_session,
        programme_outcome=programme_outcome,
        cardio_outcome=cardio_outcome,
        anatomy_outcome=anatomy_outcome,
        lecture_objective=lecture_objective,
        published_outcome=published_outcome,
        remember=remember,
        apply=apply,
    )


def programme_scope(world: World) -> ScopeRef:
    return ScopeRef(ScopeType.PROGRAMME, world.programme.id)


async def parents_of(db: AsyncSession, objective: Objective) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(ObjectiveLink.parent_id).where(ObjectiveLink.child_id == objective.id)
    )
    return set(rows)


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", f"/curriculum-versions/{MISSING}/outcomes"),
            ("POST", f"/modules/{MISSING}/outcomes"),
            ("POST", f"/learning-events/{MISSING}/objectives"),
            ("PATCH", f"/objectives/{MISSING}"),
            ("DELETE", f"/objectives/{MISSING}"),
            ("GET", f"/modules/{MISSING}/outcome-link-options"),
            ("GET", f"/learning-events/{MISSING}/objective-link-options"),
            ("GET", "/taxonomy-scales"),
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

    async def test_read_flags_and_taxonomy_level(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        world.lecture_objective.taxonomy_level_id = world.apply.id
        await db_session.flush()

        structure = (
            await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/structure")
        ).json()
        module = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        event = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        published = (
            await api_client.get(f"{API}/curriculum-versions/{world.published.id}/structure")
        ).json()

        assert structure["can_edit_outcomes"] is True
        assert module["can_edit_objectives"] is True
        assert event["can_edit_objectives"] is True
        assert event["objectives"][0]["taxonomy_level_id"] == str(world.apply.id)
        assert published["can_edit_outcomes"] is False

    async def test_adds_programme_outcome_and_audits_it(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcomes",
            json={"text": "  Communicate clearly. ", "domain": "skill"},
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["text"], body["domain"], body["level"], body["status"]) == (
            "Communicate clearly.",
            "skill",
            "programme",
            "draft",
        )
        assert body["position"] == 1
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "objectives",
                AuditLog.action == "create",
                AuditLog.entity_id == uuid.UUID(body["id"]),
            )
        )
        assert entry is not None
        assert entry.context["operation"] == "curriculum.objective_create"
        assert entry.actor_id is not None

    async def test_programme_outcomes_cannot_link_upward(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcomes",
            json={"text": "X", "parent_ids": [str(world.programme_outcome.id)]},
        )

        assert response.status_code == 422

    async def test_adds_module_outcome_linked_to_a_programme_outcome(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes",
            json={
                "text": "Explain haemodynamics.",
                "domain": "knowledge",
                "taxonomy_level_id": str(world.remember.id),
                "status": "approved",
                "parent_ids": [str(world.programme_outcome.id)],
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["level"] == "module"
        assert body["parent_ids"] == [str(world.programme_outcome.id)]
        assert body["taxonomy_level_id"] == str(world.remember.id)
        assert body["status"] == "approved"

    async def test_module_outcome_cannot_link_to_a_sibling_module_outcome(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes",
            json={"text": "X", "parent_ids": [str(world.anatomy_outcome.id)]},
        )

        assert response.status_code == 422

    async def test_adds_session_objective_linked_to_module_and_programme_outcomes(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives",
            json={
                "text": "Perform an ECG.",
                "domain": "skill",
                "parent_ids": [str(world.cardio_outcome.id), str(world.programme_outcome.id)],
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["level"] == "learning_event"
        assert set(body["parent_ids"]) == {
            str(world.cardio_outcome.id),
            str(world.programme_outcome.id),
        }

    async def test_session_objective_cannot_link_to_another_modules_outcome(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives",
            json={"text": "X", "parent_ids": [str(world.anatomy_outcome.id)]},
        )

        assert response.status_code == 422

    async def test_blank_text_and_unknown_taxonomy_level_are_refused(
        self, api_client: AsyncClient, world: World
    ) -> None:
        url = f"{API}/learning-events/{world.lab.id}/objectives"

        blank = await api_client.post(url, json={"text": "   "})
        unknown = await api_client.post(
            url, json={"text": "X", "taxonomy_level_id": str(uuid.uuid4())}
        )
        bad_domain = await api_client.post(url, json={"text": "X", "domain": "magic"})

        assert (blank.status_code, unknown.status_code, bad_domain.status_code) == (422, 422, 422)

    async def test_new_objectives_go_to_the_end(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lecture.id}/objectives", json={"text": "Second."}
        )

        assert response.json()["position"] == world.lecture_objective.position + 1

    async def test_updates_fields_and_replaces_links(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        response = await api_client.patch(
            f"{API}/objectives/{world.lecture_objective.id}",
            json={
                "text": "Explain the cardiac cycle.",
                "domain": "attitude",
                "taxonomy_level_id": str(world.apply.id),
                "status": "approved",
                "parent_ids": [str(world.cardio_outcome.id)],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "Explain the cardiac cycle."
        assert body["parent_ids"] == [str(world.cardio_outcome.id)]
        assert await parents_of(db_session, world.lecture_objective) == {world.cardio_outcome.id}
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "objective_links", AuditLog.action == "delete"
            )
        )
        assert entry is not None
        assert entry.context["operation"] == "curriculum.objective_update"

    async def test_omitted_fields_and_links_stay_and_null_clears(
        self, api_client: AsyncClient, world: World
    ) -> None:
        url = f"{API}/objectives/{world.lecture_objective.id}"
        await api_client.patch(
            url, json={"domain": "skill", "taxonomy_level_id": str(world.apply.id)}
        )

        kept = await api_client.patch(url, json={"status": "retired"})
        cleared = await api_client.patch(
            url, json={"domain": None, "taxonomy_level_id": None, "parent_ids": []}
        )

        assert kept.json()["domain"] == "skill"
        assert kept.json()["taxonomy_level_id"] == str(world.apply.id)
        assert len(kept.json()["parent_ids"]) == 2
        assert cleared.json()["domain"] is None
        assert cleared.json()["taxonomy_level_id"] is None
        assert cleared.json()["parent_ids"] == []

    async def test_clearing_text_or_status_is_refused(
        self, api_client: AsyncClient, world: World
    ) -> None:
        url = f"{API}/objectives/{world.lecture_objective.id}"

        text = await api_client.patch(url, json={"text": None})
        status = await api_client.patch(url, json={"status": None})

        assert (text.status_code, status.status_code) == (422, 422)

    async def test_deletes_objective_softly(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.delete(f"{API}/objectives/{world.lecture_objective.id}")

        assert response.status_code == 204
        assert world.lecture_objective.deleted_at is not None
        event = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        assert event["objectives"] == []
        again = await api_client.delete(f"{API}/objectives/{world.lecture_objective.id}")
        assert again.status_code == 404

    async def test_published_versions_are_read_only(
        self, api_client: AsyncClient, world: World
    ) -> None:
        added = await api_client.post(
            f"{API}/curriculum-versions/{world.published.id}/outcomes", json={"text": "X"}
        )
        changed = await api_client.patch(
            f"{API}/objectives/{world.published_outcome.id}", json={"text": "Y"}
        )
        deleted = await api_client.delete(f"{API}/objectives/{world.published_outcome.id}")

        assert (added.status_code, changed.status_code, deleted.status_code) == (409, 409, 409)

    async def test_link_options(self, api_client: AsyncClient, world: World) -> None:
        for_module = await api_client.get(f"{API}/modules/{world.cardio.id}/outcome-link-options")
        for_session = await api_client.get(
            f"{API}/learning-events/{world.lab.id}/objective-link-options"
        )

        assert [o["id"] for o in for_module.json()] == [str(world.programme_outcome.id)]
        assert for_module.json()[0]["module_code"] is None
        assert [(o["id"], o["module_code"]) for o in for_session.json()] == [
            (str(world.programme_outcome.id), None),
            (str(world.cardio_outcome.id), "HSC201"),
        ]

    async def test_unknown_items_are_not_found(self, api_client: AsyncClient) -> None:
        changed = await api_client.patch(f"{API}/objectives/{MISSING}", json={"text": "X"})
        added = await api_client.post(f"{API}/modules/{MISSING}/outcomes", json={"text": "X"})

        assert (changed.status_code, added.status_code) == (404, 404)

    async def test_lists_taxonomy_scales_with_levels(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(f"{API}/taxonomy-scales")

        assert response.status_code == 200
        [bloom] = [s for s in response.json() if s["key"] == "bloom"]
        assert [level["name"] for level in bloom["levels"]] == ["Remember", "Apply"]
        assert bloom["levels"][1]["id"] == str(world.apply.id)


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

    async def test_flags(self, api_client: AsyncClient, world: World) -> None:
        structure = (
            await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/structure")
        ).json()
        module = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        event = (await api_client.get(f"{API}/learning-events/{world.lab.id}")).json()

        assert structure["can_edit_outcomes"] is False
        assert module["can_edit_objectives"] is True
        assert event["can_edit_objectives"] is True

    async def test_edits_own_module_outcomes_and_session_objectives(
        self, api_client: AsyncClient, world: World
    ) -> None:
        outcome = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes", json={"text": "New outcome."}
        )
        objective = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives",
            json={"text": "New objective.", "parent_ids": [outcome.json()["id"]]},
        )
        changed = await api_client.patch(
            f"{API}/objectives/{world.cardio_outcome.id}", json={"domain": "knowledge"}
        )
        deleted = await api_client.delete(f"{API}/objectives/{objective.json()['id']}")

        assert (outcome.status_code, objective.status_code) == (201, 201)
        assert (changed.status_code, deleted.status_code) == (200, 204)

    async def test_cannot_change_programme_outcomes(
        self, api_client: AsyncClient, world: World
    ) -> None:
        added = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcomes", json={"text": "X"}
        )
        changed = await api_client.patch(
            f"{API}/objectives/{world.programme_outcome.id}", json={"text": "X"}
        )

        # They see the version but not its outcomes: adding is refused, changing is not found.
        assert (added.status_code, changed.status_code) == (403, 404)

    async def test_other_modules_are_not_found(self, api_client: AsyncClient, world: World) -> None:
        responses = [
            await api_client.post(f"{API}/modules/{world.anatomy.id}/outcomes", json={"text": "X"}),
            await api_client.patch(
                f"{API}/objectives/{world.anatomy_outcome.id}", json={"text": "X"}
            ),
            await api_client.post(
                f"{API}/learning-events/{world.anatomy_session.id}/objectives",
                json={"text": "X"},
            ),
        ]

        assert [r.status_code for r in responses] == [404, 404, 404]

    async def test_cannot_link_to_programme_outcomes_they_do_not_see(
        self, api_client: AsyncClient, world: World
    ) -> None:
        options = await api_client.get(f"{API}/modules/{world.cardio.id}/outcome-link-options")
        refused = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes",
            json={"text": "X", "parent_ids": [str(world.programme_outcome.id)]},
        )

        assert options.json() == []
        assert refused.status_code == 422

    async def test_links_they_cannot_see_are_kept_when_they_change_the_others(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        # The lecture objective is linked to the module outcome and a programme outcome.
        response = await api_client.patch(
            f"{API}/objectives/{world.lecture_objective.id}", json={"parent_ids": []}
        )

        assert response.status_code == 200
        assert response.json()["parent_ids"] == [str(world.programme_outcome.id)]
        assert await parents_of(db_session, world.lecture_objective) == {world.programme_outcome.id}


class TestLecturer:
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
            ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id),
        )

    async def test_edits_objectives_of_own_session_only(
        self, api_client: AsyncClient, world: World
    ) -> None:
        event = (await api_client.get(f"{API}/learning-events/{world.lab.id}")).json()
        added = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives",
            json={"text": "Take a pulse.", "domain": "skill"},
        )
        changed = await api_client.patch(
            f"{API}/objectives/{added.json()['id']}", json={"text": "Take a pulse and BP."}
        )
        other = await api_client.post(
            f"{API}/learning-events/{world.lecture.id}/objectives", json={"text": "X"}
        )
        module_outcome = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcomes", json={"text": "X"}
        )

        assert event["can_edit_objectives"] is True
        assert (added.status_code, changed.status_code) == (201, 200)
        assert other.status_code == 404
        assert module_outcome.status_code == 404

    async def test_sees_no_link_options_and_cannot_choose_links(
        self, api_client: AsyncClient, world: World
    ) -> None:
        options = await api_client.get(
            f"{API}/learning-events/{world.lab.id}/objective-link-options"
        )
        refused = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objectives",
            json={"text": "X", "parent_ids": [str(world.cardio_outcome.id)]},
        )

        assert options.json() == []
        assert refused.status_code == 422


@pytest.mark.parametrize(
    ("role_key", "scope_of", "expected"),
    [
        ("mapper", lambda w: ScopeRef(ScopeType.PROGRAMME, w.programme.id), 403),
        # Students see published versions only, so drafts are not found for them.
        ("student", lambda _w: INSTANCE, 404),
    ],
)
async def test_roles_without_objectives_edit_cannot_edit(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,
    role_key: str,
    scope_of: Any,
    expected: int,
) -> None:
    await sign_in(api_client, db_session, test_settings, role_key, scope_of(world))

    response = await api_client.post(
        f"{API}/learning-events/{world.lab.id}/objectives", json={"text": "X"}
    )
    structure = await api_client.get(f"{API}/curriculum-versions/{world.published.id}/structure")

    assert response.status_code == expected
    assert structure.json()["can_edit_outcomes"] is False
