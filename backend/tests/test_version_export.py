"""Tests for the exports of a curriculum version: round-trip workbook, matrix and JSON (ADR 056)."""

import io
import json

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models.mapping import MappingStatus
from app.models.tagging import TaggableType, TagListKind
from app.services import curriculum_export, curriculum_import, mapping_import, tag_import, tagging
from app.services.authorization import ScopeRef
from app.services.curriculum_read import curriculum_access, visible_version
from tests.test_coverage_report import Library, accept, other_status
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


async def visible_for(db: AsyncSession, user, world: World):  # type: ignore[no-untyped-def]
    access = await curriculum_access(db, user)
    visible = await visible_version(db, access, world.draft.id)
    assert visible is not None
    return visible


@pytest.fixture
async def admin_user(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
):  # type: ignore[no-untyped-def]
    return await sign_in(api_client, db_session, test_settings, "platform_admin")


def sheet_rows(content: bytes, title: str) -> list[list[object]]:
    ws = load_workbook(io.BytesIO(content))[title]
    return [[c.value for c in row] for row in ws.iter_rows(min_row=2)]


class TestRoundTrip:
    async def test_the_export_imports_back_without_a_single_change(
        self, db_session: AsyncSession, world: World, library: Library, admin_user
    ) -> None:  # type: ignore[no-untyped-def]
        # Everything in the world was made on the screens: no External IDs. Add a tag list,
        # an accepted and a suggested link, a taxonomy level and a teaching format.
        teaching = await tagging.create_tag_list(
            db_session,
            key="methods",
            name="Methods",
            kind=TagListKind.TEACHING_METHOD,
            entity_types=list(TaggableType),
        )
        lecture = await tagging.add_tag_value(db_session, teaching, "Lecture", code="LEC")
        await tagging.set_teaching_format(db_session, world.lecture, lecture)
        world.lecture_objective.taxonomy_level_id = world.apply.id
        await accept(db_session, world.lecture_objective, library.one, coverage=4)
        await other_status(
            db_session, world.lecture_objective, library.two, MappingStatus.SUGGESTED
        )
        await db_session.flush()
        visible = await visible_for(db_session, admin_user, world)

        content = await curriculum_export.build_roundtrip(db_session, visible)

        modules = sheet_rows(content, "Modules")
        assert {row[1] for row in modules} == {"HSC201", "HSC101"}
        assert all(len(str(row[0])) == 36 for row in modules)  # internal ids stand in
        faculty = world.programme.faculty_id
        plan = await curriculum_import.check(
            db_session,
            world.draft,
            content,
            max_bytes=10_000_000,
            faculty_id=faculty,
            default_scale=None,
        )
        assert plan.valid, [p.message for p in plan.problems]
        assert not plan.changes, [(r.sheet, r.row, r.changes) for r in plan.rows if r.changes]
        assert {r.action for r in plan.rows} == {"unchanged"}
        tags = await tag_import.check(db_session, content, max_bytes=10_000_000)
        assert tags.valid and not tags.changes
        links = await mapping_import.check(db_session, world.draft, content, max_bytes=10_000_000)
        assert links.valid and not links.changes  # both pairs are "already linked"
        assert {r.action for r in links.rows} == {"unchanged"}
        statuses = {row[7] for row in sheet_rows(content, "Mappings")}
        assert statuses == {"accepted", "suggested"}

    async def test_it_carries_the_sessions_formats_and_the_broader_links(
        self, db_session: AsyncSession, world: World, admin_user
    ) -> None:  # type: ignore[no-untyped-def]
        visible = await visible_for(db_session, admin_user, world)

        content = await curriculum_export.build_roundtrip(db_session, visible)

        objectives = {row[3]: row for row in sheet_rows(content, "Objectives")}
        lecture = objectives[world.lecture_objective.text]
        assert lecture[1] == "session"
        assert (
            str(world.cardio_outcome.id) in lecture[6]
            and str(world.programme_outcome.id) in lecture[6]
        )
        sessions = sheet_rows(content, "Sessions")
        assert any(row[2] == world.lecture.title for row in sessions)


class TestMatrix:
    async def test_cells_hold_the_accepted_coverage_and_nothing_else(
        self, db_session: AsyncSession, world: World, library: Library, admin_user
    ) -> None:  # type: ignore[no-untyped-def]
        await accept(db_session, world.lecture_objective, library.one, coverage=4)
        await other_status(
            db_session, world.lecture_objective, library.two, MappingStatus.SUGGESTED
        )
        visible = await visible_for(db_session, admin_user, world)

        content = await curriculum_export.build_matrix(db_session, visible, library.framework)

        book = load_workbook(io.BytesIO(content))
        assert book.sheetnames == ["About", "Matrix", "Items"]
        header = [c.value for c in book["Matrix"][1]]
        assert header[:4] == ["Level", "Module", "Session", "Objective"]
        codes = header[4:-1]
        assert "G1.1" in codes and "G1.2" in codes
        row = next(
            r
            for r in book["Matrix"].iter_rows(min_row=2)
            if r[3].value == world.lecture_objective.text
        )
        cells = {codes[i]: row[4 + i].value for i in range(len(codes))}
        assert cells["G1.1"] == 4 and cells["G1.2"] is None  # a suggested link is not shown
        assert row[-1].value == 1
        totals = [c.value for c in book["Matrix"][book["Matrix"].max_row]]
        assert totals[4 + codes.index("G1.1")] == 1
        about = {r[0].value: r[1].value for r in book["About"].iter_rows()}
        assert "accepted mapping link" in about["Method"] and "Made on" in about


