"""The review queue API: listing, deciding, four-eyes and bulk accept (ADR 040)."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import AIRun, AuditLog, FrameworkItem, MappingLink, Objective, User
from app.models.mapping import (
    AcceptMethod,
    AIRunType,
    DepthMatch,
    MappingSource,
    MappingStatus,
    ReviewDecision,
)
from app.services import mapping as mapping_service
from app.services import mapping_review
from app.services.authorization import INSTANCE, ConflictError, ScopeRef
from app.services.frameworks import add_item
from app.services.policies import MappingPolicy
from app.services.users import create_local_user
from tests.authz_helpers import grant
from tests.test_curriculum_edit_api import MISSING, PASSWORD, sign_in
from tests.test_mapping_workspace_api import (  # noqa: F401
    World,
    add,
    body,
    editor_role,
    module_scope,
    save,
    set_four_eyes,
    stored,
    world,
)

API = "/api/v1"
QUEUE = f"{API}/mapping/review-queue"


async def login(
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    email: str,
    role_key: str | None,
    scope: ScopeRef = INSTANCE,
) -> User:
    """Sign in as a (new) user with a role; the same email twice is the same person."""
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = await create_local_user(
            db, settings, email=email, display_name="Reviewer", password=PASSWORD
        )
        if role_key:
            await grant(db, user, role_key, scope)
    client.cookies.clear()
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["ocmp_csrf"]
    return user


def programme_scope(world: World) -> ScopeRef:  # noqa: F811
    return ScopeRef(ScopeType.PROGRAMME, world.programme.id)


async def ai_run(db: AsyncSession) -> AIRun:
    run = AIRun(type=AIRunType.MAPPING, provider="test", model="test", prompt_version="v1")
    await save(db, run)
    return run


async def suggest(
    db: AsyncSession,
    run: AIRun,
    objective: Objective,
    item: FrameworkItem,
    confidence: str = "0.930",
    **fields: Any,
) -> MappingLink:
    link = MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=MappingSource.AI,
        ai_run_id=run.id,
        confidence=Decimal(confidence),
        coverage=4,
        depth_match=DepthMatch.MATCHES,
        rationale="It is a direct example.",
        evidence_quote="Describe",
        **fields,
    )
    await save(db, link)
    return link


async def operations(db: AsyncSession) -> set[str]:
    return set(await db.scalars(select(AuditLog.context["operation"].as_string())))


async def review(
    client: AsyncClient,
    link: MappingLink,
    decision: str = "accept",
    expected: str = "suggested",
    **extra: Any,
) -> Any:
    return await client.post(
        f"{API}/mapping-links/{link.id}/review",
        json={"decision": decision, "expected_status": expected, **extra},
    )


@pytest.fixture
async def queue_world(db_session: AsyncSession, world: World) -> dict[str, MappingLink]:  # noqa: F811
    """AI suggestions in several places, one per scenario."""
    db = db_session
    run = await ai_run(db)
    group = await add_item(db, world.framework, code="G", title="Group")
    child = await add_item(db, world.framework, code="G.1", title="Child item", parent=group)
    return {
        "heart": await suggest(db, run, world.module_objective, world.item_a, "0.930"),
        "heart_b": await suggest(db, run, world.module_objective, child, "0.700"),
        "valves": await suggest(db, run, world.event_objective, world.item_b, "0.850"),
        "lungs": await suggest(db, run, world.other_objective, world.item_a, "0.910"),
        "outcome": await suggest(db, run, world.outcome, world.item_b, "0.990"),
        "published": await suggest(db, run, world.published_objective, world.item_a, "0.990"),
        "rejected": await suggest(
            db, run, world.published_objective, world.item_b, "0.990", status=MappingStatus.REJECTED
        ),
    }


class TestQueueReading:
    async def test_requires_sign_in(self, api_client: AsyncClient) -> None:
        assert (await api_client.get(QUEUE)).status_code == 401
        assert (await api_client.get(f"{QUEUE}/count")).status_code == 401

    async def test_a_module_reviewer_sees_only_their_module(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )

        data = (await api_client.get(QUEUE)).json()

        # Highest confidence first; the other module, the programme outcome, the published
        # version and the rejected link are not theirs to see.
        assert [item["id"] for item in data["items"]] == [
            str(queue_world[name].id) for name in ("heart", "valves", "heart_b")
        ]
        assert data["total"] == 3 and data["stage"] == "first"
        first = data["items"][0]
        assert first["confidence"] == 0.93 and first["source"] == "ai"
        assert first["rationale"] == "It is a direct example."
        assert first["evidence_quote"] == "Describe"
        assert first["objective"]["module_code"] == "HSC101"
        assert first["item"]["code"] == "A" and first["item"]["group"] is None
        assert data["items"][2]["item"]["group"] == "G Group"
        assert data["items"][1]["objective"]["learning_event_title"] == "Heart lecture"
        assert data["counts"] == {"first": 3, "second": 0, "recheck": 0, "total": 3}
        assert data["progress"]["waiting"] == 3 and data["four_eyes"] is False
        assert [m["code"] for m in data["facets"]["modules"]] == ["HSC101"]
        assert data["bulk_min_confidence"] == 0.8 and data["bulk_max_links"] == 200

    async def test_the_office_sees_every_draft_suggestion(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        data = (await api_client.get(QUEUE)).json()

        ids = {item["id"] for item in data["items"]}
        assert ids == {
            str(queue_world[n].id) for n in ("heart", "heart_b", "valves", "lungs", "outcome")
        }
        assert (await api_client.get(f"{QUEUE}/count")).json()["total"] == 5

    async def test_filters_sorting_and_paging(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        def ids(data: dict[str, Any]) -> list[str]:
            return [item["id"] for item in data["items"]]

        def link_ids(*names: str) -> list[str]:
            return [str(queue_world[n].id) for n in names]

        high = (await api_client.get(QUEUE, params={"min_confidence": "0.9"})).json()
        assert ids(high) == link_ids("outcome", "heart", "lungs")
        low = (await api_client.get(QUEUE, params={"max_confidence": "0.85"})).json()
        assert ids(low) == link_ids("heart_b")
        asc = (await api_client.get(QUEUE, params={"sort": "confidence_asc", "limit": 2})).json()
        assert ids(asc) == link_ids("heart_b", "valves")
        assert asc["total"] == 5
        second_page = (
            await api_client.get(QUEUE, params={"sort": "confidence_asc", "limit": 2, "offset": 2})
        ).json()
        assert ids(second_page) == link_ids("lungs", "heart")
        module = (
            await api_client.get(QUEUE, params={"module_id": str(world.other_module.id)})
        ).json()
        assert ids(module) == link_ids("lungs")
        # Progress and counts follow the scope, not the confidence filter.
        assert module["progress"]["total"] == 1 and module["counts"]["first"] == 1
        other_version = (
            await api_client.get(QUEUE, params={"version_id": str(world.published.id)})
        ).json()
        assert other_version["items"] == []
        bad = await api_client.get(QUEUE, params={"limit": 500})
        assert bad.status_code == 422

    async def test_without_a_review_permission_the_queue_is_empty(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "lecturer", module_scope(world.module))

        data = (await api_client.get(QUEUE)).json()

        assert data["items"] == [] and data["counts"]["total"] == 0
        assert (await api_client.get(f"{QUEUE}/count")).json()["total"] == 0

    async def test_progress_counts_the_decided_suggestions(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        reviewer = await sign_in(api_client, db_session, test_settings, "curriculum_office")
        queue_world["heart"].status = MappingStatus.ACCEPTED
        queue_world["heart"].accept_method = AcceptMethod.INDIVIDUAL
        queue_world["valves"].status = MappingStatus.REJECTED
        queue_world["lungs"].status = MappingStatus.NEEDS_SECOND_REVIEW
        queue_world["lungs"].first_reviewer_id = reviewer.id
        await db_session.flush()

        data = (await api_client.get(QUEUE)).json()

        assert data["progress"] == {
            "total": 5,
            "accepted": 1,
            "rejected": 1,
            "second_review": 1,
            "waiting": 2,
        }
        # Their own first review is not theirs to second.
        assert data["counts"] == {"first": 2, "second": 0, "recheck": 0, "total": 2}

    async def test_accepted_links_with_a_changed_objective_are_in_the_recheck_pile(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        heart = queue_world["heart"]
        heart.status = MappingStatus.ACCEPTED
        heart.accept_method = AcceptMethod.INDIVIDUAL
        heart.needs_recheck = True
        await db_session.flush()

        data = (await api_client.get(QUEUE, params={"stage": "recheck"})).json()

        assert [item["id"] for item in data["items"]] == [str(heart.id)]
        assert data["items"][0]["needs_recheck"] is True
        assert data["counts"]["recheck"] == 1
        # Confirming uses the existing action, and it leaves the pile.
        confirmed = await api_client.post(f"{API}/mapping-links/{heart.id}/recheck")
        assert confirmed.status_code == 200
        assert (await api_client.get(QUEUE, params={"stage": "recheck"})).json()["items"] == []


class TestDeciding:
    async def test_accept_is_recorded_and_audited(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        reviewer = await sign_in(api_client, db_session, test_settings, "curriculum_office")
        link = queue_world["heart"]

        response = await review(api_client, link)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"
        stored_link = await stored(db_session, str(link.id))
        assert stored_link.accept_method == AcceptMethod.INDIVIDUAL
        assert stored_link.first_reviewer_id == reviewer.id
        assert stored_link.first_decision == ReviewDecision.ACCEPT
        assert "mapping.review_first_accept" in await operations(db_session)

    async def test_edit_and_accept_changes_the_values(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        link = queue_world["heart"]

        response = await review(api_client, link, coverage=2, depth_match="below")

        assert response.status_code == 200
        stored_link = await stored(db_session, str(link.id))
        assert (stored_link.coverage, stored_link.depth_match) == (2, DepthMatch.BELOW)
        assert stored_link.status == MappingStatus.ACCEPTED
        assert "mapping.review_first_accept_edited" in await operations(db_session)

    async def test_reject_and_send_to_second_review(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        rejected = await review(api_client, queue_world["heart"], "reject")
        sent = await review(api_client, queue_world["valves"], "second_review")

        assert rejected.json()["status"] == "rejected"
        assert sent.json()["status"] == "needs_second_review"
        ops = await operations(db_session)
        assert {"mapping.review_reject", "mapping.review_send_second"} <= ops

    async def test_a_link_that_moved_on_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        link = queue_world["heart"]
        link.status = MappingStatus.NEEDS_SECOND_REVIEW
        await db_session.flush()

        # The person still saw it as a first-stage suggestion: never a second review by accident.
        response = await review(api_client, link)

        assert response.status_code == 409
        assert (await stored(db_session, str(link.id))).status == MappingStatus.NEEDS_SECOND_REVIEW

    async def test_a_decided_link_cannot_be_decided_again(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (await review(api_client, queue_world["heart"])).status_code == 200
        again = await review(api_client, queue_world["heart"], "reject", expected="accepted")
        assert again.status_code == 409

    @pytest.mark.parametrize(
        "extra", [{"coverage": 3}, {"depth_match": "above"}], ids=["coverage", "depth"]
    )
    async def test_corrections_only_come_with_an_accept(
        self,
        extra: dict[str, Any],
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await review(api_client, queue_world["heart"], "reject", **extra)
        assert response.status_code == 422

    async def test_accepting_needs_a_coverage_and_a_depth(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        link = queue_world["heart"]
        link.coverage = None
        await db_session.flush()

        assert (await review(api_client, link)).status_code == 422
        assert (await review(api_client, link, coverage=3)).status_code == 200

    @pytest.mark.parametrize(
        "change", [{"coverage": 6}, {"decision": "maybe"}, {"expected_status": "x"}]
    )
    async def test_invalid_requests_are_refused(
        self,
        change: dict[str, Any],
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        payload = {"decision": "accept", "expected_status": "suggested"} | change
        response = await api_client.post(
            f"{API}/mapping-links/{queue_world['heart'].id}/review", json=payload
        )
        assert response.status_code == 422

    async def test_permissions_follow_the_objectives_scope(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )
        # Another module, the programme outcome and an unknown link are not visible: 404.
        for name in ("lungs", "outcome"):
            assert (await review(api_client, queue_world[name])).status_code == 404
        missing = await api_client.post(
            f"{API}/mapping-links/{MISSING}/review",
            json={"decision": "accept", "expected_status": "suggested"},
        )
        assert missing.status_code == 404
        # A rejected link is hidden like a missing one.
        assert (await review(api_client, queue_world["rejected"])).status_code == 404
        assert (await review(api_client, queue_world["heart"])).status_code == 200

    async def test_seeing_is_not_reviewing(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "lecturer", module_scope(world.module))
        assert (await review(api_client, queue_world["heart"])).status_code == 403

    async def test_a_published_version_cannot_be_reviewed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (await review(api_client, queue_world["published"])).status_code == 409

    async def test_a_suggestion_by_an_editor_reaches_the_reviewer(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await editor_role(db_session)
        writer = await login(
            api_client,
            db_session,
            test_settings,
            "writer@example.org",
            "mapping_only",
            module_scope(world.module),
        )
        made = await add(api_client, world.module_objective, **body(world.item_a, 2, "below"))
        assert made.json()["status"] == "suggested"
        # The editor cannot review: their own queue is empty.
        assert (await api_client.get(QUEUE)).json()["items"] == []

        await login(
            api_client,
            db_session,
            test_settings,
            "boss@example.org",
            "module_coordinator",
            module_scope(world.module),
        )
        data = (await api_client.get(QUEUE)).json()
        [card] = data["items"]
        assert card["source"] == "human" and card["confidence"] is None
        assert card["evidence_quote"] == "" and card["coverage"] == 2

        response = await api_client.post(
            f"{API}/mapping-links/{card['id']}/review",
            json={"decision": "accept", "expected_status": "suggested"},
        )
        assert response.status_code == 200
        link = await stored(db_session, card["id"])
        assert link.created_by_id == writer.id and link.first_reviewer_id != writer.id


class TestFourEyes:
    async def test_two_different_reviewers_are_needed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await set_four_eyes(db_session, world)
        link = queue_world["heart"]
        first = await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )

        accepted = await review(api_client, link)
        assert accepted.json()["status"] == "needs_second_review"
        mine = (await api_client.get(QUEUE, params={"stage": "second"})).json()
        # The first reviewer's own work is not theirs to second, and does not count as waiting.
        assert mine["items"] == [] and mine["counts"]["second"] == 0
        assert mine["progress"]["second_review"] == 1
        again = await review(api_client, link, expected="needs_second_review")
        assert again.status_code == 409

        await login(
            api_client,
            db_session,
            test_settings,
            "m2@example.org",
            "mapper",
            programme_scope(world),
        )
        theirs = (await api_client.get(QUEUE, params={"stage": "second"})).json()
        [card] = theirs["items"]
        assert card["id"] == str(link.id) and card["first_decision"] == "accept"
        assert (await api_client.get(f"{QUEUE}/count")).json()["second"] == 1
        done = await review(api_client, link, expected="needs_second_review")

        assert done.json() == {"id": str(link.id), "status": "accepted", "needs_discussion": False}
        stored_link = await stored(db_session, str(link.id))
        assert stored_link.first_reviewer_id == first.id
        assert stored_link.second_reviewer_id != first.id
        assert stored_link.accept_method == AcceptMethod.INDIVIDUAL
        assert "mapping.review_second_accept" in await operations(db_session)

    async def test_overturning_the_first_review_is_flagged_for_discussion(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await set_four_eyes(db_session, world)
        link = queue_world["heart"]
        await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )
        await review(api_client, link)
        await login(
            api_client,
            db_session,
            test_settings,
            "m2@example.org",
            "mapper",
            programme_scope(world),
        )

        response = await review(api_client, link, "reject", expected="needs_second_review")

        assert response.json()["status"] == "rejected"
        assert response.json()["needs_discussion"] is True

    async def test_a_second_review_needs_the_second_review_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await set_four_eyes(db_session, world)
        link = queue_world["heart"]
        await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )
        await review(api_client, link)

        # A module coordinator reviews first, but holds no second-review permission.
        await login(
            api_client,
            db_session,
            test_settings,
            "c1@example.org",
            "module_coordinator",
            module_scope(world.module),
        )
        assert (await api_client.get(QUEUE, params={"stage": "second"})).json()["items"] == []
        forbidden = await review(api_client, link, expected="needs_second_review")
        assert forbidden.status_code == 403

    async def test_the_author_of_a_link_counts_as_its_first_reviewer(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await set_four_eyes(db_session, world)
        await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )
        made = await add(api_client, world.module_objective, **body(world.item_a))
        assert made.json()["status"] == "needs_second_review"
        link_id = made.json()["id"]

        # Not theirs to second, in the queue or through the API.
        assert (await api_client.get(QUEUE, params={"stage": "second"})).json()["items"] == []
        own = await api_client.post(
            f"{API}/mapping-links/{link_id}/review",
            json={"decision": "accept", "expected_status": "needs_second_review"},
        )
        assert own.status_code == 409

        await login(
            api_client,
            db_session,
            test_settings,
            "m2@example.org",
            "mapper",
            programme_scope(world),
        )
        [card] = (await api_client.get(QUEUE, params={"stage": "second"})).json()["items"]
        assert card["id"] == link_id
        other = await api_client.post(
            f"{API}/mapping-links/{link_id}/review",
            json={"decision": "accept", "expected_status": "needs_second_review"},
        )
        assert other.json()["status"] == "accepted"

    async def test_the_author_of_a_suggestion_cannot_give_the_second_review(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        """Even when someone else gave the first review (service level)."""
        await set_four_eyes(db_session, world)
        author = await create_local_user(
            db_session,
            test_settings,
            email="author@example.org",
            display_name="A",
            password=PASSWORD,
        )
        first = await create_local_user(
            db_session,
            test_settings,
            email="first@example.org",
            display_name="F",
            password=PASSWORD,
        )
        link = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.HUMAN,
            created_by_id=author.id,
            coverage=3,
            depth_match=DepthMatch.MATCHES,
        )
        await save(db_session, link)
        policy = MappingPolicy(four_eyes=True)
        await mapping_service.review_link(
            db_session, link, first, ReviewDecision.ACCEPT, policy=policy
        )
        assert link.status == MappingStatus.NEEDS_SECOND_REVIEW

        with pytest.raises(ConflictError):
            await mapping_service.review_link(
                db_session, link, author, ReviewDecision.ACCEPT, policy=policy
            )

    async def test_unsure_goes_to_a_second_review_without_four_eyes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        link = queue_world["heart"]
        await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )
        sent = await review(api_client, link, "second_review")
        assert sent.json()["status"] == "needs_second_review"
        await login(
            api_client,
            db_session,
            test_settings,
            "m2@example.org",
            "mapper",
            programme_scope(world),
        )
        done = await review(api_client, link, "accept", expected="needs_second_review")
        assert done.json()["status"] == "accepted"
        # "Unsure" is not a decision to overturn.
        assert done.json()["needs_discussion"] is False


class TestBulkAccept:
    async def bulk(self, client: AsyncClient, **payload: Any) -> Any:
        return await client.post(f"{QUEUE}/bulk-accept", json={"min_confidence": "0.9"} | payload)

    async def test_only_confident_suggestions_in_reach_are_accepted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        preview = await self.bulk(api_client, dry_run=True)
        assert preview.json() == {
            "eligible": 3,
            "processed": 0,
            "remaining": 3,
            "status_after": "accepted",
            "dry_run": True,
        }
        assert (await stored(db_session, str(queue_world["heart"].id))).status == (
            MappingStatus.SUGGESTED
        )

        done = await self.bulk(api_client)

        assert done.json()["processed"] == 3 and done.json()["remaining"] == 0
        for name in ("heart", "lungs", "outcome"):
            link = await stored(db_session, str(queue_world[name].id))
            assert (link.status, link.accept_method) == (MappingStatus.ACCEPTED, AcceptMethod.BULK)
        for name in ("heart_b", "valves"):
            assert (await stored(db_session, str(queue_world[name].id))).status == (
                MappingStatus.SUGGESTED
            )
        # The published version is never touched.
        assert (await stored(db_session, str(queue_world["published"].id))).status == (
            MappingStatus.SUGGESTED
        )
        assert "mapping.review_bulk_accept" in await operations(db_session)

    async def test_it_stays_within_the_users_scope_and_filters(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )
        done = await self.bulk(api_client)
        assert done.json()["processed"] == 1  # only "heart"; "lungs" is another module
        assert (await stored(db_session, str(queue_world["lungs"].id))).status == (
            MappingStatus.SUGGESTED
        )

        await login(
            api_client, db_session, test_settings, "office@example.org", "curriculum_office"
        )
        scoped = await self.bulk(api_client, module_id=str(world.other_module.id), dry_run=True)
        assert scoped.json()["eligible"] == 1

    async def test_the_threshold_has_a_floor(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        refused = await self.bulk(api_client, min_confidence="0.5")
        assert refused.status_code == 422
        too_high = await self.bulk(api_client, min_confidence="1.5")
        assert too_high.status_code == 422
        assert (await self.bulk(api_client, min_confidence="0.8", dry_run=True)).json()[
            "eligible"
        ] == 4

    async def test_one_batch_is_capped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        queue_world: dict[str, MappingLink],
    ) -> None:
        monkeypatch.setattr(mapping_review, "BULK_MAX_LINKS", 2)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        done = (await self.bulk(api_client)).json()

        assert (done["eligible"], done["processed"], done["remaining"]) == (3, 2, 1)
        # The most confident go first.
        assert (await stored(db_session, str(queue_world["outcome"].id))).status == (
            MappingStatus.ACCEPTED
        )
        assert (await stored(db_session, str(queue_world["lungs"].id))).status == (
            MappingStatus.SUGGESTED
        )

    async def test_in_four_eyes_mode_it_is_only_a_first_review(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await set_four_eyes(db_session, world)
        first = await login(
            api_client,
            db_session,
            test_settings,
            "m1@example.org",
            "mapper",
            programme_scope(world),
        )

        done = (await self.bulk(api_client)).json()

        assert done["status_after"] == "needs_second_review" and done["processed"] == 3
        link = await stored(db_session, str(queue_world["heart"].id))
        assert link.status == MappingStatus.NEEDS_SECOND_REVIEW
        assert link.first_reviewer_id == first.id and link.accept_method is None
        # A second bulk accept by the same person finds nothing to accept, and never reaches
        # the second stage, whoever asks.
        again = (await self.bulk(api_client)).json()
        assert again["eligible"] == 0
        await login(
            api_client,
            db_session,
            test_settings,
            "m2@example.org",
            "mapper",
            programme_scope(world),
        )
        other = (await self.bulk(api_client)).json()
        assert other["eligible"] == 0
        assert (await stored(db_session, str(queue_world["heart"].id))).status == (
            MappingStatus.NEEDS_SECOND_REVIEW
        )

    async def test_people_made_suggestions_are_left_alone(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await editor_role(db_session)
        await login(
            api_client,
            db_session,
            test_settings,
            "writer@example.org",
            "mapping_only",
            module_scope(world.module),
        )
        await add(api_client, world.module_objective, **body(world.item_a))
        await login(
            api_client,
            db_session,
            test_settings,
            "boss@example.org",
            "module_coordinator",
            module_scope(world.module),
        )
        # No confidence, so bulk accept never takes it: a person decides these one by one.
        assert (await self.bulk(api_client, dry_run=True)).json()["eligible"] == 0

    async def test_without_a_review_permission_nothing_happens(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
        queue_world: dict[str, MappingLink],
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "lecturer", module_scope(world.module))
        assert (await self.bulk(api_client)).json()["processed"] == 0
