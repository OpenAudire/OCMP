"""Tests for the "taught in many sessions" report settings and intentional repeats (ADR 053)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AuditLog, IntendedRepeat, Objective
from app.services import intended_repeats
from app.services.authorization import AuthorizationError, ConflictError, InvalidRequestError
from app.services.institution_settings import get_institution
from app.services.users import create_local_user
from tests.test_coverage_report import Library, accept
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture
from tests.test_reports_curriculum import session_with_objective, url

API = "/api/v1"


def rows_of(body: dict, start: str) -> list:  # type: ignore[type-arg]
    return next(s for s in body["sections"] if s["title"].startswith(start))["rows"]


async def teach_four_times(db: AsyncSession, world: World, library: Library) -> list[Objective]:
    made = []
    for index, name in enumerate(("cardio", "cardio", "anatomy", "anatomy")):
        objective = await session_with_objective(db, world, name, f"Session {index}", index)
        await accept(db, objective, library.one)
        made.append(objective)
    return made


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


@pytest.mark.usefixtures("admin")
class TestThreshold:
    async def test_the_report_is_labelled_taught_in_many_sessions(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        response = await api_client.get(
            url(world, "redundancy"), params={"framework_id": str(library.framework.id)}
        )

        assert response.json()["title"] == "Taught in many sessions"

    async def test_the_minimum_number_of_sessions_is_an_institution_setting(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await teach_four_times(db_session, world, library)
        institution = await get_institution(db_session)
        assert institution is not None
        institution.settings = {**institution.settings, "coverage": {"repeat_min_sessions": 5}}
        await db_session.flush()

        body = (
            await api_client.get(
                url(world, "redundancy"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        assert rows_of(body, "Items taught") == []
        note = next(s for s in body["sections"] if s["title"].startswith("Items taught"))["note"]
        assert "at least 5.0 sessions" in note and "larger of 5" in note

    async def test_the_settings_are_validated(self) -> None:
        from app.services.policies import CoveragePolicy

        with pytest.raises(ValueError):
            CoveragePolicy.model_validate({"repeat_min_sessions": 1})
        with pytest.raises(ValueError):
            CoveragePolicy.model_validate({"repeat_spread": 9})


@pytest.mark.usefixtures("admin")
class TestIntentionalRepeats:
    async def test_marking_removes_the_item_from_the_list_and_shows_it_apart(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await teach_four_times(db_session, world, library)
        params = {"framework_id": str(library.framework.id)}
        before = (await api_client.get(url(world, "redundancy"), params=params)).json()
        assert [r[0] for r in rows_of(before, "Items taught")] == ["G1.1"]

        marked = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/intended-repeats",
            json={
                "framework_id": str(library.framework.id),
                "code": "G1.1",
                "reason": "Spiral curriculum: revisited each year.",
            },
        )

        assert marked.status_code == 201, marked.text
        assert marked.json()["can_edit"] is True
        after = (await api_client.get(url(world, "redundancy"), params=params)).json()
        assert rows_of(after, "Items taught") == []
        [row] = rows_of(after, "Marked as intentional")
        assert row[0] == "G1.1" and row[2] == 4 and row[3] == "Yes"
        assert row[4] == "Spiral curriculum: revisited each year."

    async def test_a_mark_is_audited_and_can_be_removed(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await teach_four_times(db_session, world, library)
        base = f"{API}/curriculum-versions/{world.draft.id}/intended-repeats"
        body = {"framework_id": str(library.framework.id), "code": "G1.1", "reason": "Spiral."}

        created = (await api_client.post(base, json=body)).json()
        [mark] = created["marks"]
        entries = list(
            await db_session.scalars(
                select(AuditLog).where(AuditLog.entity_id == uuid.UUID(mark["id"]))
            )
        )
        assert any(
            (e.context or {}).get("operation") == "reports.intended_repeat_mark" for e in entries
        )

        removed = await api_client.delete(f"{base}/{mark['id']}")

        assert removed.status_code == 200 and removed.json()["marks"] == []
        params = {"framework_id": str(library.framework.id)}
        again = (await api_client.get(url(world, "redundancy"), params=params)).json()
        assert [r[0] for r in rows_of(again, "Items taught")] == ["G1.1"]
        # The row is kept (soft delete) and the item can be marked again.
        assert (await api_client.post(base, json=body)).status_code == 201

    async def test_an_item_is_marked_once_and_must_exist(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        base = f"{API}/curriculum-versions/{world.draft.id}/intended-repeats"
        body = {"framework_id": str(library.framework.id), "code": "G1.1"}

        assert (await api_client.post(base, json=body)).status_code == 201
        assert (await api_client.post(base, json=body)).status_code == 409
        missing = {**body, "code": "NOPE"}
        assert (await api_client.post(base, json=missing)).status_code == 422
        assert (await api_client.delete(f"{base}/{world.draft.id}")).status_code == 422

    async def test_the_list_is_readable_and_a_version_that_cannot_be_seen_is_not_found(
        self, api_client: AsyncClient, world: World
    ) -> None:
        listed = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/intended-repeats"
        )
        assert listed.status_code == 200 and listed.json() == {"can_edit": True, "marks": []}
        missing = await api_client.get(
            f"{API}/curriculum-versions/{world.cardio.id}/intended-repeats"
        )
        assert missing.status_code == 404


class TestWhoMayMark:
    async def test_someone_without_curriculum_edit_may_not(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        user = await create_local_user(
            db_session,
            test_settings,
            email="reader@example.org",
            display_name="Reader",
            password="a-long-enough-password-1",
        )

        with pytest.raises(AuthorizationError):
            await intended_repeats.mark(
                db_session, user, world.programme.id, library.framework.id, "G1.1", ""
            )
        with pytest.raises(AuthorizationError):
            await intended_repeats.unmark(db_session, user, world.programme.id, world.draft.id)
        assert not await select_marks(db_session)

    async def test_a_reason_has_a_limit(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        from tests.authz_helpers import grant

        user = await create_local_user(
            db_session,
            test_settings,
            email="director@example.org",
            display_name="Director",
            password="a-long-enough-password-1",
        )
        await grant(db_session, user, "programme_director", intended_repeats_scope(world))

        with pytest.raises(InvalidRequestError):
            await intended_repeats.mark(
                db_session, user, world.programme.id, library.framework.id, "G1.1", "x" * 501
            )
        await intended_repeats.mark(
            db_session, user, world.programme.id, library.framework.id, "G1.1", " ok "
        )
        with pytest.raises(ConflictError):
            await intended_repeats.mark(
                db_session, user, world.programme.id, library.framework.id, "G1.1", ""
            )


def intended_repeats_scope(world: World):  # type: ignore[no-untyped-def]
    from app.core.permissions import ScopeType
    from app.services.authorization import ScopeRef

    return ScopeRef(ScopeType.PROGRAMME, world.programme.id)


async def select_marks(db: AsyncSession) -> list[IntendedRepeat]:
    return list(await db.scalars(select(IntendedRepeat)))
