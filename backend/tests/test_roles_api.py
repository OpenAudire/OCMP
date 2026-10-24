"""Tests for the user, role and role assignment API."""

from collections.abc import Iterator

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import User
from app.services.authorization import INSTANCE, ScopeRef
from app.services.users import create_local_user
from tests.authz_helpers import ScopeTree, curriculum_scopes, grant, new_faculty

pytestmark = pytest.mark.usefixtures("system_roles")

PASSWORD = "a long enough passphrase"


@pytest.fixture
def tree() -> Iterator[ScopeTree]:
    with curriculum_scopes() as scopes:
        yield scopes


async def make_user(db: AsyncSession, settings: Settings, email: str) -> User:
    return await create_local_user(
        db, settings, email=email, display_name=email.split("@")[0], password=PASSWORD
    )


async def sign_in_as(
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    email: str,
    role_key: str | None = None,
    scope: ScopeRef = INSTANCE,
) -> User:
    user = await make_user(db, settings, email)
    if role_key:
        await grant(db, user, role_key, scope)
    client.cookies.clear()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["ocmp_csrf"]
    return user


@pytest.fixture
async def admin(api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings) -> User:
    return await sign_in_as(
        api_client, db_session, test_settings, "admin@example.org", "platform_admin"
    )


class TestAccessControl:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/users"),
            ("GET", "/api/v1/roles"),
            ("POST", "/api/v1/roles"),
            ("GET", "/api/v1/permissions"),
            ("POST", "/api/v1/role-assignments"),
            ("GET", "/api/v1/auth/me/roles"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, path, json={})

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("GET", "/api/v1/users", None),
            (
                "POST",
                "/api/v1/users",
                {"email": "x@example.org", "display_name": "X", "password": PASSWORD},
            ),
            (
                "POST",
                "/api/v1/roles",
                {
                    "key": "r",
                    "name": "R",
                    "permissions": ["reports.view"],
                    "scope_types": ["faculty"],
                },
            ),
        ],
    )
    async def test_needs_admin_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        method: str,
        path: str,
        body: dict[str, object] | None,
    ) -> None:
        # Curriculum office for the whole instance still cannot manage users or roles.
        await sign_in_as(
            api_client, db_session, test_settings, "office@example.org", "curriculum_office"
        )

        response = await api_client.request(method, path, json=body)

        assert response.status_code == 403


