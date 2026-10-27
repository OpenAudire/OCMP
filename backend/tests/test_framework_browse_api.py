"""Reading frameworks: the library, the tree in windows, search and where items are mapped."""

from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Programme,
)
from app.models.curriculum import VersionStatus
from app.models.mapping import MappingSource, MappingStatus
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective
from app.services.frameworks import add_item
from tests.factories import (
    CurriculumVersionFactory,
    FacultyFactory,
    FrameworkFactory,
    LearningEventFactory,
    ModuleFactory,
    ProgrammeFactory,
)
from tests.test_curriculum_edit_api import MISSING, sign_in

API = "/api/v1"


@dataclass
class World:
    framework: Framework
    area: FrameworkItem  # top level, with three children
    first: FrameworkItem  # child with the links
    second: FrameworkItem
    third: FrameworkItem
    grandchild: FrameworkItem
    other_area: FrameworkItem
    module_a: Module  # published version
    module_b: Module  # published version
    module_draft: Module  # draft version
    event_a: LearningEvent
    programme: Programme
    published: CurriculumVersion
    draft: CurriculumVersion
    outcome_a: Objective
    outcome_b: Objective
    event_objective: Objective
    programme_outcome: Objective
    draft_outcome: Objective


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


def link(
    objective: Objective, item: FrameworkItem, status: MappingStatus = MappingStatus.SUGGESTED
) -> MappingLink:
    return MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=MappingSource.IMPORT,
        status=status,
        accept_method="imported" if status == MappingStatus.ACCEPTED else None,
    )


@pytest.fixture
async def world(db_session: AsyncSession, system_roles: None) -> World:
    db = db_session
    framework = FrameworkFactory(name="Browse framework", key="browse-fw")
    programme = ProgrammeFactory(faculty=FacultyFactory(), code="BHS", name="BSc Browse")
    published = CurriculumVersionFactory(
        programme=programme, academic_year=2026, status=VersionStatus.PUBLISHED
    )
    draft = CurriculumVersionFactory(programme=programme, academic_year=2027)
    await save(db, framework, programme, published, draft)
    module_a = ModuleFactory(version=published, code="HSC101", name="Anatomy")
    module_b = ModuleFactory(version=published, code="HSC102", name="Physiology")
    module_draft = ModuleFactory(version=draft, code="HSC101", name="Anatomy")
    await save(db, module_a, module_b, module_draft)
    event_a = LearningEventFactory(module=module_a, title="Heart lecture")
    await save(db, event_a)

    area = await add_item(db, framework, code="A", title="Clinical reasoning", position=1)
    first = await add_item(db, framework, code="A.1", title="Gather history", parent=area)
    second = await add_item(
        db, framework, code="A.2", title="Examine the patient", parent=area, position=1
    )
    third = await add_item(db, framework, code="A.3", title="Order tests", parent=area, position=2)
    grandchild = await add_item(db, framework, code="A.1.1", title="Open questions", parent=first)
    other_area = await add_item(db, framework, code="B", title="Communication", position=2)

    outcome_a = await add_objective(db, module_a, "Describe the heart.")
    outcome_b = await add_objective(db, module_b, "Explain gas exchange.")
    event_objective = await add_objective(db, event_a, "Name the heart valves.")
    programme_outcome = await add_objective(db, published, "Reason clinically.")
    draft_outcome = await add_objective(db, module_draft, "Draft: describe the heart.")
    rejected = await add_objective(db, module_a, "Rejected idea.")
    await save(
        db,
        link(outcome_a, first, MappingStatus.ACCEPTED),
        link(outcome_b, first),
        link(event_objective, first, MappingStatus.ACCEPTED),
        link(programme_outcome, first, MappingStatus.ACCEPTED),
        link(draft_outcome, first),
        link(rejected, first, MappingStatus.REJECTED),
        link(outcome_a, second, MappingStatus.ACCEPTED),
    )
    return World(
        framework=framework,
        area=area,
        first=first,
        second=second,
        third=third,
        grandchild=grandchild,
        other_area=other_area,
        module_a=module_a,
        module_b=module_b,
        module_draft=module_draft,
        event_a=event_a,
        programme=programme,
        published=published,
        draft=draft,
        outcome_a=outcome_a,
        outcome_b=outcome_b,
        event_objective=event_objective,
        programme_outcome=programme_outcome,
        draft_outcome=draft_outcome,
    )


def module_scope(module: Module) -> ScopeRef:
    return ScopeRef(ScopeType.MODULE, module.id)


def event_scope(event: LearningEvent) -> ScopeRef:
    return ScopeRef(ScopeType.LEARNING_EVENT, event.id)


async def get_json(client: AsyncClient, path: str, **params: Any) -> Any:
    response = await client.get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


