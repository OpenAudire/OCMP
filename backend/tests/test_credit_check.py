"""Tests for the credits and notional hours check: the rules, the API and the settings."""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import Assessment, Institution, Module, Phase, QualificationType
from app.models.curriculum import PhaseKind
from app.services.authorization import ScopeRef
from app.services.credit_check import (
    HoursStatus,
    YearStatus,
    check_credits,
    module_hours,
)
from app.services.institution_settings import get_institution
from app.services.policies import CreditPolicy
from tests.factories import InstitutionFactory
from tests.test_curriculum_edit_api import (
    API,
    World,
    programme_scope,
    save,
    sign_in,
    world,  # noqa: F401  (fixture)
)

POLICY = CreditPolicy()


@pytest.fixture
async def institution(db_session: AsyncSession) -> Institution:
    institution = InstitutionFactory(name="Demo University", short_code="DEMO")
    db_session.add(institution)
    await db_session.flush()
    return institution


def module(credits: str | None, level: int | None = 5, code: str = "MOD1") -> Module:
    return Module(
        id=uuid.uuid4(),
        code=code,
        name="Module",
        credits=Decimal(credits) if credits is not None else None,
        nqf_level=level,
    )


def hours(m: Module, contact: int = 0, study: int = 0, assessed: int = 0, policy=POLICY):  # type: ignore[no-untyped-def]
    return module_hours(
        m,
        contact_minutes=contact,
        self_study_minutes=study,
        assessment_minutes=assessed,
        policy=policy,
    )


class TestModuleHours:
    @pytest.mark.parametrize(
        ("minutes", "status", "difference"),
        [
            (7200, HoursStatus.OK, "0.0"),  # 120 hours: exactly 12 credits x 10
            (6600, HoursStatus.OK, "-8.3"),  # 110 hours: within 10%
            (7920, HoursStatus.OK, "10.0"),  # 132 hours: on the edge
            (6480, HoursStatus.OK, "-10.0"),  # 108 hours: on the edge
            (6000, HoursStatus.UNDER, "-16.7"),
            (8400, HoursStatus.OVER, "16.7"),
            (0, HoursStatus.UNDER, "-100.0"),
        ],
    )
    def test_compares_planned_hours_with_credits(
        self, minutes: int, status: HoursStatus, difference: str
    ) -> None:
        result = hours(module("12"), contact=minutes)

        assert result.status == status
        assert result.difference_percent == Decimal(difference)
        assert result.expected_hours == Decimal(120)

    def test_adds_contact_self_study_and_assessment_time(self) -> None:
        result = hours(module("1"), contact=120, study=300, assessed=180)

        assert (result.contact_hours, result.self_study_hours, result.assessment_hours) == (
            Decimal("2.0"),
            Decimal("5.0"),
            Decimal("3.0"),
        )
        assert result.planned_hours == Decimal("10.0")
        assert result.status == HoursStatus.OK

    def test_uses_the_institutions_figures(self) -> None:
        policy = CreditPolicy(hours_per_credit=15, tolerance_percent=0)

        assert hours(module("10"), contact=9000, policy=policy).status == HoursStatus.OK
        assert hours(module("10"), contact=9060, policy=policy).status == HoursStatus.OVER

    def test_without_credits_there_is_nothing_to_compare(self) -> None:
        result = hours(module(None), contact=600)

        assert result.status == HoursStatus.NO_CREDITS
        assert (result.expected_hours, result.difference_percent) == (None, None)

    def test_zero_credits_with_planned_time_is_over(self) -> None:
        assert hours(module("0")).status == HoursStatus.OK
        zero = hours(module("0"), contact=60)
        assert (zero.status, zero.difference_percent) == (HoursStatus.OVER, None)


def phase(name: str, kind: PhaseKind = PhaseKind.YEAR) -> Phase:
    return Phase(id=uuid.uuid4(), name=name, kind=kind)


def check(
    phases: list[Phase],
    modules: list[Module],
    *,
    policy: CreditPolicy = POLICY,
    programme_total: int | None = None,
    qualification: QualificationType | None = None,
    exit_level: int | None = None,
):  # type: ignore[no-untyped-def]
    return check_credits(
        policy=policy,
        phases=phases,
        hours=[hours(m) for m in modules],
        programme_total_credits=programme_total,
        qualification=qualification,
        exit_level=exit_level,
    )