class TestUsers:
    async def test_create_list_and_get(self, api_client: AsyncClient, admin: User) -> None:
        created = await api_client.post(
            "/api/v1/users",
            json={
                "email": "Lecturer@Example.org",
                "display_name": "Demo Lecturer",
                "password": PASSWORD,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["email"] == "Lecturer@example.org"
        assert body["has_password"] is True
        assert "password_hash" not in body

        listing = (await api_client.get("/api/v1/users", params={"search": "lectur"})).json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == body["id"]
        assert (await api_client.get(f"/api/v1/users/{body['id']}")).status_code == 200

    async def test_search_treats_wildcards_literally(
        self, api_client: AsyncClient, admin: User
    ) -> None:
        listing = (await api_client.get("/api/v1/users", params={"search": "%"})).json()

        assert listing["total"] == 0

    async def test_pagination(
        self,
        api_client: AsyncClient,
        admin: User,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        for n in range(3):
            await make_user(db_session, test_settings, f"user{n}@example.org")

        page = (await api_client.get("/api/v1/users", params={"limit": 2, "offset": 1})).json()

        assert page["total"] == 4
        assert len(page["items"]) == 2

    @pytest.mark.parametrize(
        ("body", "status"),
        [
            ({"email": "admin@example.org", "display_name": "Dup", "password": PASSWORD}, 409),
            ({"email": "new@example.org", "display_name": "Weak", "password": "short"}, 422),
            ({"email": "not-an-email", "display_name": "Bad", "password": PASSWORD}, 422),
        ],
    )
    async def test_create_errors(
        self, api_client: AsyncClient, admin: User, body: dict[str, str], status: int
    ) -> None:
        assert (await api_client.post("/api/v1/users", json=body)).status_code == status

    async def test_deactivate_ends_sessions(
        self,
        api_client: AsyncClient,
        admin: User,
        db_session: AsyncSession,
        test_settings: Settings,
        redis_client: FakeAsyncRedis,
    ) -> None:
        target = await make_user(db_session, test_settings, "leaver@example.org")
        from app.services import sessions

        await sessions.create_session(redis_client, target.id, 3600)

        response = await api_client.patch(f"/api/v1/users/{target.id}", json={"is_active": False})

        assert response.status_code == 200
        assert response.json()["is_active"] is False
        assert await redis_client.smembers(f"ocmp:user-sessions:{target.id}") == set()

        again = await api_client.patch(f"/api/v1/users/{target.id}", json={"is_active": True})
        assert again.json()["is_active"] is True

    async def test_cannot_deactivate_self(self, api_client: AsyncClient, admin: User) -> None:
        response = await api_client.patch(f"/api/v1/users/{admin.id}", json={"is_active": False})

        assert response.status_code == 409

    async def test_cannot_deactivate_last_platform_admin(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        sole_admin = await make_user(db_session, test_settings, "sole@example.org")
        await grant(db_session, sole_admin, "platform_admin")
        # A user manager who is not a platform admin.
        from app.services.authorization import create_custom_role

        await create_custom_role(
            db_session,
            sole_admin,
            key="user_manager",
            name="User manager",
            description="",
            permissions=["users.manage"],
            scope_types=["instance"],
            requires_expiry=False,
        )
        await sign_in_as(
            api_client, db_session, test_settings, "manager@example.org", "user_manager"
        )

        response = await api_client.patch(
            f"/api/v1/users/{sole_admin.id}", json={"is_active": False}
        )

        assert response.status_code == 409
        assert "last platform admin" in response.json()["detail"]

    async def test_rename(self, api_client: AsyncClient, admin: User) -> None:
        response = await api_client.patch(
            f"/api/v1/users/{admin.id}", json={"display_name": "  Chief Admin "}
        )

        assert response.json()["display_name"] == "Chief Admin"

    async def test_unknown_user(self, api_client: AsyncClient, admin: User) -> None:
        response = await api_client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404


class TestRolesEndpoints:
    async def test_permissions_and_roles_are_listed(
        self, api_client: AsyncClient, admin: User
    ) -> None:
        permissions = (await api_client.get("/api/v1/permissions")).json()
        roles = (await api_client.get("/api/v1/roles")).json()

        assert {"key": "curriculum.view", "implies": ["curriculum.view_published"]} in permissions
        assert {r["key"] for r in roles} >= {"platform_admin", "student", "external_reviewer"}

    async def test_custom_role_lifecycle(self, api_client: AsyncClient, admin: User) -> None:
        created = await api_client.post(
            "/api/v1/roles",
            json={
                "key": "timetabler",
                "name": "Timetabler",
                "permissions": ["curriculum.view"],
                "scope_types": ["faculty"],
            },
        )
        assert created.status_code == 201
        assert created.json()["is_system"] is False

        updated = await api_client.patch("/api/v1/roles/timetabler", json={"name": "Scheduler"})
        assert updated.json()["name"] == "Scheduler"

        assert (await api_client.delete("/api/v1/roles/timetabler")).status_code == 204
        assert (await api_client.delete("/api/v1/roles/timetabler")).status_code == 404

    @pytest.mark.parametrize(
        ("body", "status"),
        [
            ({"key": "x1", "name": "X", "permissions": ["bogus"], "scope_types": ["faculty"]}, 422),
            (
                {
                    "key": "x2",
                    "name": "X",
                    "permissions": ["reports.view"],
                    "scope_types": ["galaxy"],
                },
                422,
            ),
            (
                {
                    "key": "student",
                    "name": "X",
                    "permissions": ["reports.view"],
                    "scope_types": ["faculty"],
                },
                409,
            ),
        ],
    )
    async def test_create_role_errors(
        self, api_client: AsyncClient, admin: User, body: dict[str, object], status: int
    ) -> None:
        assert (await api_client.post("/api/v1/roles", json=body)).status_code == status

    async def test_system_role_is_read_only(self, api_client: AsyncClient, admin: User) -> None:
        assert (
            await api_client.patch("/api/v1/roles/student", json={"name": "Learner"})
        ).status_code == 409
        assert (await api_client.delete("/api/v1/roles/student")).status_code == 409


class TestAssignments:
    async def test_admin_assigns_and_removes(
        self,
        api_client: AsyncClient,
        admin: User,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        target = await make_user(db_session, test_settings, "office@example.org")
        faculty, _ = await new_faculty(db_session)

        created = await api_client.post(
            "/api/v1/role-assignments",
            json={
                "user_id": str(target.id),
                "role_key": "curriculum_office",
                "scope_type": "faculty",
                "scope_id": str(faculty.id),
            },
        )
        assert created.status_code == 201
        assignment = created.json()
        assert assignment["role"] == {"key": "curriculum_office", "name": "Curriculum office"}

        at_scope = await api_client.get(
            "/api/v1/role-assignments",
            params={"scope_type": "faculty", "scope_id": str(faculty.id)},
        )
        assert [a["id"] for a in at_scope.json()] == [assignment["id"]]
        user_roles = await api_client.get(f"/api/v1/users/{target.id}/role-assignments")
        assert [a["id"] for a in user_roles.json()] == [assignment["id"]]

        removed = await api_client.delete(f"/api/v1/role-assignments/{assignment['id']}")
        assert removed.status_code == 204
        assert (await api_client.get(f"/api/v1/users/{target.id}/role-assignments")).json() == []

    @pytest.mark.parametrize(
        ("change", "status"),
        [
            ({"role_key": "no_such_role"}, 404),
            ({"user_id": "00000000-0000-0000-0000-000000000000"}, 404),
            ({"scope_type": "instance", "scope_id": None}, 422),  # wrong scope for the role
            ({"scope_id": "00000000-0000-0000-0000-000000000000"}, 422),  # no such faculty
            ({"scope_type": "module"}, 422),  # scope type not available yet
        ],
    )
    async def test_assignment_errors(
        self,
        api_client: AsyncClient,
        admin: User,
        db_session: AsyncSession,
        test_settings: Settings,
        change: dict[str, object],
        status: int,
    ) -> None:
        target = await make_user(db_session, test_settings, "target@example.org")
        faculty, _ = await new_faculty(db_session)
        body: dict[str, object] = {
            "user_id": str(target.id),
            "role_key": "curriculum_office",
            "scope_type": "faculty",
            "scope_id": str(faculty.id),
            **change,
        }
        if body["role_key"] == "curriculum_office" and change.get("scope_type") == "instance":
            body["role_key"] = "programme_director"

        response = await api_client.post("/api/v1/role-assignments", json=body)

        assert response.status_code == status

    async def test_duplicate_assignment(self, api_client: AsyncClient, admin: User) -> None:
        body = {"user_id": str(admin.id), "role_key": "platform_admin", "scope_type": "instance"}

        assert (await api_client.post("/api/v1/role-assignments", json=body)).status_code == 409

    async def test_curriculum_office_staffs_own_faculty_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        tree: ScopeTree,
    ) -> None:
        faculty, faculty_scope = await new_faculty(db_session)
        other, _ = await new_faculty(db_session)
        await sign_in_as(
            api_client,
            db_session,
            test_settings,
            "office@example.org",
            "curriculum_office",
            faculty_scope,
        )
        target = await make_user(db_session, test_settings, "new.director@example.org")
        programme = tree.programme(faculty_scope)

        def body(scope_type: str, scope_id: object, role: str) -> dict[str, object]:
            return {
                "user_id": str(target.id),
                "role_key": role,
                "scope_type": scope_type,
                "scope_id": str(scope_id),
            }

        ok = await api_client.post(
            "/api/v1/role-assignments", json=body("programme", programme.id, "programme_director")
        )
        elsewhere = await api_client.post(
            "/api/v1/role-assignments", json=body("faculty", other.id, "curriculum_office")
        )
        escalate = await api_client.post(
            "/api/v1/role-assignments",
            json={
                "user_id": str(target.id),
                "role_key": "platform_admin",
                "scope_type": "instance",
            },
        )

        assert ok.status_code == 201
        assert elsewhere.status_code == 403
        assert escalate.status_code == 403

        own_scope = await api_client.get(
            "/api/v1/role-assignments", params={"scope_type": "faculty", "scope_id": faculty.id}
        )
        other_scope = await api_client.get(
            "/api/v1/role-assignments", params={"scope_type": "faculty", "scope_id": other.id}
        )
        assert own_scope.status_code == 200
        assert other_scope.status_code == 403

    async def test_cannot_remove_last_platform_admin(
        self, api_client: AsyncClient, admin: User
    ) -> None:
        (assignment,) = (await api_client.get("/api/v1/auth/me/roles")).json()

        response = await api_client.delete(f"/api/v1/role-assignments/{assignment['id']}")

        assert response.status_code == 409

    async def test_users_see_own_roles_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        other = await make_user(db_session, test_settings, "other@example.org")
        me = await sign_in_as(
            api_client, db_session, test_settings, "student@example.org", "student"
        )

        mine = await api_client.get("/api/v1/auth/me/roles")
        own = await api_client.get(f"/api/v1/users/{me.id}/role-assignments")
        theirs = await api_client.get(f"/api/v1/users/{other.id}/role-assignments")

        assert [a["role"]["key"] for a in mine.json()] == ["student"]
        assert own.status_code == 200
        assert theirs.status_code == 403

    async def test_unknown_assignment(self, api_client: AsyncClient, admin: User) -> None:
        response = await api_client.delete(
            "/api/v1/role-assignments/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 404
