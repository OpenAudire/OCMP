"""Tests for the local-account authentication API."""

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.core.config import Settings
from app.models import User
from app.services.users import create_local_user

EMAIL = "lecturer@example.org"
PASSWORD = "a long enough passphrase"
CSRF_HEADER = "X-CSRF-Token"


@pytest.fixture
async def user(db_session: AsyncSession, test_settings: Settings) -> User:
    return await create_local_user(
        db_session, test_settings, email=EMAIL, display_name="Demo Lecturer", password=PASSWORD
    )


async def login(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf(client: AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies["ocmp_csrf"]}


class TestLogin:
    async def test_success_starts_session(self, api_client: AsyncClient, user: User) -> None:
        response = await login(api_client)

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["id"] == str(user.id)
        assert body["user"]["email"] == EMAIL
        assert body["user"]["last_login_at"] is not None
        assert "password_hash" not in body["user"]
        assert body["csrf_token"] == api_client.cookies["ocmp_csrf"]

    async def test_session_cookie_flags(self, api_client: AsyncClient, user: User) -> None:
        response = await login(api_client)

        cookies = {c.split("=", 1)[0]: c.lower() for c in response.headers.get_list("set-cookie")}
        assert "httponly" in cookies["ocmp_session"]
        assert "secure" in cookies["ocmp_session"]
        assert "samesite=lax" in cookies["ocmp_session"]
        assert "httponly" not in cookies["ocmp_csrf"]

    async def test_email_is_case_insensitive(self, api_client: AsyncClient, user: User) -> None:
        response = await login(api_client, email="  LECTURER@Example.org")

        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            (EMAIL, "wrong passphrase here"),
            ("nobody@example.org", PASSWORD),
            ("not-an-email", PASSWORD),
        ],
    )
    async def test_failures_are_indistinguishable(
        self, api_client: AsyncClient, user: User, email: str, password: str
    ) -> None:
        response = await login(api_client, email=email, password=password)

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid email or password."}
        assert "ocmp_session" not in api_client.cookies

    async def test_inactive_user_rejected(
        self, api_client: AsyncClient, user: User, db_session: AsyncSession
    ) -> None:
        user.is_active = False
        await db_session.flush()

        assert (await login(api_client)).status_code == 401

    async def test_failed_login_does_not_log_email(
        self, api_client: AsyncClient, user: User
    ) -> None:
        with capture_logs() as logs:
            await login(api_client, password="wrong passphrase here")

        assert logs
        assert "lecturer" not in str(logs).lower()

    async def test_login_rotates_existing_session(
        self, api_client: AsyncClient, user: User, redis_client: FakeAsyncRedis
    ) -> None:
        await login(api_client)
        old_token = api_client.cookies["ocmp_session"]

        # Re-login without a CSRF header must work (sign-in is CSRF-exempt).
        response = await login(api_client)

        assert response.status_code == 200
        assert api_client.cookies["ocmp_session"] != old_token
        assert len(await redis_client.keys("ocmp:session:*")) == 1


class TestRateLimiting:
    async def test_account_locked_after_repeated_failures(
        self, api_client: AsyncClient, user: User, test_settings: Settings
    ) -> None:
        for _ in range(test_settings.login_rate_limit_per_account):
            assert (await login(api_client, password="wrong passphrase")).status_code == 401

        # Even the right password is refused until the window passes.
        response = await login(api_client)

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0

    async def test_success_resets_account_counter(
        self, api_client: AsyncClient, user: User, test_settings: Settings
    ) -> None:
        for _ in range(test_settings.login_rate_limit_per_account - 1):
            await login(api_client, password="wrong passphrase")
        assert (await login(api_client)).status_code == 200

        assert (await login(api_client, password="wrong passphrase")).status_code == 401
        assert (await login(api_client)).status_code == 200

    async def test_client_address_limited_across_accounts(
        self, api_client: AsyncClient, test_settings: Settings
    ) -> None:
        for n in range(test_settings.login_rate_limit_per_ip):
            await login(api_client, email=f"user{n}@example.org")

        response = await login(api_client, email="another@example.org")

        assert response.status_code == 429


