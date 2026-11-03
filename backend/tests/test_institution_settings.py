"""Tests for institution settings: terminology, profiles, default taxonomy, mapping policy."""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.profiles import Feature, Profile, Term, features_for
from app.models import Institution, TaxonomyScale, User
from app.services.audit import entity_history
from app.services.authorization import InvalidRequestError
from app.services.institution_settings import (
    InstitutionSettings,
    get_institution,
    parse_settings,
    update_settings,
)
from app.services.users import create_local_user
from tests.authz_helpers import grant
from tests.factories import InstitutionFactory

EN_LOCALE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "locales" / "en.json"
)


@pytest.fixture
async def institution(db_session: AsyncSession) -> Institution:
    institution = InstitutionFactory(name="Demo University", short_code="DEMO")
    db_session.add(institution)
    await db_session.flush()
    return institution


class TestParsing:
    def test_defaults(self) -> None:
        settings = parse_settings({})

        assert settings.terminology == {}
        assert settings.profiles == {Profile.CORE}
        assert settings.features == frozenset()
        assert settings.default_taxonomy_scale is None
        assert not settings.mapping.four_eyes

    def test_core_profile_is_always_on(self) -> None:
        settings = parse_settings({"profiles": ["health"]})

        assert settings.profiles == {Profile.CORE, Profile.HEALTH}
        assert Feature.ROLE_BALANCE_REPORT in settings.features

    @pytest.mark.parametrize(
        "raw",
        [
            {"profiles": ["engineering"]},
            {"terminology": {"widget": {"singular": "W", "plural": "Ws"}}},
            {"terminology": {"module": {"singular": "  ", "plural": "Courses"}}},
            {"terminology": {"module": {"singular": "Course"}}},
            {"mapping": {"four_eyes": "yes"}},
        ],
        ids=["unknown-profile", "unknown-term", "blank-word", "missing-plural", "bad-mapping"],
    )
    def test_invalid_settings(self, raw: dict[str, object]) -> None:
        with pytest.raises(InvalidRequestError):
            parse_settings(raw)

    def test_unknown_sections_are_ignored_when_reading(self) -> None:
        assert parse_settings({"future_feature": {"x": 1}}) == InstitutionSettings()

    def test_features_per_profile(self) -> None:
        assert features_for({Profile.CORE}) == frozenset()
        assert features_for({Profile.CORE, Profile.HEALTH}) == {
            Feature.ROLE_BALANCE_REPORT,
            Feature.COUNCIL_EVIDENCE_PACK,
            Feature.CLINICAL_PLACEMENTS,
        }


