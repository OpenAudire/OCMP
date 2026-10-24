"""Tests for SSO sign-in through the API, against a fake OpenID provider."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.oidc import get_oidc_client, safe_next
from app.core.config import Settings
from app.models import User, UserIdentity
from app.services.oidc import OIDCClient
from app.services.users import create_local_user
from tests.fake_idp import CLIENT_ID, CLIENT_SECRET, DISCOVERY_URL, ISSUER, FakeIdP

LOGIN_URL = "/api/v1/auth/oidc/login"
CALLBACK_URL = "/api/v1/auth/oidc/callback"


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
def sso(api_app: FastAPI, test_settings: Settings, idp: FakeIdP) -> Settings:
    """Enable OIDC in the app's settings and point it at the fake provider."""
    for name, value in {
        "oidc_enabled": True,
        "oidc_provider_name": "University SSO",
        "oidc_discovery_url": DISCOVERY_URL,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": CLIENT_SECRET,
    }.items():
        setattr(test_settings, name, value)
    client = OIDCClient(test_settings, httpx.AsyncClient(transport=idp.transport))
    api_app.dependency_overrides[get_oidc_client] = lambda: client
    return test_settings


def location(response: Response) -> str:
    assert response.status_code == 302, response.text
    return response.headers["location"]


async def sign_in(
    api_client: AsyncClient, idp: FakeIdP, *, next: str | None = None, **claims: Any
) -> Response:
    """Go through the whole flow as a browser would."""
    params = {"next": next} if next else {}
    authorize_url = location(await api_client.get(LOGIN_URL, params=params))
    state = parse_qs(urlsplit(authorize_url).query)["state"][0]
    code = idp.authorize(authorize_url, **claims)
    return await api_client.get(CALLBACK_URL, params={"code": code, "state": state})


async def identities(db: AsyncSession) -> list[UserIdentity]:
    return list((await db.execute(select(UserIdentity))).scalars())


