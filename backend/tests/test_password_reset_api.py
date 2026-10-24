"""Tests for the password reset API."""

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import User
from app.services.users import create_local_user
from tests.conftest import EnqueuedJob
from tests.fakes import FakeEmailSender
from tests.test_password_reset import token_from

EMAIL = "lecturer@example.org"
PASSWORD = "a long enough passphrase"
NEW_PASSWORD = "a brand new passphrase"
REQUEST_URL = "/api/v1/auth/password-reset/request"
CONFIRM_URL = "/api/v1/auth/password-reset/confirm"


@pytest.fixture
async def user(db_session: AsyncSession, test_settings: Settings) -> User:
    return await create_local_user(
        db_session, test_settings, email=EMAIL, display_name="Demo Lecturer", password=PASSWORD
    )


async def issue_token(
    db_session: AsyncSession, redis_client: FakeAsyncRedis, test_settings: Settings
) -> str:
    """Run what the worker would do for a reset request and return the emailed token."""
    from app.services.password_reset import send_reset_email

    sender = FakeEmailSender()
    await send_reset_email(db_session, redis_client, test_settings, sender, EMAIL)
    return token_from(sender)


async def login(client: AsyncClient, password: str = PASSWORD) -> int:
    response = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": password})
    return response.status_code


class TestRequest:
    async def test_same_response_whether_or_not_account_exists(
        self, api_client: AsyncClient, user: User, enqueued_jobs: list[EnqueuedJob]
    ) -> None:
        known = await api_client.post(REQUEST_URL, json={"email": EMAIL})
        unknown = await api_client.post(REQUEST_URL, json={"email": "nobody@example.org"})

        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert [(j.actor, j.args) for j in enqueued_jobs] == [
            ("send_password_reset", (EMAIL,)),
            ("send_password_reset", ("nobody@example.org",)),
        ]

    async def test_limited_per_client_address(
        self,
        api_client: AsyncClient,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
    ) -> None:
        for _ in range(test_settings.password_reset_per_ip):
            await api_client.post(REQUEST_URL, json={"email": EMAIL})

        response = await api_client.post(REQUEST_URL, json={"email": EMAIL})

        assert response.status_code == 429
        assert len(enqueued_jobs) == test_settings.password_reset_per_ip


class TestConfirm:
    async def test_sets_password_and_signs_out_everywhere(
        self,
        api_client: AsyncClient,
        user: User,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
    ) -> None:
        assert await login(api_client) == 200
        token = await issue_token(db_session, redis_client, test_settings)

        response = await api_client.post(
            CONFIRM_URL,
            json={"token": token, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": api_client.cookies["ocmp_csrf"]},
        )

        assert response.status_code == 204
        assert (await api_client.get("/api/v1/auth/me")).status_code == 401
        assert await redis_client.keys("ocmp:session:*") == []
        api_client.cookies.clear()
        assert await login(api_client) == 401
        assert await login(api_client, NEW_PASSWORD) == 200
        assert ("send_password_changed_notice", (str(user.id),)) in [
            (j.actor, j.args) for j in enqueued_jobs
        ]

    async def test_works_without_a_session(
        self,
        api_client: AsyncClient,
        user: User,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
    ) -> None:
        token = await issue_token(db_session, redis_client, test_settings)

        response = await api_client.post(
            CONFIRM_URL, json={"token": token, "new_password": NEW_PASSWORD}
        )

        assert response.status_code == 204

    async def test_clears_sign_in_delays(
        self,
        api_client: AsyncClient,
        user: User,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr("app.api.v1.auth.sleep", fake_sleep)
        for _ in range(6):
            await login(api_client, "wrong passphrase")
        token = await issue_token(db_session, redis_client, test_settings)
        await api_client.post(CONFIRM_URL, json={"token": token, "new_password": NEW_PASSWORD})
        sleeps.clear()

        assert await login(api_client, NEW_PASSWORD) == 200
        assert sleeps == []

    async def test_invalid_token(self, api_client: AsyncClient, user: User) -> None:
        response = await api_client.post(
            CONFIRM_URL, json={"token": "made-up-token", "new_password": NEW_PASSWORD}
        )

        assert response.status_code == 400
        assert "invalid or has expired" in response.json()["detail"]

    async def test_weak_password(
        self,
        api_client: AsyncClient,
        user: User,
        db_session: AsyncSession,
        redis_client: FakeAsyncRedis,
        test_settings: Settings,
    ) -> None:
        token = await issue_token(db_session, redis_client, test_settings)

        response = await api_client.post(
            CONFIRM_URL, json={"token": token, "new_password": "short"}
        )

        assert response.status_code == 422
        assert "at least 12" in response.json()["detail"]


async def test_change_password_sends_notice(
    api_client: AsyncClient, user: User, enqueued_jobs: list[EnqueuedJob]
) -> None:
    await login(api_client)

    response = await api_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": api_client.cookies["ocmp_csrf"]},
    )

    assert response.status_code == 204
    assert [(j.actor, j.args) for j in enqueued_jobs] == [
        ("send_password_changed_notice", (str(user.id),))
    ]
