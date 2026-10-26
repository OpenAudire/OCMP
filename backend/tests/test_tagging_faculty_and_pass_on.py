"""Faculty-scoped tag lists (ADR 015, ADR 034) and passing a tag on to newer items."""

# ruff: noqa: F811  (the world fixture is imported by name)

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import Faculty, Tagging, TagValue
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.tagging import add_tag_value, tag_item
from tests.factories import FacultyFactory, LearningEventFactory, TagListFactory
from tests.test_curriculum_edit_api import MISSING, sign_in
from tests.test_tagging_api import (  # noqa: F401
    API,
    World,
    add,
    module_scope,
    operations,
    preview_path,
    programme_scope,
    tags_path,
    world,
)


def faculty_scope(faculty_id: Any) -> ScopeRef:
    return ScopeRef(ScopeType.FACULTY, faculty_id)


async def other_faculty(db: AsyncSession) -> Faculty:
    faculty = FacultyFactory()
    db.add(faculty)
    await db.flush()
    return faculty


async def faculty_list(
    db: AsyncSession, faculty_id: Any, key: str, kind: str = "theme", active: bool = True
) -> Any:
    tag_list = TagListFactory(
        key=key, name=key.title(), kind=kind, faculty_id=faculty_id, is_active=active
    )
    db.add(tag_list)
    await db.flush()
    await add_tag_value(db, tag_list, f"{key} tag")
    return tag_list


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/tag-lists/places"),
            ("GET", f"/taggings/{MISSING}/pass-on-preview"),
            ("POST", f"/taggings/{MISSING}/pass-on"),
        ],
    )
    async def test_requires_a_session(
        self, api_client: AsyncClient, method: str, path: str
    ) -> None:
        assert (await api_client.request(method, f"{API}{path}")).status_code == 401


