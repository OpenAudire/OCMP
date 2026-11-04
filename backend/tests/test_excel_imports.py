"""Tests for the Excel imports of tags, mappings and frameworks and the import history (ADR 055)."""

import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    Framework,
    FrameworkItem,
    ImportJob,
    MappingLink,
    Objective,
    TagList,
    TagValue,
)
from app.models.mapping import MappingSource, MappingStatus
from app.services import mapping_import, tag_import
from app.services.import_fields import Lists, Sheet, build_workbook
from app.services.import_fields_data import (
    FRAMEWORK_HOW,
    FRAMEWORK_SHEETS,
    MAPPING_SHEETS,
    TAG_SHEETS,
)
from tests.test_coverage_report import Library
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def make(sheets: tuple[Sheet, ...], **rows: list[list[object]]) -> bytes:
    return build_workbook(Lists(), rows, sheets=sheets)


def tag_book(**rows: list[list[object]]) -> bytes:
    return make(TAG_SHEETS, **rows)


def mapping_book(rows: list[list[object]]) -> bytes:
    return make(MAPPING_SHEETS, mappings=rows)


def framework_book(head: list[object], items: list[list[object]]) -> bytes:
    return make(FRAMEWORK_SHEETS, framework=[head], items=items)


class TestTemplates:
    def test_each_template_is_made_from_its_field_definitions(self) -> None:
        for sheets, how in (
            (TAG_SHEETS, ()),
            (MAPPING_SHEETS, ()),
            (FRAMEWORK_SHEETS, FRAMEWORK_HOW),
        ):
            workbook = load_workbook(io.BytesIO(build_workbook(Lists(), sheets=sheets, how=how)))
            for sheet in sheets:
                assert [c.value for c in workbook[sheet.title][1]] == [
                    f.header for f in sheet.fields
                ]

    def test_only_the_lists_a_template_uses_are_on_its_lists_sheet(self) -> None:
        workbook = load_workbook(io.BytesIO(build_workbook(Lists(), sheets=MAPPING_SHEETS)))

        assert [c.value for c in workbook["Lists"][1]] == ["Depth"]
        tags = load_workbook(io.BytesIO(build_workbook(Lists(), sheets=TAG_SHEETS)))
        assert [c.value for c in tags["Lists"][1]] == ["Kind of tag list"]


TAGS = {
    "tag_lists": [["themes", "Themes", "theme", "Cross-cutting themes", "module; session"]],
    "tag_values": [
        ["themes", "Patient safety", "PS", None],
        ["themes", "Ethics", None, "Ethical practice"],
    ],
}


class TestTagImport:
    async def test_lists_and_tags_are_planned_then_made_with_their_item_types(
        self, db_session: AsyncSession
    ) -> None:
        plan = await tag_import.check(db_session, tag_book(**TAGS), max_bytes=10_000_000)

        assert plan.valid
        assert (
            plan.counts()["tag_lists"]["create"] == 1 and plan.counts()["tag_values"]["create"] == 2
        )

        from app.models import User

        admin = User(email="tags@example.org", display_name="Tags", is_active=True)
        db_session.add(admin)
        await db_session.flush()
        job_id = await tag_import.apply(db_session, plan, admin)

        themes = await db_session.scalar(select(TagList).where(TagList.key == "themes"))
        assert themes is not None and themes.kind.value == "theme"
        assert sorted(themes.entity_types) == ["learning_event", "module"]
        values = list(
            await db_session.scalars(
                select(TagValue)
                .where(TagValue.tag_list_id == themes.id)
                .order_by(TagValue.position)
            )
        )
        assert [(v.label, v.code, v.position) for v in values] == [
            ("Patient safety", "PS", 0),
            ("Ethics", None, 1),
        ]
        job = await db_session.get(ImportJob, job_id)
        assert job is not None and job.kind == "tags"

        again = await tag_import.check(db_session, tag_book(**TAGS), max_bytes=10_000_000)
        assert again.valid and not again.changes

    async def test_problems_and_unchangeable_things_are_reported(
        self, db_session: AsyncSession
    ) -> None:
        from app.models.tagging import TaggableType, TagListKind
        from app.services import tagging

        await tagging.create_tag_list(
            db_session,
            key="methods",
            name="Methods",
            kind=TagListKind.TEACHING_METHOD,
            entity_types=list(TaggableType),
        )
        content = tag_book(
            tag_lists=[
                ["Bad Key", "A", "theme", None, None],
                ["methods", "Methods", "theme", None, None],
                ["ok", "Fine", "theme", None, "moon"],
            ],
            tag_values=[
                ["nolist", "X", None, None],
                ["methods", "A", "C1", None],
                ["methods", "B", "C1", None],
            ],
        )

        plan = await tag_import.check(db_session, content, max_bytes=10_000_000)

        found = {(p.sheet, p.row, p.column): p.message for p in plan.problems}
        assert "lower-case" in found[("Tag lists", 2, "List key")]
        assert "cannot be changed" in found[("Tag lists", 3, "Kind")]
        assert "not programme, module" in found[("Tag lists", 4, "Applies to")]
        assert "No list has the key 'nolist'" in found[("Tag values", 2, "List key")]
        assert "already used by" in found[("Tag values", 4, "Code")]


