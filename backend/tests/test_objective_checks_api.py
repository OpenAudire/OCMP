"""Tests for the objective quality checker API: live checks and the bulk check of a version."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import objective_checks
from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import Objective
from app.models.curriculum import ObjectiveStatus
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum import add_objective
from tests.test_curriculum_edit_api import MISSING, sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def finding_codes(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [f["code"] for f in body["findings"]]


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", f"/curriculum-versions/{MISSING}/outcome-checks"),
            ("POST", f"/modules/{MISSING}/outcome-checks"),
            ("POST", f"/learning-events/{MISSING}/objective-checks"),
            ("GET", f"/curriculum-versions/{MISSING}/objective-checks"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={"text": "x"})
        assert response.status_code == 401


class TestLiveCheck:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    async def test_flags_vague_wording_and_missing_domain(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcome-checks",
            json={"text": "Understand the heart."},
        )

        assert response.status_code == 200
        body = response.json()
        assert finding_codes(body) == ["vague_verb", "missing_domain"]
        first = body["findings"][0]
        assert first["severity"] == "warning"
        assert first["message_key"] == "curriculum.quality.vague_verb.message"
        assert first["suggestion_key"] == "curriculum.quality.vague_verb.suggestion"
        assert first["params"] == {"verbs": "understand"}
        assert body["detected_verb"] == "understand"

    async def test_suggests_levels_from_the_scales_verb_lists(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        world.remember.verbs = ["describe", "list"]
        world.apply.verbs = ["describe"]
        await db_session.flush()

        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcome-checks",
            json={"text": "Describe the heart.", "domain": "knowledge", "has_parent_links": True},
        )

        body = response.json()
        assert finding_codes(body) == []
        assert [(s["level_name"], s["scale_key"]) for s in body["suggestions"]] == [
            ("Remember", "bloom"),
            ("Apply", "bloom"),
        ]
        assert body["suggestions"][0]["taxonomy_level_id"] == str(world.remember.id)

    async def test_session_objective_without_links_is_flagged(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objective-checks",
            json={"text": "Perform the pulse check.", "domain": "skill", "has_parent_links": False},
        )

        assert finding_codes(response.json()) == ["missing_upward_link"]

    async def test_empty_text_is_checked_and_nothing_is_saved(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World
    ) -> None:
        before = await db_session.scalar(select(func.count()).select_from(Objective))

        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcome-checks", json={"text": ""}
        )

        assert response.status_code == 200
        assert finding_codes(response.json()) == ["missing_domain"]
        assert await db_session.scalar(select(func.count()).select_from(Objective)) == before

    async def test_text_over_the_limit_is_refused(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/outcome-checks",
            json={"text": "x" * 2001},
        )
        assert response.status_code == 422

    async def test_is_rate_limited_per_user(
        self, api_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(objective_checks, "LIVE_CHECKS_PER_MINUTE", 2)
        url = f"{API}/curriculum-versions/{world.draft.id}/outcome-checks"

        statuses = [(await api_client.post(url, json={"text": "Explain it."})).status_code]
        statuses += [(await api_client.post(url, json={"text": "Explain it."})).status_code]
        limited = await api_client.post(url, json={"text": "Explain it."})

        assert statuses == [200, 200]
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers


class TestLiveCheckPermissions:
    async def test_lecturer_checks_only_for_own_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id),
        )
        own = await api_client.post(
            f"{API}/learning-events/{world.lab.id}/objective-checks", json={"text": "Take it."}
        )
        other = await api_client.post(
            f"{API}/learning-events/{world.lecture.id}/objective-checks", json={"text": "x"}
        )
        outcome = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcome-checks", json={"text": "x"}
        )

        assert (own.status_code, other.status_code, outcome.status_code) == (200, 404, 404)

    async def test_student_cannot_check(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        response = await api_client.post(
            f"{API}/curriculum-versions/{world.published.id}/outcome-checks", json={"text": "x"}
        )

        assert response.status_code in (403, 404)


class TestVersionCheck:
    async def test_director_sees_every_live_objective_in_order(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        retired = await add_objective(db_session, world.cardio, "Retired outcome.")
        retired.status = ObjectiveStatus.RETIRED
        await db_session.flush()
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rules_language"] == "en"
        assert body["rules_version"] >= 1
        rows = body["objectives"]
        assert [r["text"] for r in rows] == [
            "Practise safely.",
            "Interpret cardiac investigations.",
            "Describe the cardiac cycle.",
            "Name the bones.",
        ]
        by_text = {r["text"]: r for r in rows}
        assert "Retired outcome." not in by_text
        assert "Published outcome." not in by_text
        assert rows[0]["level"] == "programme"
        cardio = by_text["Interpret cardiac investigations."]
        assert cardio["module_code"] == "HSC201"
        assert "missing_upward_link" in finding_codes(cardio)
        lecture = by_text["Describe the cardiac cycle."]
        assert lecture["event_title"] == "Cardiac cycle"
        assert "missing_upward_link" not in finding_codes(lecture)
        assert all(row["can_edit"] for row in rows)

    async def test_published_versions_are_checked_but_not_editable(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/objective-checks"
        )

        rows = response.json()["objectives"]
        assert [r["text"] for r in rows] == ["Published outcome."]
        assert rows[0]["can_edit"] is False

    async def test_lecturer_sees_only_the_objectives_of_their_session(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await add_objective(db_session, world.lab, "Understand the pulse.")
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id),
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        rows = response.json()["objectives"]
        assert [r["text"] for r in rows] == ["Understand the pulse."]
        assert rows[0]["can_edit"] is True
        assert "vague_verb" in finding_codes(rows[0])

    async def test_module_coordinator_sees_module_and_sessions_not_programme_outcomes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.cardio.id),
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        texts = {r["text"] for r in response.json()["objectives"]}
        assert texts == {"Interpret cardiac investigations.", "Describe the cardiac cycle."}

    async def test_people_without_edit_rights_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/objective-checks"
        )

        assert response.status_code == 403

    async def test_unknown_or_invisible_version_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, None)

        missing = await api_client.get(f"{API}/curriculum-versions/{MISSING}/objective-checks")
        hidden = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        assert (missing.status_code, hidden.status_code) == (404, 404)
