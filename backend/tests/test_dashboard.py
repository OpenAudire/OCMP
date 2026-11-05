"""Tests for the committee dashboard: key figures, snapshots, trends, comparison, credits and the
traceability from a programme outcome (ADR 058)."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import MetricSnapshot
from app.models.mapping import MappingStatus
from app.services import dashboard_metrics
from tests.test_coverage_report import Library, accept, other_status
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World, link_objectives
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def url(world: World, tail: str = "") -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/dashboard{tail}"


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


def kpi(body: dict, key: str) -> dict:  # type: ignore[type-arg]
    return next(k for k in body["kpis"] if k["key"] == key)


class TestMetrics:
    async def test_figures_count_mapped_waiting_and_framework_coverage(
        self, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.cardio_outcome, library.two)
        await other_status(db_session, world.anatomy_outcome, library.one, MappingStatus.SUGGESTED)
        visible = dashboard_metrics.full_view(world.draft, world.programme)

        metrics = await dashboard_metrics.compute_metrics(db_session, visible)

        objectives = metrics["objectives"]
        assert objectives["mapped"] == 2 and objectives["waiting"] == 1
        assert objectives["total"] > objectives["mapped"]
        found = metrics["frameworks"][str(library.framework.id)]
        assert found["name"] == "Competencies" and found["uncovered"] == 2  # G1.3 and G2
        assert metrics["credits"]["modules"] == 2

    async def test_a_snapshot_is_one_row_a_day_and_the_same_day_replaces_it(
        self, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        day = date(2026, 11, 1)
        await dashboard_metrics.take_snapshot(db_session, world.draft, world.programme, day)
        await accept(db_session, world.lecture_objective, library.one)

        again = await dashboard_metrics.take_snapshot(db_session, world.draft, world.programme, day)

        count = await db_session.scalar(
            select(func.count())
            .select_from(MetricSnapshot)
            .where(MetricSnapshot.version_id == world.draft.id)
        )
        assert count == 1 and again.metrics["objectives"]["mapped"] == 1

    async def test_every_draft_and_published_version_gets_a_snapshot(
        self, db_session: AsyncSession, world: World
    ) -> None:
        taken = await dashboard_metrics.take_all_snapshots(db_session, date(2026, 11, 2))

        assert taken >= 2
        versions = set(
            await db_session.scalars(
                select(MetricSnapshot.version_id).where(
                    MetricSnapshot.taken_on == date(2026, 11, 2)
                )
            )
        )
        assert {world.draft.id, world.published.id} <= versions


@pytest.mark.usefixtures("admin")
class TestDashboard:
    async def test_it_gives_four_indicators_with_the_trend_of_the_snapshots(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,
        library: Library,
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        today = dashboard_metrics.today()
        await dashboard_metrics.take_snapshot(
            db_session, world.draft, world.programme, today - timedelta(days=14)
        )
        await accept(db_session, world.cardio_outcome, library.two)
        await dashboard_metrics.take_snapshot(db_session, world.draft, world.programme, today)

        response = await api_client.get(url(world))

        assert response.status_code == 200, response.text
        body = response.json()
        assert [k["key"] for k in body["kpis"]] == ["mapped", "coverage", "gaps", "credits"]
        mapped = kpi(body, "mapped")
        assert mapped["unit"] == "percent" and mapped["numerator"] == 2
        assert [round(p["value"], 3) for p in mapped["series"]] == [
            round(1 / mapped["denominator"], 3),
            round(2 / mapped["denominator"], 3),
        ]
        assert body["snapshot_on"] == today.isoformat() and not body["partial"]
        assert body["framework"]["name"] == "Competencies"
        assert kpi(body, "gaps")["numerator"] == 2

    async def test_no_snapshot_means_no_trend_but_live_figures(
        self, api_client: AsyncClient, world: World, library: Library, db_session: AsyncSession
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)

        body = (await api_client.get(url(world))).json()

        assert body["snapshot_on"] is None and kpi(body, "mapped")["series"] == []
        assert kpi(body, "mapped")["numerator"] == 1

    async def test_progress_by_module_counts_outcomes_and_session_objectives(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)  # a session objective
        await other_status(db_session, world.cardio_outcome, library.two, MappingStatus.SUGGESTED)

        body = (await api_client.get(url(world))).json()

        by_code = {p["code"]: p for p in body["progress"]}
        assert by_code["HSC201"]["mapped"] == 1 and by_code["HSC201"]["waiting"] == 1
        assert by_code["HSC201"]["objectives"] >= 2
        assert by_code["HSC101"]["mapped"] == 0

    async def test_coverage_is_compared_with_the_last_published_version(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.published_outcome, library.one, coverage=2)

        body = (await api_client.get(url(world))).json()

        comparison = body["comparison"]
        assert comparison["academic_year"] == 2026 and comparison["status"] == "published"
        groups = {g["code"]: g for g in comparison["groups"]}
        assert groups["G1"]["now"] > 0 and groups["G1"]["before"] is not None
        assert groups["G2"]["now"] == 0

    async def test_the_credits_table_gives_each_module_and_the_policy(
        self, api_client: AsyncClient, world: World
    ) -> None:
        body = (await api_client.get(url(world))).json()

        credits = body["credits"]
        assert credits["hours_per_credit"] == 10 and credits["tolerance_percent"] == 10
        assert {m["code"] for m in credits["modules"]} == {"HSC201", "HSC101"}
        assert all("status" in m for m in credits["modules"])

    async def test_a_chosen_framework_must_be_one_in_use(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)

        body = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()

        assert body["framework"]["id"] == str(library.framework.id)
        assert [f["id"] for f in body["frameworks"]] == [str(library.framework.id)]

    async def test_an_unseen_version_is_a_404(self, api_client: AsyncClient) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/00000000-0000-0000-0000-000000000000/dashboard"
        )

        assert response.status_code == 404


class TestAccess:
    async def test_someone_without_report_rights_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student")

        response = await api_client.get(url(world))

        assert response.status_code in (403, 404)

    async def test_a_module_coordinator_sees_only_their_part_and_no_trend(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        from app.core.permissions import ScopeType
        from app.services.authorization import ScopeRef
        from tests.authz_helpers import grant

        user = await sign_in(api_client, db_session, test_settings, "student")
        await grant(
            db_session, user, "module_coordinator", ScopeRef(ScopeType.MODULE, world.cardio.id)
        )
        await accept(db_session, world.lecture_objective, library.one)
        await dashboard_metrics.take_snapshot(db_session, world.draft, world.programme)

        response = await api_client.get(url(world))

        if response.status_code == 200:  # reports.view at the module: a narrower view
            body = response.json()
            assert body["partial"] and body["snapshot_on"] is None
            assert {p["code"] for p in body["progress"]} <= {"HSC201"}
        else:
            assert response.status_code == 403


@pytest.mark.usefixtures("admin")
class TestTraceability:
    async def test_a_programme_outcome_is_followed_down_to_framework_items(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await link_objectives(db_session, world.cardio_outcome, world.programme_outcome)
        await accept(db_session, world.lecture_objective, library.one, coverage=4)
        await accept(db_session, world.cardio_outcome, library.two, coverage=2)
        await other_status(
            db_session, world.lecture_objective, library.three, MappingStatus.SUGGESTED
        )

        response = await api_client.get(
            url(world, "/traceability"),
            params={
                "framework_id": str(library.framework.id),
                "outcome_id": str(world.programme_outcome.id),
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["outcome"]["id"] == str(world.programme_outcome.id)
        assert [m["module_code"] for m in body["module_outcomes"]] == ["HSC201"]
        assert body["session_objectives"] >= 1 and body["module_count"] == 1
        items = {i["code"]: i for i in body["items"]}
        assert set(items) == {"G1.1", "G1.2"}  # the suggested link does not count
        assert items["G1.1"]["coverage"] == 4
        reaches = {(r["group"], r["item_id"]) for r in body["reaches"]}
        assert (0, items["G1.1"]["id"]) in reaches and (0, items["G1.2"]["id"]) in reaches

    async def test_without_a_choice_the_first_outcome_is_used_and_all_are_listed(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        body = (await api_client.get(url(world, "/traceability"))).json()

        assert body["outcome"] is not None and len(body["outcomes"]) >= 1
        assert body["items"] == [] and body["framework"] is None