class TestUpdate:
    async def test_replace_sections_and_keep_others(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        institution.settings = {"future_feature": {"keep": True}, "mapping": {"four_eyes": True}}
        await db_session.flush()

        settings = await update_settings(
            db_session,
            institution,
            {
                "terminology": {"module": {"singular": " Course ", "plural": "Courses"}},
                "profiles": ["health", "core", "health"],
            },
        )

        assert settings.terminology[Term.MODULE].singular == "Course"
        assert institution.settings == {
            "future_feature": {"keep": True},
            "mapping": {"four_eyes": True},
            "terminology": {"module": {"singular": "Course", "plural": "Courses"}},
            "profiles": ["core", "health"],
        }

    async def test_default_taxonomy_must_exist(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        with pytest.raises(InvalidRequestError, match="No taxonomy scale"):
            await update_settings(db_session, institution, {"default_taxonomy_scale": "nope"})

        db_session.add(TaxonomyScale(key="bloom-revised", name="Bloom (revised)"))
        await db_session.flush()
        settings = await update_settings(
            db_session, institution, {"default_taxonomy_scale": "bloom-revised"}
        )
        assert settings.default_taxonomy_scale == "bloom-revised"

    async def test_unknown_section(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        with pytest.raises(InvalidRequestError, match="Unknown settings sections"):
            await update_settings(db_session, institution, {"colour_scheme": "blue"})

    async def test_invalid_update_changes_nothing(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await update_settings(db_session, institution, {"profiles": ["unknown"]})

        assert institution.settings == {}

    async def test_changes_are_audited(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        await update_settings(db_session, institution, {"profiles": ["health"]})

        last = (await entity_history(db_session, "institutions", institution.id))[-1]
        assert last.action == "update"
        assert last.after == {"settings": {"profiles": ["core", "health"]}}

    async def test_single_institution_lookup(
        self, db_session: AsyncSession, institution: Institution
    ) -> None:
        assert await get_institution(db_session) is institution
        institution.soft_delete()
        await db_session.flush()
        assert await get_institution(db_session) is None


def test_every_term_has_default_wording_in_the_frontend() -> None:
    """Backend terms and frontend translations must not drift apart."""
    terms = json.loads(EN_LOCALE.read_text(encoding="utf-8"))["terms"]

    expected = {f"{t.value}_{form}" for t in Term for form in ("one", "other")}
    assert set(terms) == expected
    assert all(value.strip() for value in terms.values())


@pytest.mark.usefixtures("system_roles")
class TestAPI:
    async def sign_in(
        self, client: AsyncClient, db: AsyncSession, settings: Settings, role: str
    ) -> User:
        email = f"{role}@example.org"
        user = await create_local_user(
            db, settings, email=email, display_name=role, password="a long enough passphrase"
        )
        await grant(db, user, role)
        client.cookies.clear()
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "a long enough passphrase"}
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies["ocmp_csrf"]
        return user

    async def test_not_set_up(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        await self.sign_in(api_client, db_session, test_settings, "student")

        assert (await api_client.get("/api/v1/institution")).status_code == 404

    async def test_any_user_reads_terminology_and_features(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
    ) -> None:
        institution.settings = {
            "terminology": {"module": {"singular": "Course", "plural": "Courses"}},
            "profiles": ["health"],
        }
        await db_session.flush()
        await self.sign_in(api_client, db_session, test_settings, "student")

        body = (await api_client.get("/api/v1/institution")).json()

        assert body["name"] == "Demo University"
        assert body["terminology"] == {"module": {"singular": "Course", "plural": "Courses"}}
        assert body["profiles"] == ["core", "health"]
        assert "role_balance_report" in body["features"]
        assert body["mapping"] == {
            "four_eyes": False,
            "second_review_for_rejects": False,
            "bulk_accept_min_percent": 80,
            "bulk_accept_max_links": 200,
        }

    async def test_requires_sign_in(self, api_client: AsyncClient) -> None:
        assert (await api_client.get("/api/v1/institution")).status_code == 401

    async def test_admin_changes_settings(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
    ) -> None:
        await self.sign_in(api_client, db_session, test_settings, "platform_admin")

        response = await api_client.patch(
            "/api/v1/institution/settings",
            json={
                "terminology": {
                    "module": {"singular": "Course", "plural": "Courses"},
                    "learning_event": {"singular": "Class", "plural": "Classes"},
                },
                "mapping": {"four_eyes": True, "second_review_for_rejects": True},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body["terminology"]) == {"module", "learning_event"}
        assert body["mapping"]["second_review_for_rejects"] is True
        assert body["profiles"] == ["core"]  # untouched

        cleared = await api_client.patch("/api/v1/institution/settings", json={"terminology": None})
        assert cleared.json()["terminology"] == {}
        assert cleared.json()["mapping"]["four_eyes"] is True

    async def test_the_near_duplicate_threshold_defaults_to_the_measured_value_and_is_changed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
    ) -> None:
        await self.sign_in(api_client, db_session, test_settings, "platform_admin")

        before = await api_client.get("/api/v1/institution")
        changed = await api_client.patch(
            "/api/v1/institution/settings", json={"quality": {"near_duplicate_min_percent": 90}}
        )
        cleared = await api_client.patch("/api/v1/institution/settings", json={"quality": None})

        assert before.json()["quality"] == {"near_duplicate_min_percent": 95}
        assert changed.json()["quality"] == {"near_duplicate_min_percent": 90}
        assert cleared.json()["quality"] == {"near_duplicate_min_percent": 95}

    @pytest.mark.parametrize(
        "body",
        [
            {"profiles": ["engineering"]},
            {"terminology": {"widget": {"singular": "W", "plural": "Ws"}}},
            {"default_taxonomy_scale": "missing-scale"},
            {"colour_scheme": "blue"},
            {"quality": {"near_duplicate_min_percent": 84}},
            {"quality": {"near_duplicate_min_percent": 101}},
        ],
    )
    async def test_invalid_changes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
        body: dict[str, object],
    ) -> None:
        await self.sign_in(api_client, db_session, test_settings, "platform_admin")

        response = await api_client.patch("/api/v1/institution/settings", json=body)

        assert response.status_code == 422

    async def test_only_settings_managers_change_settings(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        institution: Institution,
    ) -> None:
        await self.sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.patch(
            "/api/v1/institution/settings", json={"profiles": ["health"]}
        )

        assert response.status_code == 403