class TestSession:
    async def test_me_requires_session(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/auth/me")

        assert response.status_code == 401

    async def test_me_returns_user(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)

        response = await api_client.get("/api/v1/auth/me")

        assert response.status_code == 200
        assert response.json()["email"] == EMAIL

    async def test_invalid_session_token(self, api_client: AsyncClient) -> None:
        api_client.cookies.set("ocmp_session", "forged-token", domain="testserver.local")

        response = await api_client.get("/api/v1/auth/me")

        assert response.status_code == 401

    async def test_deactivated_user_loses_session(
        self,
        api_client: AsyncClient,
        user: User,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
    ) -> None:
        await login(api_client)
        user.is_active = False
        await db_session.flush()

        response = await api_client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert await redis_client.keys("ocmp:session:*") == []


class TestLogout:
    async def test_logout_requires_csrf_token(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)

        response = await api_client.post("/api/v1/auth/logout")

        assert response.status_code == 403
        assert (await api_client.get("/api/v1/auth/me")).status_code == 200

    async def test_logout_rejects_wrong_csrf_token(
        self, api_client: AsyncClient, user: User
    ) -> None:
        await login(api_client)

        response = await api_client.post("/api/v1/auth/logout", headers={CSRF_HEADER: "0" * 64})

        assert response.status_code == 403

    async def test_logout_ends_session(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)
        old_token = api_client.cookies["ocmp_session"]

        response = await api_client.post("/api/v1/auth/logout", headers=csrf(api_client))

        assert response.status_code == 204
        assert "ocmp_session" not in api_client.cookies
        api_client.cookies.set("ocmp_session", old_token)
        assert (await api_client.get("/api/v1/auth/me")).status_code == 401

    async def test_logout_without_session_succeeds(self, api_client: AsyncClient) -> None:
        response = await api_client.post("/api/v1/auth/logout")

        assert response.status_code == 204


class TestChangePassword:
    NEW_PASSWORD = "a brand new passphrase"

    async def change(
        self, client: AsyncClient, current: str = PASSWORD, new: str = NEW_PASSWORD
    ) -> Response:
        return await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": current, "new_password": new},
            headers=csrf(client),
        )

    async def test_requires_session(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": self.NEW_PASSWORD},
        )

        assert response.status_code == 401

    async def test_changes_password_and_revokes_other_sessions(
        self, api_client: AsyncClient, user: User
    ) -> None:
        await login(api_client)
        other_device = api_client.cookies["ocmp_session"]
        api_client.cookies.clear()
        await login(api_client)

        response = await self.change(api_client)

        assert response.status_code == 204
        assert (await api_client.get("/api/v1/auth/me")).status_code == 200
        current = api_client.cookies["ocmp_session"]
        api_client.cookies.set("ocmp_session", other_device)
        assert (await api_client.get("/api/v1/auth/me")).status_code == 401
        api_client.cookies.set("ocmp_session", current)

        api_client.cookies.clear()
        assert (await login(api_client)).status_code == 401
        assert (await login(api_client, password=self.NEW_PASSWORD)).status_code == 200

    async def test_wrong_current_password(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)

        response = await self.change(api_client, current="not my password")

        assert response.status_code == 400

    async def test_policy_violation(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)

        response = await self.change(api_client, new="short")

        assert response.status_code == 422
        assert "at least 12" in response.json()["detail"]

    async def test_requires_csrf_token(self, api_client: AsyncClient, user: User) -> None:
        await login(api_client)

        response = await api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": self.NEW_PASSWORD},
        )

        assert response.status_code == 403

    async def test_repeated_wrong_current_password_is_rate_limited(
        self, api_client: AsyncClient, user: User, test_settings: Settings
    ) -> None:
        await login(api_client)
        for _ in range(test_settings.login_rate_limit_per_account):
            assert (await self.change(api_client, current="not my password")).status_code == 400

        response = await self.change(api_client)

        assert response.status_code == 429
