"""Tests for the tag list API (curriculum office) and tagging items with inheritance."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    AuditLog,
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    Programme,
    Tagging,
    TagList,
    TagValue,
)
from app.models.curriculum import VersionStatus
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.tagging import add_tag_value, set_teaching_format, tag_item
from tests.factories import (
    CurriculumVersionFactory,
    FacultyFactory,
    LearningEventFactory,
    ModuleFactory,
    ProgrammeFactory,
    TagListFactory,
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
    bones: LearningEvent  # anatomy
    programme_outcome: Objective
    cardio_outcome: Objective  # linked to programme_outcome
    lecture_objective: Objective  # linked to cardio_outcome and programme_outcome
    anatomy_outcome: Objective  # linked to programme_outcome
    published_module: Module
    methods: TagList  # teaching methods, all item types
    pbl: TagValue
    lecture_value: TagValue
    themes: TagList  # themes, objectives only
    ethics: TagValue


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
    cardio = ModuleFactory(version=draft, code="HSC201", name="Cardiology", position=0)
    anatomy = ModuleFactory(version=draft, code="HSC101", name="Anatomy", position=1)
    published_module = ModuleFactory(version=published, code="HSC201")
    db.add_all([cardio, anatomy, published_module])
    await db.flush()
    lecture = LearningEventFactory(module=cardio, title="Cardiac cycle", position=0)
    lab = LearningEventFactory(module=cardio, title="Skills lab", position=1)
    bones = LearningEventFactory(module=anatomy, title="Bones", position=0)
    db.add_all([lecture, lab, bones])
    await db.flush()
    programme_outcome = await add_objective(db, draft, "Practise safely.")
    cardio_outcome = await add_objective(db, cardio, "Interpret cardiac investigations.")
    anatomy_outcome = await add_objective(db, anatomy, "Name the bones.")
    lecture_objective = await add_objective(db, lecture, "Describe the cardiac cycle.")
    await link_objectives(db, cardio_outcome, programme_outcome)
    await link_objectives(db, anatomy_outcome, programme_outcome)
    await link_objectives(db, lecture_objective, cardio_outcome)
    await link_objectives(db, lecture_objective, programme_outcome)

    methods = TagListFactory(key="methods", name="Teaching methods", kind="teaching_method")
    themes = TagListFactory(key="themes", name="Themes", kind="theme", entity_types=["objective"])
    db.add_all([methods, themes])
    await db.flush()
    pbl = await add_tag_value(db, methods, "PBL", code="pbl")
    lecture_value = await add_tag_value(db, methods, "Lecture", position=1)
    ethics = await add_tag_value(db, themes, "Ethics")
    return World(
        programme=programme,
        draft=draft,
        published=published,
        cardio=cardio,
        anatomy=anatomy,
        lecture=lecture,
        lab=lab,
        bones=bones,
        programme_outcome=programme_outcome,
        cardio_outcome=cardio_outcome,
        lecture_objective=lecture_objective,
        anatomy_outcome=anatomy_outcome,
        published_module=published_module,
        methods=methods,
        pbl=pbl,
        lecture_value=lecture_value,
        themes=themes,
        ethics=ethics,
    )


def programme_scope(world: World) -> ScopeRef:
    return ScopeRef(ScopeType.PROGRAMME, world.programme.id)


def module_scope(module: Module) -> ScopeRef:
    return ScopeRef(ScopeType.MODULE, module.id)


def tags_path(kind: str, item_id: uuid.UUID) -> str:
    return f"{API}/curriculum-items/{kind}/{item_id}/tags"


def preview_path(kind: str, item_id: uuid.UUID) -> str:
    return f"{API}/curriculum-items/{kind}/{item_id}/tag-preview"


async def add(
    client: AsyncClient, kind: str, item_id: uuid.UUID, value: TagValue, *, inherit: bool = False
) -> Any:
    response = await client.post(
        tags_path(kind, item_id), json={"tag_value_id": str(value.id), "inherit": inherit}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def event_tags(client: AsyncClient, event: LearningEvent) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/learning-events/{event.id}")
    assert response.status_code == 200
    tags: list[dict[str, Any]] = response.json()["tags"]
    return tags


async def operations(db: AsyncSession, operation: str) -> int:
    count = await db.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.context["operation"].astext == operation)
    )
    return count or 0


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/tag-lists"),
            ("POST", "/tag-lists"),
            ("PATCH", f"/tag-lists/{MISSING}"),
            ("DELETE", f"/tag-lists/{MISSING}"),
            ("POST", f"/tag-lists/{MISSING}/values"),
            ("PATCH", f"/tag-values/{MISSING}"),
            ("DELETE", f"/tag-values/{MISSING}"),
            ("GET", f"/curriculum-items/module/{MISSING}/tag-preview"),
            ("POST", f"/curriculum-items/module/{MISSING}/tags"),
            ("DELETE", f"/taggings/{MISSING}"),
        ],
    )
    async def test_requires_a_session(
        self, api_client: AsyncClient, method: str, path: str
    ) -> None:
        response = await api_client.request(method, f"{API}{path}")
        assert response.status_code == 401


class TestManagingLists:
    async def test_curriculum_office_creates_and_changes_a_list(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        created = await api_client.post(
            f"{API}/tag-lists",
            json={"key": "threads", "name": "Threads", "kind": "thread", "description": "Long"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["entity_types"] == ["module", "learning_event", "objective"]
        assert body["is_active"] is True
        assert body["values"] == []

        changed = await api_client.patch(
            f"{API}/tag-lists/{body['id']}",
            json={
                "name": "Longitudinal threads",
                "entity_types": ["objective"],
                "is_active": False,
            },
        )
        assert changed.status_code == 200
        assert changed.json()["name"] == "Longitudinal threads"
        assert changed.json()["entity_types"] == ["objective"]
        assert changed.json()["is_active"] is False
        assert changed.json()["key"] == "threads"
        assert await operations(db_session, "taglist.create") == 1
        assert await operations(db_session, "taglist.update") == 1

    async def test_key_is_unique_and_well_formed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        clash = await api_client.post(f"{API}/tag-lists", json={"key": "themes", "name": "Again"})
        assert clash.status_code == 409
        bad = await api_client.post(f"{API}/tag-lists", json={"key": "Not OK", "name": "Bad"})
        assert bad.status_code == 422

    async def test_key_and_kind_cannot_change(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await api_client.patch(
            f"{API}/tag-lists/{world.themes.id}", json={"key": "other", "kind": "custom"}
        )
        assert response.status_code == 422

    async def test_values_are_added_changed_and_deleted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        added = await api_client.post(
            f"{API}/tag-lists/{world.methods.id}/values",
            json={"label": "  TBL  ", "code": "tbl", "description": "Team-based"},
        )
        assert added.status_code == 201
        value = added.json()
        assert value["label"] == "TBL"
        assert value["position"] == 2  # after PBL (0) and Lecture (1)

        assert (
            await api_client.post(
                f"{API}/tag-lists/{world.methods.id}/values", json={"label": "TBL"}
            )
        ).status_code == 409
        assert (
            await api_client.post(
                f"{API}/tag-lists/{world.methods.id}/values", json={"label": "Other", "code": "tbl"}
            )
        ).status_code == 409

        changed = await api_client.patch(
            f"{API}/tag-values/{value['id']}",
            json={"label": "Team-based learning", "code": None, "is_active": False},
        )
        assert changed.status_code == 200
        assert changed.json()["label"] == "Team-based learning"
        assert changed.json()["code"] is None
        assert changed.json()["is_active"] is False
        # A label left out stays; the label of another value is a conflict.
        assert (
            await api_client.patch(f"{API}/tag-values/{value['id']}", json={"description": "x"})
        ).json()["label"] == "Team-based learning"
        assert (
            await api_client.patch(f"{API}/tag-values/{value['id']}", json={"label": "PBL"})
        ).status_code == 409
        assert (
            await api_client.patch(f"{API}/tag-values/{value['id']}", json={"code": "pbl"})
        ).status_code == 409

        assert (await api_client.delete(f"{API}/tag-values/{value['id']}")).status_code == 204
        assert (await api_client.delete(f"{API}/tag-values/{value['id']}")).status_code == 404
        assert await operations(db_session, "tagvalue.create") == 1
        assert await operations(db_session, "tagvalue.delete") == 1

    async def test_a_tag_in_use_cannot_be_deleted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await tag_item(db_session, world.pbl, world.cardio)
        await set_teaching_format(db_session, world.lab, world.lecture_value)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        assert (await api_client.delete(f"{API}/tag-values/{world.pbl.id}")).status_code == 409
        # A session's format counts as use too.
        assert (
            await api_client.delete(f"{API}/tag-values/{world.lecture_value.id}")
        ).status_code == 409
        assert (await api_client.delete(f"{API}/tag-lists/{world.methods.id}")).status_code == 409
        # Making it inactive is allowed.
        inactive = await api_client.patch(
            f"{API}/tag-values/{world.pbl.id}", json={"is_active": False}
        )
        assert inactive.status_code == 200

    async def test_an_unused_list_is_deleted_with_its_values(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (await api_client.delete(f"{API}/tag-lists/{world.themes.id}")).status_code == 204
        assert (await api_client.delete(f"{API}/tag-lists/{world.themes.id}")).status_code == 404
        assert (await api_client.delete(f"{API}/tag-values/{world.ethics.id}")).status_code == 404
        listing = await api_client.get(f"{API}/tag-lists")
        assert [item["key"] for item in listing.json()] == ["methods"]
        # One entry for the list and one for its value.
        assert await operations(db_session, "taglist.delete") == 2

    async def test_unknown_list_or_value(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (await api_client.patch(f"{API}/tag-lists/{MISSING}", json={})).status_code == 404
        assert (
            await api_client.post(f"{API}/tag-lists/{MISSING}/values", json={"label": "X"})
        ).status_code == 404
        assert (await api_client.patch(f"{API}/tag-values/{MISSING}", json={})).status_code == 404

    async def test_listing_shows_usage_to_managers_only_active_to_others(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await tag_item(db_session, world.pbl, world.cardio)
        world.lecture_value.is_active = False
        world.themes.is_active = False
        await db_session.flush()

        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        managed = {item["key"]: item for item in (await api_client.get(f"{API}/tag-lists")).json()}
        assert set(managed) == {"methods", "themes"}
        values = {v["label"]: v for v in managed["methods"]["values"]}
        assert values["PBL"]["usage_count"] == 1
        assert values["Lecture"]["is_active"] is False

        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        others = {item["key"]: item for item in (await api_client.get(f"{API}/tag-lists")).json()}
        assert set(others) == {"methods"}
        assert [v["label"] for v in others["methods"]["values"]] == ["PBL"]
        assert others["methods"]["values"][0]["usage_count"] == 0

    @pytest.mark.parametrize(
        "role_key", ["programme_director", "module_coordinator", "lecturer", None]
    )
    async def test_other_roles_cannot_manage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        role_key: str | None,
    ) -> None:
        scope = (
            module_scope(world.cardio)
            if role_key in ("module_coordinator", "lecturer")
            else programme_scope(world)
        )
        await sign_in(api_client, db_session, test_settings, role_key, scope)
        assert (
            await api_client.post(f"{API}/tag-lists", json={"key": "x", "name": "X"})
        ).status_code == 403
        assert (
            await api_client.patch(f"{API}/tag-lists/{world.themes.id}", json={})
        ).status_code == 403
        assert (await api_client.delete(f"{API}/tag-lists/{world.themes.id}")).status_code == 403
        assert (
            await api_client.post(f"{API}/tag-lists/{world.themes.id}/values", json={"label": "X"})
        ).status_code == 403
        assert (
            await api_client.patch(f"{API}/tag-values/{world.ethics.id}", json={})
        ).status_code == 403
        assert (await api_client.delete(f"{API}/tag-values/{world.ethics.id}")).status_code == 403


class TestTaggingAModule:
    async def test_tag_with_inheritance_preview_and_source(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )

        preview = await api_client.get(
            preview_path("module", world.cardio.id), params={"tag_value_id": str(world.pbl.id)}
        )
        assert preview.status_code == 200
        body = preview.json()
        assert body["label"] == "PBL"
        assert body["list_name"] == "Teaching methods"
        assert body["item_has_tag"] is False
        assert [(i["name"], i["status"], i["module_code"]) for i in body["items"]] == [
            ("Cardiac cycle", "new", "HSC201"),
            ("Skills lab", "new", "HSC201"),
        ]
        # The preview saves nothing.
        assert await db_session.scalar(select(func.count(Tagging.id))) == 0

        applied = await add(api_client, "module", world.cardio.id, world.pbl, inherit=True)
        assert applied["inherited_count"] == 2
        assert [t["label"] for t in applied["tags"]] == ["PBL"]
        assert applied["tags"][0]["direct_tagging_id"] is not None
        assert applied["tags"][0]["sources"] == []

        tags = await event_tags(api_client, world.lecture)
        assert len(tags) == 1
        assert tags[0]["label"] == "PBL"
        assert tags[0]["list_name"] == "Teaching methods"
        assert tags[0]["direct_tagging_id"] is None
        assert tags[0]["sources"] == [
            {"item_type": "module", "item_id": str(world.cardio.id), "name": "HSC201 Cardiology"}
        ]
        # One audit entry for the direct tagging and one for each inherited one.
        assert await operations(db_session, "tagging.add") == 3

    async def test_tag_without_inheritance_touches_only_the_module(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        applied = await add(api_client, "module", world.cardio.id, world.pbl)

        assert applied["inherited_count"] == 0
        assert await event_tags(api_client, world.lecture) == []
        module = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        assert [t["label"] for t in module["tags"]] == ["PBL"]
        assert module["can_edit_tags"] is True

    async def test_remove_direct_tag_takes_inherited_ones_with_it(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        applied = await add(api_client, "module", world.cardio.id, world.pbl, inherit=True)
        direct_id = applied["tags"][0]["direct_tagging_id"]

        inherited = await db_session.scalar(
            select(Tagging).where(
                Tagging.learning_event_id == world.lecture.id,
                Tagging.inherited_from_id.is_not(None),
            )
        )
        assert inherited is not None
        refused = await api_client.delete(f"{API}/taggings/{inherited.id}")
        assert refused.status_code == 422

        assert (await api_client.delete(f"{API}/taggings/{direct_id}")).status_code == 204
        assert await event_tags(api_client, world.lecture) == []
        assert await db_session.scalar(select(func.count(Tagging.id))) == 0
        assert await operations(db_session, "tagging.remove") == 3
        # Each removed row is in the audit log, inherited ones included.
        deleted = await db_session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.entity_type == "taggings", AuditLog.action == "delete"
            )
        )
        assert deleted == 3

    async def test_preview_marks_items_that_have_the_tag_or_cannot_take_it(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await tag_item(db_session, world.pbl, world.lab)
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        body = (
            await api_client.get(
                preview_path("module", world.cardio.id), params={"tag_value_id": str(world.pbl.id)}
            )
        ).json()
        assert {i["name"]: i["status"] for i in body["items"]} == {
            "Cardiac cycle": "new",
            "Skills lab": "has_tag",
        }
        applied = await add(api_client, "module", world.cardio.id, world.pbl, inherit=True)
        assert applied["inherited_count"] == 1

        # A list that does not apply to sessions: they are listed, not tagged.
        world.methods.entity_types = ["module"]
        await db_session.flush()
        await tag_item(db_session, world.lecture_value, world.anatomy)
        body = (
            await api_client.get(
                preview_path("module", world.cardio.id),
                params={"tag_value_id": str(world.lecture_value.id)},
            )
        ).json()
        assert {i["status"] for i in body["items"]} == {"not_applicable"}
        applied = await add(
            api_client, "module", world.cardio.id, world.lecture_value, inherit=True
        )
        assert applied["inherited_count"] == 0

    async def test_tagging_twice_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        await add(api_client, "module", world.cardio.id, world.pbl)
        again = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": str(world.pbl.id)}
        )
        assert again.status_code == 409
        preview = await api_client.get(
            preview_path("module", world.cardio.id), params={"tag_value_id": str(world.pbl.id)}
        )
        assert preview.json()["item_has_tag"] is True

    async def test_an_inactive_or_unknown_tag_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        world.pbl.is_active = False
        await db_session.flush()
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        inactive = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": str(world.pbl.id)}
        )
        assert inactive.status_code == 422
        unknown = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": MISSING}
        )
        assert unknown.status_code == 422
        assert (
            await api_client.get(
                preview_path("module", world.cardio.id), params={"tag_value_id": MISSING}
            )
        ).status_code == 422

    async def test_a_list_that_does_not_apply_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        response = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": str(world.ethics.id)}
        )
        assert response.status_code == 422


class TestTaggingSessionsAndObjectives:
    async def test_tag_a_session_directly(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        applied = await add(api_client, "learning_event", world.lab.id, world.lecture_value)
        assert applied["tags"][0]["label"] == "Lecture"
        # A session passes its tag on to nothing.
        preview = await api_client.get(
            preview_path("learning_event", world.lab.id),
            params={"tag_value_id": str(world.pbl.id)},
        )
        assert preview.json()["items"] == []
        body = (await api_client.get(f"{API}/learning-events/{world.lab.id}")).json()
        assert body["can_edit_tags"] is True
        assert [t["label"] for t in body["tags"]] == ["Lecture"]

    async def test_programme_outcome_flows_down_through_the_links(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        preview = await api_client.get(
            preview_path("objective", world.programme_outcome.id),
            params={"tag_value_id": str(world.ethics.id)},
        )
        body = preview.json()
        # Module outcomes first, then session objectives, each once.
        assert [(i["level"], i["module_code"], i["status"]) for i in body["items"]] == [
            ("module", "HSC201", "new"),
            ("module", "HSC101", "new"),
            ("learning_event", "HSC201", "new"),
        ]

        applied = await add(
            api_client, "objective", world.programme_outcome.id, world.ethics, inherit=True
        )
        assert applied["inherited_count"] == 3

        outcomes = (
            await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/outcomes")
        ).json()
        assert outcomes[0]["tags"][0]["direct_tagging_id"] is not None
        cardio = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        sources = cardio["outcomes"][0]["tags"][0]["sources"]
        assert [s["name"] for s in sources] == ["Practise safely."]
        assert sources[0]["item_type"] == "objective"
        lecture = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        assert lecture["objectives"][0]["tags"][0]["sources"][0]["name"] == "Practise safely."

    async def test_a_tag_from_two_sources_shows_both(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        await add(api_client, "objective", world.programme_outcome.id, world.ethics, inherit=True)
        await add(api_client, "objective", world.cardio_outcome.id, world.ethics, inherit=True)

        lecture = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        tag = lecture["objectives"][0]["tags"]
        assert len(tag) == 1
        assert sorted(s["name"] for s in tag[0]["sources"]) == [
            "Interpret cardiac investigations.",
            "Practise safely.",
        ]
        # The module outcome has the tag directly and from the programme outcome.
        cardio = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        outcome = cardio["outcomes"][0]["tags"][0]
        assert outcome["direct_tagging_id"] is not None
        assert [s["name"] for s in outcome["sources"]] == ["Practise safely."]

    async def test_a_source_that_was_deleted_is_not_shown(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        await add(api_client, "objective", world.cardio_outcome.id, world.ethics, inherit=True)
        world.cardio_outcome.soft_delete()
        await db_session.flush()
        lecture = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        assert lecture["objectives"][0]["tags"] == []

    async def test_coordinator_tags_module_outcomes_not_programme_outcomes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        applied = await add(
            api_client, "objective", world.cardio_outcome.id, world.ethics, inherit=True
        )
        assert applied["inherited_count"] == 1
        denied = await api_client.post(
            tags_path("objective", world.programme_outcome.id),
            json={"tag_value_id": str(world.ethics.id)},
        )
        assert denied.status_code == 404
        # Programme outcomes are not visible to them, so they are not found (ADR 027),
        # nor is an outcome of a module they have no role in.
        hidden = await api_client.post(
            tags_path("objective", world.anatomy_outcome.id),
            json={"tag_value_id": str(world.ethics.id)},
        )
        assert hidden.status_code == 404

    async def test_structure_says_who_may_tag_programme_outcomes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        draft = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/structure")
        assert draft.json()["can_edit_outcome_tags"] is True
        published = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/structure"
        )
        assert published.json()["can_edit_outcome_tags"] is False


class TestWhoMayTag:
    async def test_a_lecturer_cannot_tag(
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
        denied = await api_client.post(
            tags_path("learning_event", world.lecture.id),
            json={"tag_value_id": str(world.pbl.id)},
        )
        assert denied.status_code == 403
        body = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        assert body["can_edit_tags"] is False
        # A session the lecturer does not see is not found.
        hidden = await api_client.post(
            tags_path("learning_event", world.bones.id), json={"tag_value_id": str(world.pbl.id)}
        )
        assert hidden.status_code == 404

    async def test_published_versions_are_read_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        response = await api_client.post(
            tags_path("module", world.published_module.id),
            json={"tag_value_id": str(world.pbl.id)},
        )
        assert response.status_code == 409
        module = (await api_client.get(f"{API}/modules/{world.published_module.id}")).json()
        assert module["can_edit_tags"] is False

        # A tag set while it was a draft cannot be removed once published.
        tagging = await tag_item(db_session, world.pbl, world.cardio)
        world.draft.status = VersionStatus.PUBLISHED
        await db_session.flush()
        removed = await api_client.delete(f"{API}/taggings/{tagging.id}")
        assert removed.status_code == 409

    async def test_unknown_items_and_taggings_are_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        for kind in ("module", "learning_event", "objective"):
            response = await api_client.post(
                tags_path(kind, uuid.UUID(MISSING)), json={"tag_value_id": str(world.pbl.id)}
            )
            assert response.status_code == 404
        assert (await api_client.delete(f"{API}/taggings/{MISSING}")).status_code == 404
        # Programmes are not taggable here.
        assert (
            await api_client.post(
                tags_path("programme", world.programme.id), json={"tag_value_id": str(world.pbl.id)}
            )
        ).status_code == 404

    async def test_a_programme_tagging_is_not_reachable(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        tagging = Tagging(tag_value_id=world.pbl.id, programme_id=world.programme.id)
        db_session.add(tagging)
        await db_session.flush()
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        assert (await api_client.delete(f"{API}/taggings/{tagging.id}")).status_code == 404


class TestDeletedValuesAreHidden:
    async def test_deleted_values_do_not_show_on_items(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await tag_item(db_session, world.pbl, world.cardio)
        world.pbl.soft_delete()
        await db_session.flush()
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        module = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()
        assert module["tags"] == []
