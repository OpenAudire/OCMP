"""Tests for the audit log: automatic capture, privacy, immutability, retention and API."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import AIRun, AuditLog, Framework, Programme, User
from app.models.audit import ActorType
from app.models.framework import FrameworkStatus
from app.models.mapping import AIRunType, MappingSource, ReviewDecision
from app.services.audit import (
    actor_scope,
    current_actor,
    entity_history,
    purge_audit_log,
    record_event,
)
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective
from app.services.frameworks import activate_framework, add_item
from app.services.mapping import create_link, reopen_link, review_link
from app.services.users import create_local_user
from tests.authz_helpers import grant, new_user
from tests.factories import FrameworkFactory, ModuleFactory, ProgrammeFactory

pytestmark = pytest.mark.filterwarnings(
    "ignore:Object of type .* not in session:sqlalchemy.exc.SAWarning"
)


async def entries(db: AsyncSession, **filters: object) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.seq)
    for key, value in filters.items():
        query = query.where(getattr(AuditLog, key) == value)
    return list((await db.execute(query)).scalars())


class TestCapture:
    async def test_create_update_soft_delete_restore_delete(self, db_session: AsyncSession) -> None:
        actor = await new_user(db_session)
        with actor_scope(actor.id):
            programme = ProgrammeFactory(code="BHS", name="BSc Health Sciences (Demo)")
            db_session.add(programme)
            await db_session.flush()
            programme.name = "BSc Health Sciences"
            await db_session.flush()
            programme.soft_delete()
            await db_session.flush()
            programme.restore()
            await db_session.flush()
            await db_session.delete(programme)
            await db_session.flush()

        history = await entity_history(db_session, "programmes", programme.id)

        assert [e.action for e in history] == [
            "create",
            "update",
            "soft_delete",
            "restore",
            "delete",
        ]
        created, renamed, soft_deleted, _restored, deleted = history
        assert all(e.actor_type == ActorType.USER and e.actor_id == actor.id for e in history)
        assert created.after is not None
        assert created.after["code"] == "BHS"
        assert created.after["status"] == "planned"  # defaults are captured
        assert "updated_at" not in created.after
        assert (renamed.before, renamed.after) == (
            {"name": "BSc Health Sciences (Demo)"},
            {"name": "BSc Health Sciences"},
        )
        assert soft_deleted.before == {"deleted_at": None}
        assert deleted.before is not None
        assert deleted.before["name"] == "BSc Health Sciences"

    async def test_changes_without_an_actor_are_system_changes(
        self, db_session: AsyncSession
    ) -> None:
        programme = ProgrammeFactory()
        db_session.add(programme)
        await db_session.flush()

        (entry,) = await entity_history(db_session, "programmes", programme.id)
        assert (entry.actor_type, entry.actor_id) == (ActorType.SYSTEM, None)

    async def test_no_entry_when_nothing_really_changed(self, db_session: AsyncSession) -> None:
        programme = ProgrammeFactory(name="Same")
        db_session.add(programme)
        await db_session.flush()

        programme.name = "Same"
        await db_session.flush()

        assert len(await entity_history(db_session, "programmes", programme.id)) == 1

    async def test_rolled_back_changes_leave_no_entries(self, db_session: AsyncSession) -> None:
        async with db_session.begin_nested() as savepoint:
            programme = ProgrammeFactory()
            db_session.add(programme)
            await db_session.flush()
            programme_id = programme.id
            await savepoint.rollback()

        assert await entity_history(db_session, "programmes", programme_id) == []

    async def test_ai_run_logs_are_not_audited(self, db_session: AsyncSession) -> None:
        db_session.add(AIRun(type=AIRunType.QA, provider="p", model="m", prompt_version="v"))
        await db_session.flush()

        assert await entries(db_session, entity_type="ai_runs") == []

    async def test_framework_activation_is_audited(self, db_session: AsyncSession) -> None:
        old = FrameworkFactory(key="council", version_label="2019")
        new = FrameworkFactory(key="council", version_label="2025")
        db_session.add_all([old, new])
        await db_session.flush()
        await activate_framework(db_session, old)

        await activate_framework(db_session, new)

        superseded = [
            e
            for e in await entity_history(db_session, "frameworks", old.id)
            if e.action == "update"
        ]
        assert superseded[-1].after == {"status": FrameworkStatus.SUPERSEDED.value}


class TestPersonalData:
    async def test_user_personal_fields_are_never_logged(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        user = await create_local_user(
            db_session,
            test_settings,
            email="private.person@example.org",
            display_name="Private Person",
            password="a long enough passphrase",
        )
        user.display_name = "Renamed Person"
        user.email = "renamed.person@example.org"
        await db_session.flush()

        history = await entity_history(db_session, "users", user.id)

        assert [e.action for e in history] == ["create", "update"]
        everything = str([(e.before, e.after, e.context) for e in history])
        for secret in ("private.person", "Private Person", "Renamed", "argon2"):
            assert secret not in everything
        assert history[1].context["unrecorded_fields"] == ["display_name", "email"]

    async def test_password_change_is_recorded_without_the_hash(
        self, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        from app.services.users import change_password

        user = await create_local_user(
            db_session,
            test_settings,
            email="p@example.org",
            display_name="P",
            password="a long enough passphrase",
        )
        await change_password(
            db_session,
            test_settings,
            user,
            current_password="a long enough passphrase",
            new_password="another passphrase!",
        )

        last = (await entity_history(db_session, "users", user.id))[-1]
        assert last.context["unrecorded_fields"] == ["password_hash"]
        assert "argon2" not in str(last.before) + str(last.after)

    async def test_sign_in_time_is_not_audited(self, db_session: AsyncSession) -> None:
        user = await new_user(db_session)
        user.last_login_at = datetime.now(UTC)
        await db_session.flush()

        assert [e.action for e in await entity_history(db_session, "users", user.id)] == ["create"]

    async def test_view_events(self, db_session: AsyncSession) -> None:
        admin = await new_user(db_session)
        viewed = await new_user(db_session)
        with actor_scope(admin.id):
            await record_event(db_session, action="view", entity_type="users", entity_id=viewed.id)

        (entry,) = await entries(db_session, action="view")
        assert (entry.actor_id, entry.entity_id) == (admin.id, viewed.id)

    async def test_deleting_the_actor_anonymises_entries(self, db_session: AsyncSession) -> None:
        actor = await new_user(db_session)
        with actor_scope(actor.id):
            programme = ProgrammeFactory()
            db_session.add(programme)
            await db_session.flush()

        await db_session.execute(delete(User).where(User.id == actor.id))

        (entry,) = await entity_history(db_session, "programmes", programme.id)
        await db_session.refresh(entry)
        assert (entry.actor_type, entry.actor_id) == (ActorType.USER, None)


class TestOperations:
    @pytest.mark.usefixtures("system_roles")
    async def test_reopen_records_operation_reason_and_reviewer(
        self, db_session: AsyncSession
    ) -> None:
        module = ModuleFactory()
        framework = FrameworkFactory()
        db_session.add_all([module, framework])
        await db_session.flush()
        objective = await add_objective(db_session, module, "Explain the cardiac cycle.")
        item = await add_item(db_session, framework, code="K1", title="Knowledge")
        alice, carol = await new_user(db_session), await new_user(db_session)
        await grant(db_session, carol, "mapper", ScopeRef(ScopeType.MODULE, module.id))
        link = await create_link(db_session, objective, item, source=MappingSource.IMPORT)
        link.status = "suggested"  # make it reviewable
        link.accept_method = None
        await db_session.flush()
        await review_link(db_session, link, alice, ReviewDecision.REJECT)

        await reopen_link(db_session, carol, link, reason="Rejected by mistake")

        reopened = (await entity_history(db_session, "mapping_links", link.id))[-1]
        assert reopened.context == {"operation": "mapping.reopen", "reason": "Rejected by mistake"}
        assert reopened.actor_id == carol.id
        assert reopened.after is not None
        assert reopened.after["status"] == "suggested"
        assert current_actor() is None  # the explicit actor does not leak


class TestImmutability:
    async def make_entry(self, db: AsyncSession) -> AuditLog:
        programme = ProgrammeFactory()
        db.add(programme)
        await db.flush()
        (entry,) = await entity_history(db, "programmes", programme.id)
        return entry

    async def test_entries_cannot_be_changed(self, db_session: AsyncSession) -> None:
        entry = await self.make_entry(db_session)

        with pytest.raises(DBAPIError, match="cannot be changed"):
            async with db_session.begin_nested():
                await db_session.execute(
                    update(AuditLog).where(AuditLog.id == entry.id).values(action="tampered")
                )

    async def test_entries_cannot_be_deleted(self, db_session: AsyncSession) -> None:
        await self.make_entry(db_session)

        with pytest.raises(DBAPIError, match="cannot be deleted"):
            async with db_session.begin_nested():
                await db_session.execute(delete(AuditLog))

    async def test_retention_purge(self, db_session: AsyncSession) -> None:
        old = await self.make_entry(db_session)
        recent = await self.make_entry(db_session)
        # Backdate one entry the only way the guard allows: inside a purge-flagged
        # transaction, re-inserting it with an old timestamp.
        await db_session.execute(text("SET LOCAL ocmp.allow_audit_purge = 'on'"))
        snapshot = {
            c: getattr(old, c)
            for c in (
                "actor_type",
                "entity_type",
                "entity_id",
                "action",
                "before",
                "after",
                "context",
            )
        }
        await db_session.execute(delete(AuditLog).where(AuditLog.id == old.id))
        db_session.expunge(old)
        db_session.add(
            AuditLog(id=old.id, occurred_at=datetime.now(UTC) - timedelta(days=400), **snapshot)
        )
        await db_session.flush()

        assert await purge_audit_log(db_session, older_than_days=0) == 0
        assert await purge_audit_log(db_session, older_than_days=365) == 1
        remaining = {e.id for e in await entries(db_session)}
        assert old.id not in remaining
        assert recent.id in remaining


@pytest.mark.usefixtures("system_roles")
class TestAPI:
    async def sign_in(
        self,
        client: AsyncClient,
        db: AsyncSession,
        settings: Settings,
        email: str,
        role: str | None,
    ) -> User:
        user = await create_local_user(
            db, settings, email=email, display_name="Admin", password="a long enough passphrase"
        )
        if role:
            await grant(db, user, role)
        client.cookies.clear()
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "a long enough passphrase"}
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies["ocmp_csrf"]
        return user

    async def test_changes_through_the_api_record_the_signed_in_user(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        admin = await self.sign_in(
            api_client, db_session, test_settings, "admin@example.org", "platform_admin"
        )

        created = await api_client.post(
            "/api/v1/users",
            json={
                "email": "new.person@example.org",
                "display_name": "New Person",
                "password": "a long enough passphrase",
            },
        )

        (entry,) = await entries(
            db_session,
            entity_type="users",
            action="create",
            entity_id=__import__("uuid").UUID(created.json()["id"]),
        )
        assert entry.actor_id == admin.id
        assert "new.person" not in str(entry.after)
        assert current_actor() is None  # the request's actor does not leak

    async def test_admin_views_of_users_are_recorded(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        admin = await self.sign_in(
            api_client, db_session, test_settings, "admin@example.org", "platform_admin"
        )

        await api_client.get("/api/v1/users", params={"search": "admin@"})
        await api_client.get(f"/api/v1/users/{admin.id}")

        list_view, detail_view = await entries(db_session, action="view")
        assert list_view.entity_id is None
        assert list_view.context == {"user_ids": [str(admin.id)], "searched": True}
        assert "admin@" not in str(list_view.context)  # the search text is not stored
        assert (detail_view.entity_id, detail_view.actor_id) == (admin.id, admin.id)

    async def test_reading_the_log_needs_audit_permission(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        await self.sign_in(
            api_client, db_session, test_settings, "office@example.org", "curriculum_office"
        )

        assert (await api_client.get("/api/v1/audit-log")).status_code == 403

    async def test_filters_and_pagination(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        await self.sign_in(
            api_client, db_session, test_settings, "admin@example.org", "platform_admin"
        )
        programmes = [ProgrammeFactory() for _ in range(3)]
        db_session.add_all(programmes)
        await db_session.flush()
        programmes[0].name = "Changed"
        await db_session.flush()

        page = (
            await api_client.get(
                "/api/v1/audit-log", params={"entity_type": "programmes", "limit": 2}
            )
        ).json()
        one = (
            await api_client.get(
                "/api/v1/audit-log",
                params={
                    "entity_type": "programmes",
                    "entity_id": str(programmes[0].id),
                    "action": "update",
                },
            )
        ).json()

        assert page["total"] == 4
        assert len(page["items"]) == 2
        assert one["total"] == 1
        assert one["items"][0]["after"] == {"name": "Changed"}

    async def test_actor_and_time_filters(
        self, api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings
    ) -> None:
        admin = await self.sign_in(
            api_client, db_session, test_settings, "admin@example.org", "platform_admin"
        )
        other = await new_user(db_session)
        with actor_scope(other.id):
            db_session.add(ProgrammeFactory())
            await db_session.flush()

        def get(**params: str) -> dict[str, object]:
            return {"entity_type": "programmes", **params}

        by_other = (
            await api_client.get("/api/v1/audit-log", params=get(actor_id=str(other.id)))
        ).json()
        by_admin = (
            await api_client.get("/api/v1/audit-log", params=get(actor_id=str(admin.id)))
        ).json()
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        after_now = (await api_client.get("/api/v1/audit-log", params=get(since=future))).json()
        window = (
            await api_client.get("/api/v1/audit-log", params=get(since=past, until=future))
        ).json()

        assert (by_other["total"], by_admin["total"]) == (1, 0)
        assert after_now["total"] == 0
        assert window["total"] == 1


def test_programme_model_is_audited() -> None:
    from app.models.base import Audited

    assert issubclass(Programme, Audited)
    assert issubclass(Framework, Audited)
    assert not issubclass(AIRun, Audited)
