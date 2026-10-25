"""Tests for first-run setup."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AuditLog, Institution, User
from app.services.authorization import user_assignments
from app.services.setup import setup_token, token_matches
from tests.factories import InstitutionFactory


def body(settings: Settings, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "token": setup_token(settings),
        "institution_name": "Demo University",
        "institution_short_code": "demo",
        "country": "za",
        "health_profile": True,
        "admin_display_name": "First Admin",
        "admin_email": "first.admin@example.org",
        "admin_password": "a long enough passphrase",
    }
    values.update(overrides)
    return values


class TestToken:
    def test_format_and_stability(self, test_settings: Settings) -> None:
        token = setup_token(test_settings)

        assert len(token) == 19
        assert token.count("-") == 3
        assert token == setup_token(test_settings)

    def test_depends_on_the_secret_key(self, test_settings: Settings) -> None:
        other = test_settings.model_copy(
            update={"secret_key": "another-secret-key-of-32-characters!!"}
        )

        assert setup_token(other) != setup_token(test_settings)

    def test_matching_ignores_case_spaces_and_dashes(self, test_settings: Settings) -> None:
        token = setup_token(test_settings)

        assert token_matches(test_settings, token.lower().replace("-", " "))
        assert not token_matches(test_settings, "AAAA-BBBB-CCCC-DDDD")
        assert not token_matches(test_settings, "")


class TestSetupAPI:
    async def test_status(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        assert (await api_client.get("/api/v1/setup/status")).json() == {"needs_setup": True}

        db_session.add(InstitutionFactory())
        await db_session.flush()

        assert (await api_client.get("/api/v1/setup/status")).json() == {"needs_setup": False}

    async def test_creates_institution_and_signed_in_admin(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        response = await api_client.post("/api/v1/setup", json=body(test_settings))

        assert response.status_code == 201
        assert response.json()["user"]["email"] == "first.admin@example.org"
        institution = (await db_session.execute(select(Institution))).scalar_one()
        assert (institution.name, institution.short_code, institution.country) == (
            "Demo University",
            "DEMO",
            "ZA",
        )
        assert institution.settings["profiles"] == ["core", "health"]
        admin = (await db_session.execute(select(User))).scalar_one()
        assert [a.role.key for a in await user_assignments(db_session, admin.id)] == [
            "platform_admin"
        ]
        # The admin is signed in and can use admin endpoints straight away.
        me = await api_client.get("/api/v1/auth/me")
        assert me.json()["id"] == str(admin.id)
        assert (await api_client.get("/api/v1/users")).status_code == 200

    async def test_is_recorded_in_the_audit_log(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        await api_client.post("/api/v1/setup", json=body(test_settings))

        entries = (
            (
                await db_session.execute(
                    select(AuditLog).where(AuditLog.context["operation"].astext == "setup.complete")
                )
            )
            .scalars()
            .all()
        )
        assert {e.entity_type for e in entries} >= {"institutions", "users", "role_assignments"}

    async def test_wrong_token(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        response = await api_client.post(
            "/api/v1/setup", json=body(test_settings, token="AAAA-BBBB-CCCC-DDDD")
        )

        assert response.status_code == 403
        assert (await db_session.execute(select(Institution))).first() is None

    async def test_only_once(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        assert (await api_client.post("/api/v1/setup", json=body(test_settings))).status_code == 201
        api_client.cookies.clear()

        again = await api_client.post(
            "/api/v1/setup",
            json=body(test_settings, admin_email="intruder@example.org"),
        )

        assert again.status_code == 409
        users = (await db_session.execute(select(User.email))).scalars().all()
        assert users == ["first.admin@example.org"]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"admin_password": "short"},
            {"admin_email": "not-an-email"},
            {"country": "ZAF"},
            {"institution_short_code": "has space"},
        ],
        ids=["weak-password", "bad-email", "bad-country", "bad-short-code"],
    )
    async def test_invalid_input_changes_nothing(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        overrides: dict[str, object],
    ) -> None:
        response = await api_client.post("/api/v1/setup", json=body(test_settings, **overrides))

        assert response.status_code == 422
        assert (await db_session.execute(select(Institution))).first() is None
        assert (await db_session.execute(select(User))).first() is None

    async def test_attempts_are_rate_limited(
        self, api_client: AsyncClient, test_settings: Settings
    ) -> None:
        for _ in range(10):
            await api_client.post("/api/v1/setup", json=body(test_settings, token="WRONG"))

        response = await api_client.post("/api/v1/setup", json=body(test_settings))

        assert response.status_code == 429

    async def test_stale_session_cookie_does_not_block_setup(
        self, api_client: AsyncClient, test_settings: Settings
    ) -> None:
        api_client.cookies.set("ocmp_session", "left-over-from-an-old-install")

        response = await api_client.post("/api/v1/setup", json=body(test_settings))

        assert response.status_code == 201