class TestLibrary:
    async def test_lists_versions_with_counts_and_licence(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        newer = FrameworkFactory(
            key="browse-fw", name="Browse framework", version_label="2.0", status="active"
        )
        await save(db_session, newer)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, "/frameworks")

        assert body["can_manage"] is True
        mine = [f for f in body["frameworks"] if f["key"] == "browse-fw"]
        assert {f["version_label"] for f in mine} == {"1.0", "2.0"}
        first = next(f for f in mine if f["version_label"] == "1.0")
        assert first["item_count"] == 6
        assert first["top_level_count"] == 2
        assert first["level_count"] == 3
        assert first["licence_note"] == "Fictional framework for tests"
        empty = next(f for f in mine if f["version_label"] == "2.0")
        assert (empty["item_count"], empty["level_count"]) == (0, 0)

    async def test_deleted_frameworks_are_not_listed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        world.framework.soft_delete()
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, "/frameworks")

        assert all(f["key"] != "browse-fw" for f in body["frameworks"])
        response = await api_client.get(f"{API}/frameworks/{world.framework.id}/items")
        assert response.status_code == 404

    async def test_sign_in_and_a_reading_permission_are_needed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        assert (await api_client.get(f"{API}/frameworks")).status_code == 401
        await sign_in(api_client, db_session, test_settings, "student")
        assert (await api_client.get(f"{API}/frameworks")).status_code == 403
        item_path = f"{API}/frameworks/{world.framework.id}/items/{world.first.id}"
        assert (await api_client.get(f"{item_path}/mappings")).status_code == 403

    async def test_a_module_lecturer_reads_but_cannot_manage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "lecturer", module_scope(world.module_a)
        )

        body = await get_json(api_client, "/frameworks")

        assert body["can_manage"] is False
        assert any(f["key"] == "browse-fw" for f in body["frameworks"])


