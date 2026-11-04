"""Tests for the report documents and their export endpoints (ADR 051)."""

import io
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import reports as reports_api
from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models.framework import FrameworkStatus
from app.models.mapping import MappingStatus
from app.services.authorization import INSTANCE, ScopeRef
from tests.test_coverage_report import Library, accept, other_status
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def url(world: World, key: str, tail: str = "") -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/reports/{key}{tail}"


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


@pytest.mark.usefixtures("admin")
class TestReportJson:
    async def test_the_coverage_report_is_tables_that_say_how_they_were_made(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)

        response = await api_client.get(
            url(world, "coverage"), params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["key"] == "coverage" and body["method"] == "Single match"
        assert body["made_on"]
        about = {line["label"]: line["value"] for line in body["about"]}
        assert about["Method"].startswith("Single match. An item")
        assert about["Framework"] == "Competencies (1.0.0)" or "Competencies" in about["Framework"]
        assert "BHS" in about["Curriculum version"] and about["Made on"].endswith("UTC")
        assert [s["title"] for s in body["sections"]] == ["Summary", "Heatmap", "Items"]
        items = body["sections"][2]
        assert [c["label"] for c in items["columns"]][:4] == [
            "Code",
            "Item or group",
            "Kind",
            "Status",
        ]
        codes = [row[0] for row in items["rows"]]
        assert codes == ["G1", "G1.1", "G1.2", "G1.3", "G2"]
        summary = body["sections"][0]
        assert summary["columns"][1] == {"label": "Headline", "kind": "percent"}
        assert summary["rows"][0][0] == "Single match (this report)"

    async def test_the_gap_report_lists_objectives_and_the_groups_for_subordinate_match(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await other_status(db_session, world.cardio_outcome, library.two, MappingStatus.SUGGESTED)
        params = {"framework_id": str(library.framework.id)}

        single = (await api_client.get(url(world, "gaps"), params=params)).json()
        subordinate = (
            await api_client.get(url(world, "gaps"), params={**params, "method": "subordinate"})
        ).json()

        titles = [s["title"] for s in single["sections"]]
        assert titles[0] == "Items not covered" and titles[1].startswith(
            "Objectives with no mapping"
        )
        assert titles[2].startswith("Objectives with suggestions waiting (1)")
        assert [s["title"] for s in subordinate["sections"]][1] == "Groups under 50%"

    async def test_unknown_report_is_not_found_and_a_missing_framework_is_a_plain_refusal(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        unknown = await api_client.get(url(world, "nonsense"))
        no_framework = await api_client.get(url(world, "coverage"))

        assert unknown.status_code == 404
        assert (
            no_framework.status_code == 422 and "framework" in no_framework.json()["detail"].lower()
        )

    async def test_a_draft_framework_is_refused(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        library.framework.status = FrameworkStatus.DRAFT
        await db_session.flush()

        response = await api_client.get(
            url(world, "coverage"), params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 422


@pytest.mark.usefixtures("admin")
class TestExport:
    async def get(
        self, client: AsyncClient, world: World, library: Library, key: str, **params: str
    ):  # type: ignore[no-untyped-def]
        return await client.get(
            url(world, key, "/export"),
            params={"framework_id": str(library.framework.id), **params},
        )

    async def test_an_excel_workbook_with_the_method_and_date_on_every_sheet(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)

        response = await self.get(api_client, world, library, "coverage", format="xlsx")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert 'filename="coverage-report.xlsx"' in response.headers["content-disposition"]
        book = load_workbook(io.BytesIO(response.content))
        assert book.sheetnames == ["About", "Summary", "Heatmap", "Items"]
        for name in ("Summary", "Heatmap", "Items"):
            sheet = book[name]
            assert sheet["A2"].value == "Method: Single match"
            assert sheet["A3"].value.startswith("Made on: 20") and sheet["A3"].value.endswith("UTC")
        assert book["About"]["A1"].value == "Coverage report"

    async def test_a_pdf_with_the_method_and_date_in_the_footer_of_every_page(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        response = await self.get(api_client, world, library, "coverage", format="pdf")

        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        assert response.headers["content-type"] == "application/pdf"
        assert 'filename="coverage-report.pdf"' in response.headers["content-disposition"]
        pages = [p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages]
        assert "Coverage report" in pages[0] and "Framework: Competencies" in pages[0]
        for text in pages:
            assert "Single match · made 20" in text.replace("\n", " ")

    async def test_the_gap_report_exports_with_the_objectives_and_stays_text(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        world.anatomy_outcome.text = '=HYPERLINK("http://example.org","click")'
        await db_session.flush()

        response = await self.get(
            api_client, world, library, "gaps", format="xlsx", method="multiple"
        )

        book = load_workbook(io.BytesIO(response.content))
        assert book.sheetnames[0] == "About" and len(book.sheetnames) == 4
        unlinked = next(book[n] for n in book.sheetnames if n.startswith("Objectives with no"))
        cells = [
            c
            for row in unlinked.iter_rows()
            for c in row
            if c.value and "HYPERLINK" in str(c.value)
        ]
        assert cells and all(c.data_type == "s" for c in cells)  # text, never a formula

    async def test_a_format_must_be_chosen_from_the_two(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        for params in ({}, {"format": "docx"}, {"format": "html"}):
            response = await self.get(api_client, world, library, "coverage", **params)
            assert response.status_code == 422, params

    async def test_a_report_that_fails_checks_is_not_exported(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(url(world, "coverage", "/export"), params={"format": "pdf"})

        assert response.status_code == 422  # no framework

    async def test_exports_are_limited(
        self,
        api_client: AsyncClient,
        world: World,
        library: Library,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(reports_api, "EXPORTS_PER_MINUTE", 2)

        codes = [
            (await self.get(api_client, world, library, "coverage", format="xlsx")).status_code
            for _ in range(3)
        ]

        assert codes == [200, 200, 429]


class TestWhoMayExport:
    async def test_signed_out_is_refused(self, api_client: AsyncClient, world: World) -> None:
        for tail in ("", "/export"):
            response = await api_client.get(
                url(world, "coverage", tail),
                params={"format": "xlsx", "framework_id": str(uuid.uuid4())},
            )
            assert response.status_code == 401, tail

    async def test_a_person_without_reports_view_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lecture.id),
        )

        for tail in ("", "/export"):
            response = await api_client.get(
                url(world, "coverage", tail),
                params={"format": "xlsx", "framework_id": str(library.framework.id)},
            )
            assert response.status_code == 403, tail

    async def test_a_version_that_cannot_be_seen_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        response = await api_client.get(
            url(world, "coverage", "/export"),
            params={"format": "pdf", "framework_id": str(library.framework.id)},
        )

        assert response.status_code == 404

    async def test_a_module_coordinator_exports_a_report_on_their_module_and_it_says_so(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await accept(db_session, world.anatomy_outcome, library.one)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.anatomy.id),
        )

        response = await api_client.get(
            url(world, "coverage", "/export"),
            params={"format": "xlsx", "framework_id": str(library.framework.id)},
        )

        assert response.status_code == 200
        about = load_workbook(io.BytesIO(response.content))["About"]
        labels = [c.value for c in about["A"]]
        assert "Only part of the curriculum" in labels