class TestJson:
    async def test_the_document_holds_the_version_with_ids_links_and_statuses(
        self, db_session: AsyncSession, world: World, library: Library, admin_user
    ) -> None:  # type: ignore[no-untyped-def]
        await accept(db_session, world.lecture_objective, library.one, coverage=4)
        await other_status(db_session, world.lecture_objective, library.two, MappingStatus.REJECTED)
        visible = await visible_for(db_session, admin_user, world)

        document = await curriculum_export.build_json(db_session, visible)

        json.dumps(document)  # it is plain data
        assert document["schema"] == "ocmp.curriculum-version" and document["schema_version"] == 1
        assert document["partial"] is False
        assert document["version"]["programme_code"] == "BHS"
        assert {m["code"] for m in document["modules"]} == {"HSC201", "HSC101"}
        assert len(document["objectives"]) == 4
        lecture = next(
            o for o in document["objectives"] if o["id"] == str(world.lecture_objective.id)
        )
        assert lecture["level"] == "session" and len(lecture["broader"]) == 2
        statuses = {(link["item_code"], link["status"]) for link in document["mapping_links"]}
        assert ("G1.1", "accepted") in statuses and ("G1.2", "rejected") in statuses


@pytest.mark.usefixtures("admin_user")
class TestApi:
    async def test_three_downloads_with_fixed_names(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        base = f"{API}/curriculum-versions/{world.draft.id}/export"

        workbook = await api_client.get(f"{base}/workbook")
        matrix = await api_client.get(
            f"{base}/matrix", params={"framework_id": str(library.framework.id)}
        )
        document = await api_client.get(f"{base}/json")

        assert workbook.status_code == 200 and "spreadsheetml" in workbook.headers["content-type"]
        assert 'filename="curriculum-export.xlsx"' in workbook.headers["content-disposition"]
        assert (
            matrix.status_code == 200
            and "objectives-by-items.xlsx" in matrix.headers["content-disposition"]
        )
        assert document.status_code == 200
        assert json.loads(document.text)["version"]["academic_year"] == 2027

    async def test_a_framework_is_needed_for_the_matrix_and_must_be_usable(
        self, api_client: AsyncClient, world: World
    ) -> None:
        base = f"{API}/curriculum-versions/{world.draft.id}/export/matrix"

        missing = await api_client.get(base)
        unknown = await api_client.get(base, params={"framework_id": str(world.draft.id)})

        assert missing.status_code == 422 and unknown.status_code == 422

    async def test_an_unseen_version_is_not_found(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(f"{API}/curriculum-versions/{world.cardio.id}/export/json")

        assert response.status_code == 404


class TestWhoMayExport:
    async def test_a_module_coordinator_gets_their_part_but_not_the_full_workbook(
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
        base = f"{API}/curriculum-versions/{world.draft.id}/export"

        document = await api_client.get(f"{base}/json")
        workbook = await api_client.get(f"{base}/workbook")

        assert document.status_code == 200
        body = document.json()
        assert body["partial"] is True
        assert {m["code"] for m in body["modules"]} == {"HSC201"}
        assert all(o["level"] != "programme" for o in body["objectives"])
        assert workbook.status_code == 403

    async def test_a_student_may_not_export(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student")

        response = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/export/json")

        assert response.status_code in (403, 404)

    async def test_an_external_reviewer_who_reads_published_evidence_may_not_export(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from app.services.users import create_local_user
        from tests.authz_helpers import grant

        user = await create_local_user(
            db_session,
            test_settings,
            email="reviewer@example.org",
            display_name="Reviewer",
            password="a-long-enough-password-1",
        )
        await grant(
            db_session,
            user,
            "external_reviewer",
            ScopeRef(ScopeType.PROGRAMME, world.programme.id),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        await api_client.post(
            f"{API}/auth/login",
            json={"email": "reviewer@example.org", "password": "a-long-enough-password-1"},
        )

        report = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/reports/coverage",
            params={"framework_id": str(world.draft.id)},
        )
        export = await api_client.get(f"{API}/curriculum-versions/{world.published.id}/export/json")

        assert report.status_code != 403  # reports are theirs to read (here: a bad framework, 422)
        assert export.status_code == 403
