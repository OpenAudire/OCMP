"""Tests for personal API tokens (ADR 060)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_token
from app.models import ApiToken, AuditLog
from app.services import api_tokens
from tests.test_curriculum_edit_api import sign_in

API = "/api/v1"

pytestmark = pytest.mark.usefixtures("system_roles")


async def make(
    client: AsyncClient, scopes: list[str] | None = None, days: int = 30, name: str = "Script"
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"{API}/api-tokens", json={"name": name, "scopes": scopes or ["read"], "days": days}
    )
    assert response.status_code == 201, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def use(client: AsyncClient, method: str, path: str, token: str, **kwargs):  # type: ignore[no-untyped-def]
    """A request made with only the token: no cookie, no CSRF header."""
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    return await client.request(method, f"{API}{path}", headers=bearer(token), **kwargs)


class TestMaking:
    async def test_the_token_is_shown_once_and_only_its_hash_is_kept(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        user = await sign_in(api_client, db_session, test_settings, "curriculum_office")

        made = await make(api_client, ["read"], 30)

        assert made["token"].startswith("ocmp_") and len(made["token"]) > 40
        assert made["token_prefix"] == made["token"][:12] and made["state"] == "active"
        stored = await db_session.scalar(select(ApiToken).where(ApiToken.user_id == user.id))
        assert stored is not None and stored.token_hash == hash_token(made["token"])
        assert made["token"] not in stored.token_hash
        listed = (await api_client.get(f"{API}/api-tokens")).json()
        assert [t["id"] for t in listed] == [made["id"]]
        assert "token" not in listed[0]

    async def test_making_and_revoking_are_audited_without_the_hash(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await make(api_client)

        await api_client.delete(f"{API}/api-tokens/{made['id']}")

        rows = list(
            await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "api_tokens"))
        )
        assert {r.action for r in rows} >= {"create", "update"}
        assert made["token"] not in str([(r.before, r.after) for r in rows])
        assert hash_token(made["token"]) not in str([(r.before, r.after) for r in rows])

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "x", "scopes": [], "days": 10},
            {"name": "x", "scopes": ["admin"], "days": 10},
            {"name": "x", "scopes": ["read"], "days": 0},
            {"name": "x", "scopes": ["read"], "days": 366},
            {"name": "   ", "scopes": ["read"], "days": 10},
        ],
    )
    async def test_a_bad_request_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        body: dict,  # type: ignore[type-arg]
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.post(f"{API}/api-tokens", json=body)

        assert response.status_code == 422

    async def test_a_person_may_have_only_so_many_active_tokens(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        for n in range(api_tokens.MAX_ACTIVE):
            await make(api_client, name=f"t{n}")

        response = await api_client.post(
            f"{API}/api-tokens", json={"name": "one more", "scopes": ["read"], "days": 5}
        )

        assert response.status_code == 409


class TestUsing:
    async def test_a_read_token_reads_as_its_owner_and_cannot_write(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        user = await sign_in(api_client, db_session, test_settings, "platform_admin")
        made = await make(api_client, ["read"])

        me = await use(api_client, "GET", "/auth/me", made["token"])
        write = await use(
            api_client,
            "POST",
            "/users",
            made["token"],
            json={"email": "new.person@example.org", "display_name": "N", "password": "x" * 20},
        )

        assert me.status_code == 200 and me.json()["id"] == str(user.id)
        assert write.status_code == 403 and "only read" in write.json()["detail"]

    async def test_a_write_token_writes_with_its_owners_permissions_and_no_more(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        admin_token = await make(api_client, ["read", "write"])
        created = await use(
            api_client,
            "POST",
            "/users",
            admin_token["token"],
            json={
                "email": "made.by.token@example.org",
                "display_name": "Made",
                "password": "a long passphrase for tests 42",
            },
        )
        await sign_in(api_client, db_session, test_settings, "student")
        student_token = await make(api_client, ["read", "write"])
        refused = await use(
            api_client,
            "POST",
            "/users",
            student_token["token"],
            json={"email": "no.way@example.org", "display_name": "N", "password": "x" * 20},
        )

        assert created.status_code == 201
        assert refused.status_code == 403  # the token never exceeds its owner

    async def test_a_token_cannot_make_tokens_or_change_a_password(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await make(api_client, ["read", "write"])

        again = await use(
            api_client,
            "POST",
            "/api-tokens",
            made["token"],
            json={"name": "x", "scopes": ["read"], "days": 5},
        )
        password = await use(
            api_client,
            "POST",
            "/auth/change-password",
            made["token"],
            json={"current_password": "a", "new_password": "b" * 20},
        )
        listing = await use(api_client, "GET", "/api-tokens", made["token"])

        assert again.status_code == 403 and password.status_code == 403
        assert listing.status_code == 403

    @pytest.mark.parametrize("header", ["Bearer ocmp_nonsense", "Bearer ", "Basic abc", "ocmp_x"])
    async def test_a_wrong_or_missing_token_is_a_401(
        self, api_client: AsyncClient, header: str
    ) -> None:
        api_client.cookies.clear()

        response = await api_client.get(f"{API}/auth/me", headers={"Authorization": header})

        assert response.status_code == 401

    async def test_revoked_expired_and_deactivated_tokens_stop_working(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        user = await sign_in(api_client, db_session, test_settings, "curriculum_office")
        revoked = await make(api_client, name="revoked")
        expired = await make(api_client, name="expired")
        kept = await make(api_client, name="kept")
        await api_client.delete(f"{API}/api-tokens/{revoked['id']}")
        row = await db_session.get(ApiToken, expired["id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.flush()

        assert (await use(api_client, "GET", "/auth/me", revoked["token"])).status_code == 401
        assert (await use(api_client, "GET", "/auth/me", expired["token"])).status_code == 401
        assert (await use(api_client, "GET", "/auth/me", kept["token"])).status_code == 200
        user.is_active = False
        await db_session.flush()
        assert (await use(api_client, "GET", "/auth/me", kept["token"])).status_code == 401

    async def test_using_a_token_records_when_but_not_in_the_audit_log(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await make(api_client)
        before = len(list(await db_session.scalars(select(AuditLog))))

        await use(api_client, "GET", "/auth/me", made["token"])

        row = await db_session.get(ApiToken, made["id"])
        await db_session.refresh(row)
        assert row is not None and row.last_used_at is not None
        assert len(list(await db_session.scalars(select(AuditLog)))) == before


class TestRevoking:
    async def test_nobody_revokes_someone_elses_token_without_user_rights(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        theirs = await make(api_client)
        await sign_in(api_client, db_session, test_settings, "student")

        response = await api_client.delete(f"{API}/api-tokens/{theirs['id']}")

        assert response.status_code == 404
        assert (await use(api_client, "GET", "/auth/me", theirs["token"])).status_code == 200

    async def test_an_administrator_sees_and_revokes_anyones_tokens(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        owner = await sign_in(api_client, db_session, test_settings, "curriculum_office")
        theirs = await make(api_client)
        await sign_in(api_client, db_session, test_settings, "platform_admin")

        listed = await api_client.get(f"{API}/users/{owner.id}/api-tokens")
        revoked = await api_client.delete(f"{API}/api-tokens/{theirs['id']}")

        assert [t["id"] for t in listed.json()] == [theirs["id"]]
        assert revoked.status_code == 204
        assert (await use(api_client, "GET", "/auth/me", theirs["token"])).status_code == 401

    async def test_deactivating_a_person_revokes_their_tokens(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        owner = await sign_in(api_client, db_session, test_settings, "curriculum_office")
        theirs = await make(api_client)
        await sign_in(api_client, db_session, test_settings, "platform_admin")

        response = await api_client.patch(f"{API}/users/{owner.id}", json={"is_active": False})

        assert response.status_code == 200
        row = await db_session.get(ApiToken, theirs["id"])
        await db_session.refresh(row)
        assert row is not None and row.revoked_at is not None

    async def test_listing_needs_a_signed_in_person(self, api_client: AsyncClient) -> None:
        api_client.cookies.clear()

        assert (await api_client.get(f"{API}/api-tokens")).status_code == 401