class TestTree:
    async def test_top_level_and_children_in_order_with_counts(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        base = f"/frameworks/{world.framework.id}/items"

        top = await get_json(api_client, base)
        assert [i["code"] for i in top["items"]] == ["A", "B"]
        assert top["total"] == 2 and top["offset"] == 0
        assert top["items"][0]["child_count"] == 3
        assert top["items"][1]["child_count"] == 0

        children = await get_json(api_client, base, parent_id=str(world.area.id))
        assert [i["code"] for i in children["items"]] == ["A.1", "A.2", "A.3"]
        assert children["items"][0]["child_count"] == 1
        assert children["items"][0]["depth"] == 1

    async def test_children_come_in_windows(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        base = f"/frameworks/{world.framework.id}/items"

        page = await get_json(api_client, base, parent_id=str(world.area.id), offset=1, limit=1)

        assert page["total"] == 3 and page["offset"] == 1
        assert [i["code"] for i in page["items"]] == ["A.2"]
        too_many = await api_client.get(f"{API}{base}", params={"limit": 201})
        assert too_many.status_code == 422

    async def test_an_item_of_another_framework_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other = FrameworkFactory()
        await save(db_session, other)
        stranger = await add_item(db_session, other, code="X", title="Elsewhere")
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        for path in (
            f"/frameworks/{world.framework.id}/items/{stranger.id}",
            f"/frameworks/{world.framework.id}/items/{stranger.id}/mappings",
            f"/frameworks/{world.framework.id}/items/{MISSING}",
            f"/frameworks/{MISSING}/items",
        ):
            assert (await api_client.get(f"{API}{path}")).status_code == 404, path
        wrong_parent = await api_client.get(
            f"{API}/frameworks/{world.framework.id}/items", params={"parent_id": str(stranger.id)}
        )
        assert wrong_parent.status_code == 404

    async def test_item_detail_has_path_and_place_among_siblings(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        detail = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items/{world.grandchild.id}"
        )
        assert [a["code"] for a in detail["path"]] == ["A", "A.1"]
        assert [a["sibling_index"] for a in detail["path"]] == [0, 0]
        assert detail["sibling_index"] == 0
        assert detail["child_count"] == 0

        third = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items/{world.third.id}"
        )
        assert third["sibling_index"] == 2
        assert third["path"][0]["title"] == "Clinical reasoning"
        assert third["path"][0]["sibling_index"] == 0

        other = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items/{world.other_area.id}"
        )
        assert other["path"] == [] and other["sibling_index"] == 1

    async def test_a_big_flat_framework_is_read_in_windows(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        framework = FrameworkFactory()
        await save(db_session, framework)
        db_session.add_all(
            FrameworkItem(
                framework_id=framework.id, code=f"K{n:05d}", title=f"Keyword {n}", position=n
            )
            for n in range(1500)
        )
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        page = await get_json(
            api_client, f"/frameworks/{framework.id}/items", offset=1400, limit=200
        )

        assert page["total"] == 1500
        assert len(page["items"]) == 100
        assert page["items"][0]["code"] == "K01400"


class TestSearch:
    async def test_finds_by_code_or_text_case_insensitively(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        path = f"/frameworks/{world.framework.id}/search"

        by_text = await get_json(api_client, path, q="PATIENT")
        assert [h["code"] for h in by_text["hits"]] == ["A.2"]
        assert [a["code"] for a in by_text["hits"][0]["path"]] == ["A"]

        by_code = await get_json(api_client, path, q="a.1")
        assert [h["code"] for h in by_code["hits"]] == ["A.1", "A.1.1"]
        assert by_code["total"] == 2
        assert by_code["hits"][1]["path"][-1]["code"] == "A.1"

    async def test_wildcards_are_plain_text_and_empty_searches_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        path = f"/frameworks/{world.framework.id}/search"

        assert (await get_json(api_client, path, q="%"))["total"] == 0
        assert (await get_json(api_client, path, q="_"))["total"] == 0
        assert (await api_client.get(f"{API}{path}", params={"q": "   "})).status_code == 422
        assert (await api_client.get(f"{API}{path}")).status_code == 422

    async def test_results_come_in_pages_and_carry_mapped_counts(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        path = f"/frameworks/{world.framework.id}/search"

        page = await get_json(api_client, path, q="A.", offset=1, limit=1)

        assert page["total"] == 4
        assert len(page["hits"]) == 1
        everything = await get_json(api_client, path, q="A.")
        counts = {h["code"]: h["mapped_count"] for h in everything["hits"]}
        assert counts["A.1"] == 5 and counts["A.2"] == 1 and counts["A.3"] == 0


class TestWhereMapped:
    def path(self, world: World, item: FrameworkItem) -> str:
        return f"/frameworks/{world.framework.id}/items/{item.id}/mappings"

    async def test_the_office_sees_every_link_except_rejected_ones(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, self.path(world, world.first))

        assert body["total"] == 5
        by_text = {m["objective_text"]: m for m in body["mappings"]}
        assert "Rejected idea." not in by_text
        module_row = by_text["Describe the heart."]
        assert module_row["status"] == "accepted"
        assert module_row["module_code"] == "HSC101"
        assert module_row["programme_name"] == "BSc Browse"
        assert module_row["academic_year"] == 2026
        assert module_row["version_status"] == "published"
        event_row = by_text["Name the heart valves."]
        assert event_row["learning_event_title"] == "Heart lecture"
        assert event_row["module_code"] == "HSC101"
        assert by_text["Reason clinically."]["level"] == "programme"
        assert by_text["Reason clinically."]["module_id"] is None
        assert by_text["Draft: describe the heart."]["version_status"] == "draft"
        assert by_text["Explain gas exchange."]["status"] == "suggested"

    async def test_a_module_role_sees_only_its_own_module_and_sessions(
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
            module_scope(world.module_a),
        )

        body = await get_json(api_client, self.path(world, world.first))

        assert {m["objective_text"] for m in body["mappings"]} == {
            "Describe the heart.",
            "Name the heart valves.",
        }
        assert body["total"] == 2
        page = await get_json(api_client, f"/frameworks/{world.framework.id}/items")
        assert page["items"][0]["mapped_count"] == 0  # the top level item has no direct links
        children = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items", parent_id=str(world.area.id)
        )
        assert [i["mapped_count"] for i in children["items"]] == [2, 1, 0]

    async def test_a_session_role_sees_only_that_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "lecturer", event_scope(world.event_a))

        body = await get_json(api_client, self.path(world, world.first))

        assert [m["objective_text"] for m in body["mappings"]] == ["Name the heart valves."]
        detail = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items/{world.first.id}"
        )
        assert detail["mapped_count"] == 1

    async def test_links_in_hidden_curriculum_are_not_counted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        other_programme = ProgrammeFactory(faculty=FacultyFactory(), code="OTH")
        await save(db_session, other_programme)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "programme_director",
            ScopeRef(ScopeType.PROGRAMME, other_programme.id),
        )

        body = await get_json(api_client, self.path(world, world.first))

        assert body["total"] == 0 and body["mappings"] == []

    async def test_deleted_objectives_modules_and_versions_are_left_out(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        world.outcome_b.soft_delete()
        world.event_a.soft_delete()
        world.draft.soft_delete()
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, self.path(world, world.first))

        assert {m["objective_text"] for m in body["mappings"]} == {
            "Describe the heart.",
            "Reason clinically.",
        }

    async def test_deleted_links_are_not_listed_or_counted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        stale = await db_session.scalar(
            select(MappingLink).where(
                MappingLink.objective_id == world.outcome_b.id,
                MappingLink.framework_item_id == world.first.id,
            )
        )
        assert stale is not None
        stale.soft_delete()
        # An old orphan: the link is live but its objective was deleted.
        world.programme_outcome.soft_delete()
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, self.path(world, world.first))
        detail = await get_json(
            api_client, f"/frameworks/{world.framework.id}/items/{world.first.id}"
        )

        assert {m["objective_text"] for m in body["mappings"]} == {
            "Describe the heart.",
            "Name the heart valves.",
            "Draft: describe the heart.",
        }
        assert detail["mapped_count"] == 3

    async def test_flags_that_reports_must_show_are_returned(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        stored = await db_session.scalar(
            select(MappingLink).where(
                MappingLink.objective_id == world.outcome_a.id,
                MappingLink.framework_item_id == world.second.id,
            )
        )
        assert stored is not None
        stored.needs_recheck = True
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        body = await get_json(api_client, self.path(world, world.second))

        assert [m["needs_recheck"] for m in body["mappings"]] == [True]