class TestYearsAndLevels:
    def test_years_are_compared_with_the_typical_credits(self) -> None:
        year1, year2, block = phase("Year 1"), phase("Year 2"), phase("Block", PhaseKind.BLOCK)
        modules = [module("120", code="A"), module("100", code="B"), module("30", code="C")]
        modules[0].phase_id, modules[1].phase_id, modules[2].phase_id = (
            year1.id,
            year2.id,
            block.id,
        )
        longitudinal = module("10", code="D")
        longitudinal.phase_id = None
        unset = module(None, code="E")
        unset.phase_id = year2.id

        result = check([year1, year2, block], [*modules, longitudinal, unset])

        assert [(y.name, y.credits, y.status) for y in result.years] == [
            ("Year 1", 120, YearStatus.OK),
            ("Year 2", 100, YearStatus.UNDER),
            ("Block", 30, YearStatus.NOT_CHECKED),
        ]
        assert result.years[1].modules_without_credits == 1
        assert (result.unphased_credits, result.unphased_modules) == (10, 1)
        over = check([year1], [_in(year1, "130")])
        assert over.years[0].status == YearStatus.OVER

    def test_credits_are_totalled_per_nqf_level(self) -> None:
        result = check(
            [], [module("60", 5), module("30", 6), module("30", 5, "B"), module("12", None, "C")]
        )

        assert [(row.level, row.credits, row.modules) for row in result.levels] == [
            (5, 90, 2),
            (6, 30, 1),
            (None, 12, 1),
        ]
        assert result.total_credits == 132

    def test_findings_against_the_programme_and_qualification(self) -> None:
        bachelor = QualificationType(
            key="bachelor", name="Bachelor's degree", nqf_exit_level=7, min_total_credits=360
        )
        modules = [module("120", 7, "A"), module("100", 8, "B")]
        policy = CreditPolicy(min_exit_level_credits=240)

        result = check(
            [],
            modules,
            policy=policy,
            programme_total=360,
            qualification=bachelor,
            exit_level=7,
        )

        assert {f.code: f.params for f in result.findings} == {
            "total_differs_from_programme": {"total": "220", "programme": 360},
            "total_below_qualification_minimum": {"total": "220", "minimum": 360},
            "above_exit_level": {"level": 7, "modules": "B"},
            "exit_level_credits_low": {"level": 7, "credits": "120", "minimum": 240},
        }
        assert result.qualification_name == "Bachelor's degree"

    def test_the_qualification_type_sets_the_exit_level_minimum(self) -> None:
        bachelor = QualificationType(
            key="bachelor",
            name="Bachelor's degree",
            nqf_exit_level=7,
            min_total_credits=360,
            min_exit_level_credits=120,
        )
        few = [module("90", 7, "A"), module("270", 6, "B")]

        low = check([], few, qualification=bachelor, exit_level=7)
        assert low.exit_level_minimum == 120
        assert {f.code: f.params for f in low.findings if f.code == "exit_level_credits_low"} == {
            "exit_level_credits_low": {"level": 7, "credits": "90", "minimum": 120}
        }

        enough = check(
            [], [module("120", 7, "A"), module("240", 6, "B")], qualification=bachelor, exit_level=7
        )
        assert enough.exit_level_minimum == 120
        assert all(f.code != "exit_level_credits_low" for f in enough.findings)

    def test_the_institutions_figure_wins_over_the_qualification_type(self) -> None:
        bachelor = QualificationType(
            key="bachelor",
            name="Bachelor's degree",
            nqf_exit_level=7,
            min_total_credits=360,
            min_exit_level_credits=120,
        )
        result = check(
            [],
            [module("120", 7, "A")],
            policy=CreditPolicy(min_exit_level_credits=60),
            qualification=bachelor,
            exit_level=7,
        )
        assert result.exit_level_minimum == 60
        assert all(f.code != "exit_level_credits_low" for f in result.findings)

    def test_the_type_minimum_applies_only_at_its_own_exit_level(self) -> None:
        bachelor = QualificationType(
            key="bachelor",
            name="Bachelor's degree",
            nqf_exit_level=7,
            min_total_credits=360,
            min_exit_level_credits=120,
        )
        # The programme sets a different exit level, so the type's figure does not fit it.
        result = check([], [module("30", 8, "A")], qualification=bachelor, exit_level=8)
        assert result.exit_level_minimum is None

    def test_no_findings_when_everything_fits(self) -> None:
        result = check([], [module("360", 7)], programme_total=360, exit_level=7)

        assert result.findings == []


def _in(parent: Phase, credits: str) -> Module:
    found = module(credits)
    found.phase_id = parent.id
    return found