class TestInfo:
    async def test_disabled_by_default(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/auth/oidc")

        assert response.json() == {"enabled": False, "provider_name": "SSO"}
        assert (await api_client.get(LOGIN_URL)).status_code == 404

    @pytest.mark.usefixtures("sso")
    async def test_enabled(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/auth/oidc")

        assert response.json() == {"enabled": True, "provider_name": "University SSO"}


@pytest.mark.usefixtures("sso")
class TestSignIn:
    async def test_first_sign_in_creates_account(
        self, api_client: AsyncClient, idp: FakeIdP, db_session: AsyncSession
    ) -> None:
        response = await sign_in(api_client, idp, next="/modules?year=2")

        assert location(response) == "/modules?year=2"
        me = (await api_client.get("/api/v1/auth/me")).json()
        assert me["email"] == "sso.user@example.org"
        assert me["display_name"] == "SSO Demo User"
        (identity,) = await identities(db_session)
        assert (identity.protocol, identity.issuer, identity.subject) == (
            "oidc",
            ISSUER,
            "subject-1",
        )
        user = await db_session.get(User, identity.user_id)
        assert user is not None
        assert user.password_hash is None  # SSO-only: no local password
        assert "ocmp_oidc_state" not in api_client.cookies

    async def test_returning_user_is_matched_by_subject_not_email(
        self, api_client: AsyncClient, idp: FakeIdP, db_session: AsyncSession
    ) -> None:
        await sign_in(api_client, idp)
        first_id = (await api_client.get("/api/v1/auth/me")).json()["id"]
        api_client.cookies.clear()

        # Email changed at the provider; same subject.
        await sign_in(api_client, idp, email="renamed@example.org")

        me = (await api_client.get("/api/v1/auth/me")).json()
        assert me["id"] == first_id
        assert len(await identities(db_session)) == 1

    async def test_existing_local_account_is_not_taken_over(
        self,
        api_client: AsyncClient,
        idp: FakeIdP,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await create_local_user(
            db_session,
            test_settings,
            email="victim@example.org",
            display_name="Local User",
            password="a long enough passphrase",
        )

        response = await sign_in(api_client, idp, sub="attacker", email="Victim@example.org")

        assert location(response) == "/login?sso_error=account_exists"
        assert "ocmp_session" not in api_client.cookies
        assert await identities(db_session) == []

    async def test_username_used_when_email_claim_missing(
        self, api_client: AsyncClient, idp: FakeIdP
    ) -> None:
        response = await sign_in(
            api_client, idp, email=None, preferred_username="upn.user@example.org"
        )

        assert location(response) == "/"
        assert (await api_client.get("/api/v1/auth/me")).json()["email"] == ("upn.user@example.org")

    async def test_no_email_at_all(self, api_client: AsyncClient, idp: FakeIdP) -> None:
        response = await sign_in(api_client, idp, email=None, preferred_username="no-at-sign")

        assert location(response) == "/login?sso_error=no_email"

    async def test_disabled_account(
        self, api_client: AsyncClient, idp: FakeIdP, db_session: AsyncSession
    ) -> None:
        await sign_in(api_client, idp)
        (identity,) = await identities(db_session)
        user = await db_session.get(User, identity.user_id)
        assert user is not None
        user.is_active = False
        await db_session.flush()
        api_client.cookies.clear()

        response = await sign_in(api_client, idp)

        assert location(response) == "/login?sso_error=account_disabled"

    async def test_auto_provisioning_can_be_turned_off(
        self, api_client: AsyncClient, idp: FakeIdP, sso: Settings
    ) -> None:
        sso.oidc_auto_provision = False

        response = await sign_in(api_client, idp)

        assert location(response) == "/login?sso_error=not_provisioned"

    async def test_invalid_id_token(self, api_client: AsyncClient, idp: FakeIdP) -> None:
        response = await sign_in(api_client, idp, aud="someone-else")

        assert location(response) == "/login?sso_error=sso_failed"
        assert "ocmp_session" not in api_client.cookies

    async def test_provider_unreachable(self, api_client: AsyncClient, idp: FakeIdP) -> None:
        idp.down = True

        response = await api_client.get(LOGIN_URL)

        assert location(response) == "/login?sso_error=sso_unavailable"

    async def test_user_cancels_at_provider(self, api_client: AsyncClient) -> None:
        response = await api_client.get(
            CALLBACK_URL, params={"error": "access_denied", "state": "x"}
        )

        assert location(response) == "/login?sso_error=sso_cancelled"

    async def test_replayed_callback_is_rejected(
        self, api_client: AsyncClient, idp: FakeIdP
    ) -> None:
        authorize_url = location(await api_client.get(LOGIN_URL))
        state = parse_qs(urlsplit(authorize_url).query)["state"][0]
        code = idp.authorize(authorize_url)
        await api_client.get(CALLBACK_URL, params={"code": code, "state": state})
        api_client.cookies.set("ocmp_oidc_state", state, path="/api/v1/auth/oidc")

        response = await api_client.get(CALLBACK_URL, params={"code": code, "state": state})

        assert location(response) == "/login?sso_error=sso_expired"

    async def test_callback_from_another_browser_is_rejected(
        self, api_client: AsyncClient, idp: FakeIdP
    ) -> None:
        """Login CSRF: an attacker's own code/state injected into a victim's browser."""
        authorize_url = location(await api_client.get(LOGIN_URL))
        state = parse_qs(urlsplit(authorize_url).query)["state"][0]
        code = idp.authorize(authorize_url)
        api_client.cookies.clear()  # the victim's browser has no matching state cookie

        response = await api_client.get(CALLBACK_URL, params={"code": code, "state": state})

        assert location(response) == "/login?sso_error=sso_expired"
        assert "ocmp_session" not in api_client.cookies

    async def test_state_cookie_is_http_only_and_scoped(self, api_client: AsyncClient) -> None:
        response = await api_client.get(LOGIN_URL)

        cookie = response.headers["set-cookie"].lower()
        assert cookie.startswith("ocmp_oidc_state=")
        for flag in ("httponly", "secure", "samesite=lax", "path=/api/v1/auth/oidc"):
            assert flag in cookie

    async def test_open_redirect_is_blocked(self, api_client: AsyncClient, idp: FakeIdP) -> None:
        response = await sign_in(api_client, idp, next="//evil.example.com/phish")

        assert location(response) == "/"

    async def test_sso_start_counts_toward_address_limit(
        self, api_client: AsyncClient, test_settings: Settings
    ) -> None:
        for _ in range(test_settings.login_rate_limit_per_ip):
            await api_client.get(LOGIN_URL)

        response = await api_client.get(LOGIN_URL)

        assert location(response) == "/login?sso_error=too_many_attempts"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/modules", "/modules"),
        ("/a?b=c#d", "/a?b=c#d"),
        (None, "/"),
        ("", "/"),
        ("modules", "/"),
        ("//evil.example.com", "/"),
        ("/\\evil.example.com", "/"),
        ("https://evil.example.com", "/"),
        ("/ok\r\nSet-Cookie: x=y", "/"),
        ("/" + "a" * 3000, "/"),
    ],
)
def test_safe_next(target: str | None, expected: str) -> None:
    assert safe_next(target) == expected