class TestMappingImport:
    async def objective(self, db: AsyncSession, world: World, ext: str) -> Objective:
        objective = world.lecture_objective
        objective.external_id = ext
        await db.flush()
        return objective

    async def test_new_pairs_become_suggested_import_links_and_existing_ones_are_left(
        self, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        from app.models import User
        from tests.authz_helpers import grant
        from tests.test_coverage_report import accept

        objective = await self.objective(db_session, world, "OBJ-1")
        await accept(db_session, objective, library.two)
        actor = User(email="mapper@example.org", display_name="Mapper", is_active=True)
        db_session.add(actor)
        await db_session.flush()
        await grant(db_session, actor, "platform_admin")
        key = library.framework.key
        content = mapping_book(
            [
                ["OBJ-1", key, None, "G1.1", 4, "matches", "From the old spreadsheet."],
                ["OBJ-1", key, None, "G1.2", 3, None, None],
                ["OBJ-1", key, None, "G1.3", 2, "above", None],
            ]
        )

        plan = await mapping_import.check(db_session, world.draft, content, max_bytes=10_000_000)

        assert plan.valid
        assert [r.action for r in plan.rows] == ["create", "unchanged", "create"]
        assert plan.rows[1].changes == ["already linked (accepted)"]
        await mapping_import.apply(db_session, world.draft, plan, actor)
        links = list(
            await db_session.scalars(
                select(MappingLink).where(MappingLink.objective_id == objective.id)
            )
        )
        made = [x for x in links if x.source is MappingSource.IMPORT]
        assert len(made) == 2
        assert {x.status for x in made} == {MappingStatus.SUGGESTED}  # never accepted by an import
        assert {x.created_by_id for x in made} == {actor.id}
        assert sorted((x.coverage, x.depth_match.value) for x in made if x.depth_match) == [
            (2, "above"),
            (4, "matches"),
        ]
        old = next(x for x in links if x.source is not MappingSource.IMPORT)
        assert old.status is MappingStatus.ACCEPTED and old.coverage == 4  # untouched

    async def test_problems_name_the_row_and_the_cell(
        self, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await self.objective(db_session, world, "OBJ-1")
        key = library.framework.key
        content = mapping_book(
            [
                ["NOPE", key, None, "G1.1", 4, None, None],
                ["OBJ-1", "no-such", None, "G1.1", 4, None, None],
                ["OBJ-1", key, "9.9", "G1.1", 4, None, None],
                ["OBJ-1", key, None, "ZZ", 4, None, None],
                ["OBJ-1", key, None, "G1.1", 9, None, None],
                ["OBJ-1", key, None, "G1.1", 4, "sideways", None],
                ["OBJ-1", key, None, "G1.1", 4, None, None],
                ["OBJ-1", key, None, "G1.1", 3, None, None],
            ]
        )

        plan = await mapping_import.check(db_session, world.draft, content, max_bytes=10_000_000)

        found = {(p.row, p.column): p.message for p in plan.problems}
        assert (
            "No objective of this version has the External ID 'NOPE'"
            in found[(2, "Objective (External ID)")]
        )
        assert found[(3, "Framework key")] == "No framework has the key 'no-such'."
        assert "no version '9.9'" in found[(4, "Framework version")]
        assert "no item with the code 'ZZ'" in found[(5, "Framework item code")]
        assert found[(6, "Coverage (1-5)")] == "Coverage (1-5) must be from 1 to 5."
        assert "not in the list" in found[(7, "Depth")]
        assert "also on row 8" in found[(9, "Framework item code")]


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


@pytest.mark.usefixtures("admin")
class TestApi:
    async def test_tags_preview_apply_and_the_history(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        template = await api_client.get(f"{API}/imports/tags/template")
        assert template.status_code == 200
        assert load_workbook(io.BytesIO(template.content)).sheetnames[0] == "Instructions"

        preview = await api_client.post(f"{API}/imports/tags/preview", content=tag_book(**TAGS))
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["valid"] and body["token"]
        assert await db_session.scalar(select(func.count()).select_from(TagList)) == 0

        applied = await api_client.post(f"{API}/imports/tags/apply", json={"token": body["token"]})
        assert applied.status_code == 200, applied.text
        assert await db_session.scalar(select(func.count()).select_from(TagValue)) == 2
        assert (
            await api_client.post(f"{API}/imports/tags/apply", json={"token": body["token"]})
        ).status_code == 422

        history = (await api_client.get(f"{API}/import-jobs")).json()
        assert [j["kind"] for j in history] == ["tags"]
        assert history[0]["counts"]["tag_values"]["create"] == 2 and history[0]["by"]

    async def test_mappings_through_the_api_and_their_history_with_the_version(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        world.lecture_objective.external_id = "OBJ-1"
        await db_session.flush()
        base = f"{API}/curriculum-versions/{world.draft.id}/import/mappings"
        content = mapping_book([["OBJ-1", library.framework.key, None, "G1.1", 4, None, None]])

        template = await api_client.get(f"{base}/template")
        preview = await api_client.post(f"{base}/preview", content=content)
        token = preview.json()["token"]
        applied = await api_client.post(f"{base}/apply", json={"token": token})

        assert template.status_code == 200 and preview.json()["valid"]
        assert applied.status_code == 200, applied.text
        link = await db_session.scalar(
            select(MappingLink).where(MappingLink.source == MappingSource.IMPORT)
        )
        assert link is not None and link.status is MappingStatus.SUGGESTED
        job = (await api_client.get(f"{API}/import-jobs")).json()[0]
        assert job["kind"] == "mappings" and job["programme_code"] == "BHS"

    async def test_links_already_reviewed_elsewhere_can_be_recorded_as_decided(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        world.lecture_objective.external_id = "OBJ-1"
        await db_session.flush()
        base = f"{API}/curriculum-versions/{world.draft.id}/import/mappings"
        content = mapping_book([["OBJ-1", library.framework.key, None, "G1.1", 4, None, None]])
        token = (await api_client.post(f"{base}/preview", content=content)).json()["token"]

        applied = await api_client.post(f"{base}/apply", json={"token": token, "decided": True})

        assert applied.status_code == 200, applied.text
        link = await db_session.scalar(
            select(MappingLink).where(MappingLink.source == MappingSource.IMPORT)
        )
        assert link is not None and link.status is MappingStatus.ACCEPTED
        assert link.accept_method is not None and link.accept_method.value == "imported"
        assert link.first_reviewer_id is None  # nobody is recorded as having reviewed it
        job = (await api_client.get(f"{API}/import-jobs")).json()[0]
        assert job["counts"]["decided"]["links"] == 1

    async def test_a_published_version_is_refused_for_mappings(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.published.id}/import/mappings/preview",
            content=mapping_book([["X", "y", None, "z", 1, None, None]]),
        )

        assert response.status_code == 409

    async def test_a_framework_in_excel_goes_through_the_pack_preview_and_import(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        head = [
            "excel-demo",
            "Excel demo framework",
            2024,
            "Test publisher",
            "Own text",
            None,
            None,
            "From Excel.",
        ]
        items = [
            ["A", "First competency", None, None],
            ["A.1", "A part of the first", "More words", "A"],
            ["B", "Second competency", None, None],
        ]
        template = await api_client.get(f"{API}/framework-packs/excel-template")
        assert template.status_code == 200

        preview = await api_client.post(
            f"{API}/framework-packs/preview-excel", content=framework_book(head, items)
        )

        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["valid"] and body["metadata"]["version"] == "2024"
        assert body["counts"]["items"] == 3 and body["counts"]["levels"] == 2
        done = await api_client.post(
            f"{API}/framework-packs/import", json={"token": body["token"], "activate": True}
        )
        assert done.status_code == 201, done.text
        framework = await db_session.scalar(select(Framework).where(Framework.key == "excel-demo"))
        assert framework is not None
        codes = list(
            await db_session.scalars(
                select(FrameworkItem.code).where(FrameworkItem.framework_id == framework.id)
            )
        )
        assert sorted(codes) == ["A", "A.1", "B"]
        history = (await api_client.get(f"{API}/import-jobs")).json()
        assert history[0]["kind"] == "framework"

    async def test_framework_problems_are_reported_with_the_sheet_and_row(
        self, api_client: AsyncClient
    ) -> None:
        bad_head = ["Bad Key", "Name", "1", "Publisher", None, None, None, None]
        good_head = ["good-key", "Name", "1", "Publisher", None, None, None, None]
        items = [
            ["A", "First", None, None],
            ["B", "Second", None, "MISSING"],
            ["A", "Again", None, None],
        ]

        head_problem = (
            await api_client.post(
                f"{API}/framework-packs/preview-excel", content=framework_book(bad_head, items[:1])
            )
        ).json()
        item_problems = (
            await api_client.post(
                f"{API}/framework-packs/preview-excel", content=framework_book(good_head, items)
            )
        ).json()

        assert head_problem["valid"] is False and head_problem["token"] is None
        assert [e["path"] for e in head_problem["errors"]] == ["Framework, row 2, key"]
        assert item_problems["valid"] is False and item_problems["token"] is None
        paths = {e["path"] for e in item_problems["errors"]}
        assert any(p.startswith("Items, row 3") for p in paths), paths

    async def test_an_administrator_reads_everyones_import_history(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from app.models import User

        other = User(email="other@example.org", display_name="Other", is_active=True)
        db_session.add(other)
        await db_session.flush()
        db_session.add(ImportJob(kind="tags", status="applied", summary={}, created_by_id=other.id))
        await db_session.flush()

        mine = (await api_client.get(f"{API}/import-jobs")).json()

        assert [j["by"] for j in mine] == ["Other"]  # the administrator may read everyone's


class TestWithoutRights:
    async def test_a_student_may_not_import_and_sees_no_one_elses_history(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        from app.models import User

        await sign_in(api_client, db_session, test_settings, "student")
        other = User(email="someone@example.org", display_name="Someone", is_active=True)
        db_session.add(other)
        await db_session.flush()
        db_session.add(ImportJob(kind="tags", status="applied", summary={}, created_by_id=other.id))
        await db_session.flush()

        tags = await api_client.post(f"{API}/imports/tags/preview", content=b"x")
        framework = await api_client.post(f"{API}/framework-packs/preview-excel", content=b"x")
        mappings = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/import/mappings/preview", content=b"x"
        )
        history = await api_client.get(f"{API}/import-jobs")

        assert tags.status_code == 403 and framework.status_code == 403
        assert mappings.status_code in (403, 404)
        assert history.status_code == 200 and history.json() == []