class TestFacultyManagers:
    async def test_faculty_office_manages_lists_of_its_faculty(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        faculty_id = world.programme.faculty_id
        await sign_in(
            api_client, db_session, test_settings, "curriculum_office", faculty_scope(faculty_id)
        )
        created = await api_client.post(
            f"{API}/tag-lists",
            json={"key": "fac-themes", "name": "Faculty themes", "faculty_id": str(faculty_id)},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["faculty_id"] == str(faculty_id)
        assert body["faculty_name"]
        assert body["can_manage"] is True

        value = await api_client.post(f"{API}/tag-lists/{body['id']}/values", json={"label": "A"})
        assert value.status_code == 201
        value_id = value.json()["id"]
        assert (
            await api_client.patch(f"{API}/tag-values/{value_id}", json={"label": "B"})
        ).status_code == 200
        assert (
            await api_client.patch(f"{API}/tag-lists/{body['id']}", json={"name": "Renamed"})
        ).status_code == 200
        assert (await api_client.delete(f"{API}/tag-values/{value_id}")).status_code == 204
        assert (await api_client.delete(f"{API}/tag-lists/{body['id']}")).status_code == 204

    async def test_faculty_office_cannot_touch_institution_wide_lists(
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
            faculty_scope(world.programme.faculty_id),
        )
        # Creating one without a faculty means institution-wide.
        assert (
            await api_client.post(f"{API}/tag-lists", json={"key": "wide", "name": "Wide"})
        ).status_code == 403
        assert (
            await api_client.patch(f"{API}/tag-lists/{world.themes.id}", json={"name": "X"})
        ).status_code == 403
        assert (await api_client.delete(f"{API}/tag-lists/{world.themes.id}")).status_code == 403
        assert (
            await api_client.post(f"{API}/tag-lists/{world.themes.id}/values", json={"label": "X"})
        ).status_code == 403
        assert (
            await api_client.patch(f"{API}/tag-values/{world.ethics.id}", json={"label": "X"})
        ).status_code == 403
        assert (await api_client.delete(f"{API}/tag-values/{world.ethics.id}")).status_code == 403

    async def test_faculty_office_cannot_touch_another_facultys_lists(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        theirs = await faculty_list(db_session, other.id, "theirs")
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "curriculum_office",
            faculty_scope(world.programme.faculty_id),
        )
        created = await api_client.post(
            f"{API}/tag-lists",
            json={"key": "sneaky", "name": "Sneaky", "faculty_id": str(other.id)},
        )
        assert created.status_code == 403
        assert (
            await api_client.patch(f"{API}/tag-lists/{theirs.id}", json={"name": "X"})
        ).status_code == 403
        assert (await api_client.delete(f"{API}/tag-lists/{theirs.id}")).status_code == 403

    async def test_instance_office_manages_faculty_and_institution_lists(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        mine = await faculty_list(db_session, world.programme.faculty_id, "mine")
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (
            await api_client.patch(f"{API}/tag-lists/{mine.id}", json={"name": "Changed"})
        ).status_code == 200
        wide = await api_client.post(f"{API}/tag-lists", json={"key": "wide", "name": "Wide"})
        assert wide.status_code == 201
        assert wide.json()["faculty_id"] is None
        missing = await api_client.post(
            f"{API}/tag-lists", json={"key": "gone", "name": "Gone", "faculty_id": MISSING}
        )
        assert missing.status_code == 422

    async def test_places_lists_where_the_user_may_create(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await other_faculty(db_session)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "curriculum_office",
            faculty_scope(world.programme.faculty_id),
        )
        places = (await api_client.get(f"{API}/tag-lists/places")).json()
        assert places["institution"] is False
        assert [f["id"] for f in places["faculties"]] == [str(world.programme.faculty_id)]

        await sign_in(api_client, db_session, test_settings, "platform_admin")
        everywhere = (await api_client.get(f"{API}/tag-lists/places")).json()
        assert everywhere["institution"] is True
        assert len(everywhere["faculties"]) == 2


class TestListVisibility:
    async def test_lists_are_visible_to_their_faculty_and_managers_see_inactive(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        await faculty_list(db_session, world.programme.faculty_id, "mine")
        await faculty_list(db_session, world.programme.faculty_id, "mine-off", active=False)
        await faculty_list(db_session, other.id, "theirs")
        world.themes.is_active = False
        await db_session.flush()

        await sign_in(
            api_client,
            db_session,
            test_settings,
            "curriculum_office",
            faculty_scope(world.programme.faculty_id),
        )
        seen = {item["key"]: item for item in (await api_client.get(f"{API}/tag-lists")).json()}
        # Their faculty's lists (inactive too) and the active institution-wide ones.
        assert set(seen) == {"methods", "mine", "mine-off"}
        assert seen["mine"]["can_manage"] is True
        assert seen["methods"]["can_manage"] is False
        assert seen["mine"]["values"][0]["usage_count"] == 0

    async def test_module_coordinators_see_their_faculty_lists_not_others(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        await faculty_list(db_session, world.programme.faculty_id, "mine")
        await faculty_list(db_session, other.id, "theirs")
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        seen = {item["key"] for item in (await api_client.get(f"{API}/tag-lists")).json()}
        assert seen == {"methods", "themes", "mine"}

    async def test_instance_users_see_every_faculty(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        await faculty_list(db_session, other.id, "theirs")
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        seen = {item["key"] for item in (await api_client.get(f"{API}/tag-lists")).json()}
        assert "theirs" in seen

    async def test_format_choices_leave_out_other_facultys_lists(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        await faculty_list(db_session, other.id, "theirs", kind="teaching_method")
        await faculty_list(db_session, world.programme.faculty_id, "mine", kind="teaching_method")
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.cardio)
        )
        lists = {f["list_name"] for f in (await api_client.get(f"{API}/teaching-formats")).json()}
        assert lists == {"Teaching methods", "Mine"}


class TestFacultyListsOnItems:
    async def test_a_faculty_list_tags_only_items_of_that_faculty(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = await other_faculty(db_session)
        await faculty_list(db_session, world.programme.faculty_id, "mine")
        theirs = await faculty_list(db_session, other.id, "theirs")
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        lists = {item["key"]: item for item in (await api_client.get(f"{API}/tag-lists")).json()}
        own_tag = lists["mine"]["values"][0]["id"]
        response = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": own_tag}
        )
        assert response.status_code == 201

        foreign_tag = await db_session.scalar(
            select(TagValue).where(TagValue.tag_list_id == theirs.id)
        )
        assert foreign_tag is not None
        refused = await api_client.post(
            tags_path("module", world.cardio.id), json={"tag_value_id": str(foreign_tag.id)}
        )
        assert refused.status_code == 422
        assert "another faculty" in refused.json()["detail"]
        preview = await api_client.get(
            preview_path("module", world.cardio.id), params={"tag_value_id": str(foreign_tag.id)}
        )
        assert preview.status_code == 422


async def module_detail(client: AsyncClient, module_id: Any) -> dict[str, Any]:
    response = await client.get(f"{API}/modules/{module_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def not_reached(detail: dict[str, Any], label: str) -> int:
    (tag,) = [t for t in detail["tags"] if t["label"] == label]
    count: int = tag["not_reached"]
    return count


class TestPassingATagOn:
    async def test_newer_sessions_are_counted_previewed_and_given_the_tag(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        # Tagged without passing it on: both sessions have not been reached.
        await add(api_client, "module", world.cardio.id, world.pbl)
        detail = await module_detail(api_client, world.cardio.id)
        assert not_reached(detail, "PBL") == 2
        tagging_id = detail["tags"][0]["direct_tagging_id"]

        # One session gets the tag by hand; it no longer counts.
        await add(api_client, "learning_event", world.lab.id, world.pbl)
        assert not_reached(await module_detail(api_client, world.cardio.id), "PBL") == 1

        preview = (await api_client.get(f"{API}/taggings/{tagging_id}/pass-on-preview")).json()
        statuses = {item["name"]: item["status"] for item in preview["items"]}
        assert statuses == {"Cardiac cycle": "new", "Skills lab": "has_tag"}

        passed = await api_client.post(f"{API}/taggings/{tagging_id}/pass-on")
        assert passed.status_code == 201, passed.text
        assert passed.json()["inherited_count"] == 1
        assert await operations(db_session, "tagging.pass_on") == 1
        assert not_reached(await module_detail(api_client, world.cardio.id), "PBL") == 0
        sources = (await api_client.get(f"{API}/learning-events/{world.lecture.id}")).json()
        assert sources["tags"][0]["sources"][0]["item_id"] == str(world.cardio.id)

        # A session added later has not been reached; passing on again gives it the tag.
        late = LearningEventFactory(module=world.cardio, title="Late session", position=5)
        db_session.add(late)
        await db_session.flush()
        assert not_reached(await module_detail(api_client, world.cardio.id), "PBL") == 1
        again = await api_client.post(f"{API}/taggings/{tagging_id}/pass-on")
        assert again.json()["inherited_count"] == 1
        nothing = await api_client.post(f"{API}/taggings/{tagging_id}/pass-on")
        assert nothing.status_code == 201
        assert nothing.json()["inherited_count"] == 0

        # Removing the direct tag still takes everything it passed on.
        assert (await api_client.delete(f"{API}/taggings/{tagging_id}")).status_code == 204
        late_tags = (await api_client.get(f"{API}/learning-events/{late.id}")).json()["tags"]
        assert late_tags == []

    async def test_objectives_linked_later_are_reached(
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
        newer = await add_objective(db_session, world.cardio, "Explain heart failure.")
        await link_objectives(db_session, newer, world.programme_outcome)

        outcomes = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/outcomes")
        assert outcomes.status_code == 200
        programme_outcomes = outcomes.json()
        (outcome,) = [o for o in programme_outcomes if o["id"] == str(world.programme_outcome.id)]
        (tag,) = outcome["tags"]
        assert tag["not_reached"] == 1
        passed = await api_client.post(f"{API}/taggings/{tag['direct_tagging_id']}/pass-on")
        assert passed.json()["inherited_count"] == 1

    async def test_rules(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        direct = await tag_item(db_session, world.pbl, world.cardio)
        inherited = await tag_item(db_session, world.pbl, world.lecture, inherited_from=direct)
        published = await tag_item(db_session, world.pbl, world.published_module)
        await db_session.flush()
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.anatomy)
        )
        # A coordinator of another module neither sees nor changes it.
        assert (await api_client.post(f"{API}/taggings/{direct.id}/pass-on")).status_code == 404

        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        refused = await api_client.post(f"{API}/taggings/{inherited.id}/pass-on")
        assert refused.status_code == 422
        previewed = await api_client.get(f"{API}/taggings/{inherited.id}/pass-on-preview")
        assert previewed.status_code == 422
        assert (await api_client.post(f"{API}/taggings/{published.id}/pass-on")).status_code == 409
        assert (await api_client.post(f"{API}/taggings/{MISSING}/pass-on")).status_code == 404

        # The new rows point at the direct tagging, as for tags passed on when tagging.
        count = await api_client.post(f"{API}/taggings/{direct.id}/pass-on")
        assert count.json()["inherited_count"] == 1
        rows = (
            await db_session.execute(
                Tagging.__table__.select().where(Tagging.inherited_from_id == direct.id)
            )
        ).all()
        assert len(rows) == 2

    async def test_lecturers_cannot_pass_on(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        direct = await tag_item(db_session, world.pbl, world.cardio)
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "lecturer", module_scope(world.cardio))
        assert (await api_client.post(f"{API}/taggings/{direct.id}/pass-on")).status_code == 403
        assert (
            await api_client.get(f"{API}/taggings/{direct.id}/pass-on-preview")
        ).status_code == 403