class TestPolicy:
    def test_defaults(self) -> None:
        assert CreditPolicy().model_dump() == {
            "hours_per_credit": 10,
            "tolerance_percent": 10,
            "credits_per_year": 120,
            "min_exit_level_credits": None,
        }

    @pytest.mark.parametrize(
        "values",
        [
            {"hours_per_credit": 0},
            {"tolerance_percent": 101},
            {"credits_per_year": 0},
            {"min_exit_level_credits": -1},
            {"hours_per_credit": "ten"},
        ],
    )
    def test_rejects_bad_figures(self, values: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            CreditPolicy(**values)  # type: ignore[arg-type]


class TestCreditCheckApi:
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

    async def test_checks_every_module_year_and_level(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        # Cardiology has two sessions of 90 + 120 minutes: 7 hours. An exam adds 3 more.
        await save(db_session, Assessment(module_id=world.cardio.id, name="Exam", time_minutes=180))

        response = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/credit-check")

        assert response.status_code == 200
        body = response.json()
        assert body["policy"] == {
            "hours_per_credit": 10,
            "tolerance_percent": 10,
            "credits_per_year": 120,
            "min_exit_level_credits": None,
        }
        by_code = {m["code"]: m for m in body["modules"]}
        cardio = by_code["HSC201"]
        assert (
            float(cardio["contact_hours"]),
            float(cardio["self_study_hours"]),
            float(cardio["assessment_hours"]),
            float(cardio["planned_hours"]),
            float(cardio["expected_hours"]),
        ) == (3.0, 4.0, 3.0, 10.0, 120.0)
        assert cardio["status"] == "under"
        assert by_code["HSC101"]["planned_hours"] == "0.0"
        assert [(y["name"], float(y["credits"]), y["status"]) for y in body["years"]] == [
            ("Year 1", 12.0, "under"),
            ("Year 2", 12.0, "under"),
        ]
        assert [(row["level"], float(row["credits"])) for row in body["levels"]] == [(5, 24.0)]
        assert float(body["total_credits"]) == 24
        assert body["programme_total_credits"] == 360
        assert body["exit_level"] == 7
        assert [f["code"] for f in body["findings"]] == ["total_differs_from_programme"]

    async def test_follows_the_institutions_figures(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        institution = await get_institution(db_session)
        assert institution is not None
        institution.settings = {"credits": {"hours_per_credit": 1, "credits_per_year": 12}}
        await db_session.flush()

        body = (
            await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/credit-check")
        ).json()

        assert [y["status"] for y in body["years"]] == ["ok", "ok"]
        cardio = next(m for m in body["modules"] if m["code"] == "HSC201")
        assert (float(cardio["expected_hours"]), cardio["status"]) == (12.0, "under")

    async def test_module_detail_carries_its_own_check(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        detail = (await api_client.get(f"{API}/modules/{world.cardio.id}")).json()

        assert detail["hours"]["status"] == "under"
        assert float(detail["hours"]["planned_hours"]) == 7.0

    async def test_other_programmes_and_missing_versions_are_not_found(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        other = await api_client.get(
            f"{API}/curriculum-versions/{world.other_version.id}/credit-check"
        )
        missing = await api_client.get(f"{API}/curriculum-versions/{uuid.uuid4()}/credit-check")

        assert (other.status_code, missing.status_code) == (404, 404)

    async def test_names_the_qualification_minimum(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        bachelor = QualificationType(
            key="bachelor-test", name="Bachelor's degree", nqf_exit_level=7, min_total_credits=360
        )
        await save(db_session, bachelor)
        world.programme.qualification_type_id = bachelor.id
        world.programme.total_credits = None
        await db_session.flush()

        body = (
            await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/credit-check")
        ).json()

        assert body["qualification_name"] == "Bachelor's degree"
        assert body["qualification_min_credits"] == 360
        assert [f["code"] for f in body["findings"]] == ["total_below_qualification_minimum"]


class TestNarrowRoles:
    async def test_a_module_coordinator_does_not_see_the_version_check(
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

        version = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/credit-check")
        module_detail = await api_client.get(f"{API}/modules/{world.cardio.id}")

        assert version.status_code == 404
        assert module_detail.json()["hours"]["status"] == "under"


class TestSettingsApi:
    async def test_admin_changes_the_credit_policy(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        system_roles: None,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")

        read = (await api_client.get(f"{API}/institution")).json()
        changed = await api_client.patch(
            f"{API}/institution/settings",
            json={"credits": {"hours_per_credit": 12, "tolerance_percent": 5}},
        )
        invalid = await api_client.patch(
            f"{API}/institution/settings", json={"credits": {"hours_per_credit": 0}}
        )
        cleared = await api_client.patch(f"{API}/institution/settings", json={"credits": None})

        assert read["credits"]["hours_per_credit"] == 10
        assert changed.status_code == 200
        assert changed.json()["credits"] == {
            "hours_per_credit": 12,
            "tolerance_percent": 5,
            "credits_per_year": 120,
            "min_exit_level_credits": None,
        }
        assert invalid.status_code == 422
        assert cleared.json()["credits"]["hours_per_credit"] == 10
