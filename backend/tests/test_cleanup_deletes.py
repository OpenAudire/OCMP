"""Deleting an unused framework and an account (ADR 037), and the seeded exit-level credits."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    AuditLog,
    Crosswalk,
    MappingLink,
    QualificationType,
    RoleAssignment,
)
from app.models.mapping import MappingSource
from app.services.curriculum import add_objective
from app.services.frameworks import add_item
from app.services.users import create_local_user
from tests.authz_helpers import grant
from tests.factories import FrameworkFactory, ModuleFactory
from tests.test_curriculum_edit_api import MISSING, sign_in

API = "/api/v1"


class TestDeleteFramework:
    async def test_an_unused_framework_is_hidden_and_audited(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        framework = FrameworkFactory()
        db_session.add(framework)
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.delete(f"{API}/frameworks/{framework.id}")

        assert response.status_code == 204
        await db_session.refresh(framework)
        assert framework.is_deleted
        logged = await db_session.scalars(
            select(AuditLog).where(AuditLog.context["operation"].astext == "framework.delete")
        )
        assert len(list(logged)) == 1
        assert (await api_client.delete(f"{API}/frameworks/{framework.id}")).status_code == 404

    async def test_a_mapped_framework_cannot_be_deleted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        framework = FrameworkFactory()
        module = ModuleFactory()
        db_session.add_all([framework, module])
        await db_session.flush()
        item = await add_item(db_session, framework, code="A", title="Area")
        objective = await add_objective(db_session, module, "Do something measurable.")
        db_session.add(
            MappingLink(
                objective_id=objective.id,
                framework_item_id=item.id,
                source=MappingSource.IMPORT,
                status="suggested",
            )
        )
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.delete(f"{API}/frameworks/{framework.id}")

        assert response.status_code == 409
        await db_session.refresh(framework)
        assert not framework.is_deleted

    async def test_an_older_version_with_a_newer_one_built_on_it_stays(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        older = FrameworkFactory(key="fw", version_label="1")
        newer = FrameworkFactory(key="fw", version_label="2")
        db_session.add_all([older, newer])
        await db_session.flush()
        db_session.add(Crosswalk(from_framework_id=older.id, to_framework_id=newer.id))
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        assert (await api_client.delete(f"{API}/frameworks/{older.id}")).status_code == 409
        # The newer one can go first, then the older.
        assert (await api_client.delete(f"{API}/frameworks/{newer.id}")).status_code == 204
        assert (await api_client.delete(f"{API}/frameworks/{older.id}")).status_code == 204

    async def test_needs_the_permission_and_a_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        assert (await api_client.delete(f"{API}/frameworks/{MISSING}")).status_code == 401
        framework = FrameworkFactory()
        db_session.add(framework)
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, None)
        assert (await api_client.delete(f"{API}/frameworks/{framework.id}")).status_code == 403


class TestDeleteUser:
    async def test_an_admin_deletes_an_account(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        target = await create_local_user(
            db_session,
            test_settings,
            email="temp@example.org",
            display_name="Temp Person",
            password="a-long-enough-password-1",
        )
        await grant(db_session, target, "curriculum_office")
        await sign_in(api_client, db_session, test_settings, "platform_admin")

        response = await api_client.delete(f"{API}/users/{target.id}")

        assert response.status_code == 204
        await db_session.refresh(target)
        assert target.is_deleted
        assert target.email != "temp@example.org"
        assert target.display_name == "Deleted user"
        assert target.password_hash is None
        left = await db_session.scalars(
            select(RoleAssignment).where(RoleAssignment.user_id == target.id)
        )
        assert list(left) == []
        assert (await api_client.delete(f"{API}/users/{target.id}")).status_code == 404
        # The address can be used for a new account.
        again = await api_client.post(
            f"{API}/users",
            json={
                "email": "temp@example.org",
                "display_name": "Temp Again",
                "password": "a-long-enough-password-1",
            },
        )
        assert again.status_code == 201

    async def test_not_yourself_and_not_without_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        admin = await sign_in(api_client, db_session, test_settings, "platform_admin")
        assert (await api_client.delete(f"{API}/users/{admin.id}")).status_code == 409
        assert (await api_client.delete(f"{API}/users/{MISSING}")).status_code == 404

        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (await api_client.delete(f"{API}/users/{admin.id}")).status_code == 403


class TestSeededExitLevelCredits:
    async def test_bachelors_types_carry_the_figures_and_where_they_come_from(
        self, db_session: AsyncSession
    ) -> None:
        rows = {row.key: row for row in await db_session.scalars(select(QualificationType))}
        assert rows["bachelors"].nqf_exit_level == 7
        assert rows["bachelors"].min_total_credits == 360
        assert rows["bachelors"].min_exit_level_credits == 120
        assert rows["bachelors_professional"].nqf_exit_level == 8
        assert rows["bachelors_professional"].min_total_credits == 480
        assert rows["bachelors_professional"].min_exit_level_credits == 120
        for key in ("bachelors", "bachelors_professional"):
            assert "Stellenbosch University" in rows[key].notes
            assert "verify" in rows[key].notes.lower()
        assert rows["honours"].min_exit_level_credits is None


class TestAuditOfMixedFlush:
    async def test_one_flush_with_a_create_an_update_and_a_delete_is_recorded(
        self, db_session: AsyncSession
    ) -> None:
        old = FrameworkFactory()
        gone = FrameworkFactory()
        db_session.add_all([old, gone])
        await db_session.flush()

        old.name = "Renamed"
        await db_session.delete(gone)
        db_session.add(FrameworkFactory())
        await db_session.flush()

        actions = {
            row.action
            for row in await db_session.scalars(
                select(AuditLog).where(AuditLog.entity_type == "frameworks")
            )
        }
        assert {"create", "update", "delete"} <= actions
