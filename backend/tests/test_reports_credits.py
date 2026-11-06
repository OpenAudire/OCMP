"""The credits and notional hours check as a report with Excel and PDF export (Slice 1.31)."""

from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.services.authorization import ScopeRef
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def url(world: World) -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/reports/credits"


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


@pytest.mark.usefixtures("admin")
class TestCreditsReport:
    async def test_it_lays_out_modules_phases_levels_and_findings(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(url(world))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["key"] == "credits"
        assert "One credit stands for 10 hours" in body["method"]
        titles = [s["title"] for s in body["sections"]]
        assert titles == ["Modules", "Credits by phase", "Credits by NQF level", "Findings"]
        modules = next(s for s in body["sections"] if s["title"] == "Modules")
        assert {row[0] for row in modules["rows"]} == {"HSC201", "HSC101"}

    async def test_it_exports_to_excel_and_pdf_stating_method_and_date(
        self, api_client: AsyncClient, world: World
    ) -> None:
        excel = await api_client.get(url(world) + "/export", params={"format": "xlsx"})
        assert excel.status_code == 200
        sheets = load_workbook(BytesIO(excel.content)).sheetnames
        assert "Modules" in sheets

        pdf = await api_client.get(url(world) + "/export", params={"format": "pdf"})
        assert pdf.status_code == 200
        text = PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
        assert "Credits and notional hours" in text
        assert "made" in text.lower()


class TestNarrowViewIsRefused:
    async def test_someone_who_sees_only_a_module_gets_no_credits_report(
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

        response = await api_client.get(url(world))

        assert response.status_code in (403, 422)
