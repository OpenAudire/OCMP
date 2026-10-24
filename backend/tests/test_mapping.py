"""Tests for mapping links, their review workflow, AI runs and review assignments."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ScopeType
from app.models import (
    AIRun,
    AIRunCall,
    FrameworkItem,
    MappingLink,
    Objective,
    ReviewAssignment,
    User,
)
from app.models.mapping import (
    AcceptMethod,
    AIRunStatus,
    AIRunType,
    DepthMatch,
    MappingSource,
    MappingStatus,
    ReviewDecision,
)
from app.services.ai_runs import purge_ai_call_content
from app.services.authorization import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    ScopeRef,
)
from app.services.curriculum import add_objective
from app.services.curriculum_scopes import objective_scope
from app.services.frameworks import add_item
from app.services.mapping import (
    bulk_accept,
    create_link,
    links_for_objective,
    reopen_link,
    review_link,
)
from app.services.policies import MappingPolicy, mapping_policy_for, parse_mapping_policy
from tests.authz_helpers import grant, new_user
from tests.factories import FrameworkFactory, LearningEventFactory

pytestmark = pytest.mark.filterwarnings(
    "ignore:Object of type .* not in session:sqlalchemy.exc.SAWarning"
)

FOUR_EYES = MappingPolicy(four_eyes=True)
OBJECTIVE_TEXT = "Take a focused history from a patient with chest pain."


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


async def must_fail(db: AsyncSession, *objects: object) -> None:
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add_all(objects)
            await db.flush()


class World:
    """An objective, a framework with items, an AI run and three people."""

    def __init__(
        self,
        objective: Objective,
        items: list[FrameworkItem],
        run: AIRun,
        people: list[User],
    ) -> None:
        self.objective = objective
        self.items = items
        self.run = run
        self.alice, self.bob, self.carol = people


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    event = LearningEventFactory()
    framework = FrameworkFactory()
    run = AIRun(type=AIRunType.MAPPING, provider="null", model="test-model", prompt_version="v1")
    await save(db_session, event, framework, run)
    objective = await add_objective(db_session, event.module, OBJECTIVE_TEXT)
    items = [
        await add_item(db_session, framework, code=f"C{n}", title=f"Competency {n}")
        for n in range(4)
    ]
    people = [await new_user(db_session) for _ in range(3)]
    return World(objective, items, run, people)


async def grant_mapper(db: AsyncSession, w: World, user: User) -> None:
    assert w.objective.module_id is not None
    await grant(db, user, "mapper", ScopeRef(ScopeType.MODULE, w.objective.module_id))


async def suggestion(db: AsyncSession, w: World, item: int = 0, **kwargs: object) -> MappingLink:
    values: dict[str, object] = {
        "source": MappingSource.AI,
        "ai_run": w.run,
        "coverage": 3,
        "depth_match": DepthMatch.MATCHES,
        "confidence": 0.8,
        "rationale": "The objective asks for history taking.",
        "evidence_quote": "focused history",
        **kwargs,
    }
    return await create_link(db, w.objective, w.items[item], **values)  # type: ignore[arg-type]


class TestAIRuns:
    async def test_defaults_and_calls(self, db_session: AsyncSession, world: World) -> None:
        call = AIRunCall(
            run_id=world.run.id,
            request={"messages": [{"role": "user", "content": "Map this objective"}]},
            response='{"candidates": []}',
            input_tokens=120,
            output_tokens=40,
            duration_ms=850,
            valid=True,
        )
        await save(db_session, call)

        assert world.run.status == AIRunStatus.QUEUED
        assert world.run.estimated_cost == 0
        assert world.run.parameters == {}
        assert call.content_purged_at is None

    @pytest.mark.parametrize(
        "values",
        [
            {"input_tokens": -1},
            {"estimated_cost": Decimal("-0.01")},
            {
                "started_at": datetime.now(UTC),
                "finished_at": datetime.now(UTC) - timedelta(minutes=1),
            },
        ],
        ids=["negative-tokens", "negative-cost", "finished-before-start"],
    )
    async def test_value_checks(self, db_session: AsyncSession, values: dict[str, object]) -> None:
        await must_fail(
            db_session,
            AIRun(type=AIRunType.QA, provider="p", model="m", prompt_version="v", **values),
        )

    @pytest.mark.parametrize("table", [AIRun, AIRunCall])
    async def test_runs_and_calls_can_never_be_deleted(
        self, db_session: AsyncSession, world: World, table: type[AIRun] | type[AIRunCall]
    ) -> None:
        await save(db_session, AIRunCall(run_id=world.run.id, request={"messages": []}))

        with pytest.raises(DBAPIError, match="permanent"):
            async with db_session.begin_nested():
                await db_session.execute(delete(table))

    async def test_ai_link_must_reference_its_run(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await must_fail(
            db_session,
            MappingLink(
                objective_id=world.objective.id,
                framework_item_id=world.items[0].id,
                source=MappingSource.AI,
                status="suggested",
            ),
        )


class TestRetention:
    async def make_call(self, db: AsyncSession, w: World, age_days: int) -> AIRunCall:
        call = AIRunCall(
            run_id=w.run.id,
            request={"messages": [{"role": "user", "content": OBJECTIVE_TEXT}]},
            response='{"is_match": true}',
            input_tokens=100,
            output_tokens=20,
            duration_ms=500,
            valid=True,
            error_message="retried once",
        )
        await save(db, call)
        call.created_at = datetime.now(UTC) - timedelta(days=age_days)
        await db.flush()
        return call

    async def test_clears_old_content_and_keeps_the_record(
        self, db_session: AsyncSession, world: World
    ) -> None:
        old = await self.make_call(db_session, world, age_days=400)
        recent = await self.make_call(db_session, world, age_days=10)
        link = await suggestion(db_session, world)

        purged = await purge_ai_call_content(db_session, older_than_days=365)

        assert purged == 1
        await db_session.refresh(old)
        await db_session.refresh(recent)
        assert (old.request, old.response, old.error_message) == ({}, None, None)
        assert old.content_purged_at is not None
        # Counts, timing and validity stay for cost reports and audit.
        assert (old.input_tokens, old.output_tokens, old.duration_ms, old.valid) == (
            100,
            20,
            500,
            True,
        )
        assert recent.response == '{"is_match": true}'
        await db_session.refresh(link)
        assert link.ai_run_id == world.run.id
        assert await db_session.get(AIRun, world.run.id) is not None

    async def test_is_idempotent_and_can_be_disabled(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await self.make_call(db_session, world, age_days=400)

        assert await purge_ai_call_content(db_session, older_than_days=0) == 0
        assert await purge_ai_call_content(db_session, older_than_days=30) == 1
        assert await purge_ai_call_content(db_session, older_than_days=30) == 0


class TestCreateLink:
    async def test_starting_status_by_source(self, db_session: AsyncSession, world: World) -> None:
        ai = await suggestion(db_session, world, 0)
        human = await create_link(
            db_session,
            world.objective,
            world.items[1],
            source=MappingSource.HUMAN,
            creator=world.alice,
            coverage=4,
        )
        imported = await create_link(
            db_session, world.objective, world.items[2], source=MappingSource.IMPORT
        )
        migrated = await create_link(
            db_session,
            world.objective,
            world.items[3],
            source=MappingSource.MIGRATED,
            migrated_from=imported,
        )

        assert (ai.status, ai.accept_method) == (MappingStatus.SUGGESTED, None)
        assert (human.status, human.accept_method, human.first_reviewer_id) == (
            MappingStatus.ACCEPTED,
            AcceptMethod.INDIVIDUAL,
            world.alice.id,
        )
        assert imported.accept_method == AcceptMethod.IMPORTED
        assert (migrated.status, migrated.migrated_from_id) == (
            MappingStatus.SUGGESTED,
            imported.id,
        )

    async def test_hand_made_link_in_four_eyes_mode(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await create_link(
            db_session,
            world.objective,
            world.items[0],
            source=MappingSource.HUMAN,
            creator=world.alice,
            policy=FOUR_EYES,
        )

        assert link.status == MappingStatus.NEEDS_SECOND_REVIEW
        with pytest.raises(ConflictError, match="someone else"):
            await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT)

    async def test_one_link_per_objective_and_item(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await suggestion(db_session, world)

        with pytest.raises(ConflictError):
            await suggestion(db_session, world)

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"coverage": 6}, "Coverage"),
            ({"confidence": 1.2}, "Confidence"),
            ({"ai_run": None}, "AI run"),
            ({"evidence_quote": "words the objective never used"}, "words from the objective"),
            ({"source": MappingSource.HUMAN, "ai_run": None}, "author"),
            ({"source": MappingSource.MIGRATED, "ai_run": None}, "link they replace"),
        ],
    )
    async def test_validation(
        self, db_session: AsyncSession, world: World, kwargs: dict[str, object], message: str
    ) -> None:
        with pytest.raises(InvalidRequestError, match=message):
            await suggestion(db_session, world, **kwargs)

    async def test_quote_matching_ignores_case_and_spacing(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await suggestion(db_session, world, evidence_quote="FOCUSED   history from a patient")

    async def test_deleted_objective_or_framework(
        self, db_session: AsyncSession, world: World
    ) -> None:
        from app.models import Framework

        framework = await db_session.get(Framework, world.items[0].framework_id)
        assert framework is not None
        framework.soft_delete()
        with pytest.raises(InvalidRequestError, match="framework has been deleted"):
            await suggestion(db_session, world)

        world.objective.soft_delete()
        with pytest.raises(InvalidRequestError, match="deleted objective"):
            await suggestion(db_session, world)

    async def test_database_checks(self, db_session: AsyncSession, world: World) -> None:
        def raw(**kwargs: object) -> MappingLink:
            return MappingLink(
                objective_id=world.objective.id,
                framework_item_id=world.items[0].id,
                source=MappingSource.IMPORT,
                **kwargs,
            )

        await must_fail(db_session, raw(coverage=-1, status="suggested"))
        await must_fail(db_session, raw(confidence=Decimal("1.5"), status="suggested"))
        await must_fail(db_session, raw(status="accepted"))  # no accept method
        await must_fail(db_session, raw(status="suggested", accept_method="bulk"))
        await must_fail(
            db_session,
            raw(
                status="suggested",
                first_reviewer_id=world.alice.id,
                second_reviewer_id=world.alice.id,
            ),
        )


class TestReview:
    async def test_accept_with_corrections(self, db_session: AsyncSession, world: World) -> None:
        link = await suggestion(db_session, world)

        await review_link(
            db_session,
            link,
            world.alice,
            ReviewDecision.ACCEPT,
            coverage=2,
            depth_match=DepthMatch.BELOW,
        )

        assert (link.status, link.coverage, link.depth_match) == (
            MappingStatus.ACCEPTED,
            2,
            DepthMatch.BELOW,
        )
        assert link.first_reviewer_id == world.alice.id
        assert link.first_reviewed_at is not None

    async def test_reject_is_final_by_default_even_in_four_eyes(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world)

        await review_link(db_session, link, world.alice, ReviewDecision.REJECT, policy=FOUR_EYES)

        assert link.status == MappingStatus.REJECTED
        with pytest.raises(ConflictError, match="already been decided"):
            await review_link(db_session, link, world.bob, ReviewDecision.ACCEPT)

    async def test_policy_can_require_second_review_for_rejects(
        self, db_session: AsyncSession, world: World
    ) -> None:
        policy = MappingPolicy(second_review_for_rejects=True)
        confirmed = await suggestion(db_session, world, 0)
        overturned = await suggestion(db_session, world, 1)

        for link in (confirmed, overturned):
            await review_link(db_session, link, world.alice, ReviewDecision.REJECT, policy=policy)
            assert link.status == MappingStatus.NEEDS_SECOND_REVIEW

        await review_link(db_session, confirmed, world.bob, ReviewDecision.REJECT)
        await review_link(db_session, overturned, world.bob, ReviewDecision.ACCEPT)

        assert (confirmed.status, confirmed.needs_discussion) == (MappingStatus.REJECTED, False)
        assert (overturned.status, overturned.needs_discussion) == (MappingStatus.ACCEPTED, True)

    async def test_four_eyes_needs_two_people(self, db_session: AsyncSession, world: World) -> None:
        link = await suggestion(db_session, world)

        await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT, policy=FOUR_EYES)
        assert link.status == MappingStatus.NEEDS_SECOND_REVIEW

        with pytest.raises(ConflictError, match="someone else"):
            await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT)
        await review_link(db_session, link, world.bob, ReviewDecision.ACCEPT)

        assert (link.status, link.second_reviewer_id, link.needs_discussion) == (
            MappingStatus.ACCEPTED,
            world.bob.id,
            False,
        )

    async def test_disagreement_is_flagged(self, db_session: AsyncSession, world: World) -> None:
        link = await suggestion(db_session, world)
        await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT, policy=FOUR_EYES)

        await review_link(db_session, link, world.bob, ReviewDecision.REJECT)

        assert link.status == MappingStatus.REJECTED
        assert link.needs_discussion

    async def test_unsure_first_reviewer_is_not_a_disagreement(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world)
        await review_link(db_session, link, world.alice, ReviewDecision.SECOND_REVIEW)

        await review_link(db_session, link, world.bob, ReviewDecision.REJECT)

        assert not link.needs_discussion

    async def test_second_review_cannot_be_deferred_again(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world)
        await review_link(db_session, link, world.alice, ReviewDecision.SECOND_REVIEW)

        with pytest.raises(InvalidRequestError, match="already the second review"):
            await review_link(db_session, link, world.bob, ReviewDecision.SECOND_REVIEW)

    @pytest.mark.usefixtures("system_roles")
    async def test_authorised_reviewer_reopens_rejected_link(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await grant_mapper(db_session, world, world.carol)
        link = await suggestion(db_session, world)
        await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT, policy=FOUR_EYES)
        await review_link(db_session, link, world.bob, ReviewDecision.REJECT)

        await reopen_link(db_session, world.carol, link)

        assert link.status == MappingStatus.SUGGESTED
        assert (link.first_reviewer_id, link.second_reviewer_id, link.needs_discussion) == (
            None,
            None,
            False,
        )
        await review_link(db_session, link, world.carol, ReviewDecision.ACCEPT)
        assert link.status == MappingStatus.ACCEPTED

    @pytest.mark.usefixtures("system_roles")
    async def test_reopen_needs_permission_and_a_rejected_link(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await grant_mapper(db_session, world, world.carol)
        rejected = await suggestion(db_session, world, 0)
        await review_link(db_session, rejected, world.alice, ReviewDecision.REJECT)
        accepted = await suggestion(db_session, world, 1)
        await review_link(db_session, accepted, world.alice, ReviewDecision.ACCEPT)

        # Bob has no mapping role for this objective's module.
        with pytest.raises(AuthorizationError):
            await reopen_link(db_session, world.bob, rejected)
        with pytest.raises(ConflictError, match="Only rejected"):
            await reopen_link(db_session, world.carol, accepted)
        assert rejected.status == MappingStatus.REJECTED

    async def test_invalid_coverage_correction(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world)

        with pytest.raises(InvalidRequestError):
            await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT, coverage=9)

    async def test_reviewer_removal_keeps_the_decision(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world)
        await review_link(db_session, link, world.alice, ReviewDecision.ACCEPT)

        await db_session.execute(delete(User).where(User.id == world.alice.id))
        await db_session.refresh(link)

        assert (link.status, link.first_reviewer_id) == (MappingStatus.ACCEPTED, None)


class TestBulkAccept:
    async def test_accepts_only_confident_suggestions(
        self, db_session: AsyncSession, world: World
    ) -> None:
        high = await suggestion(db_session, world, 0, confidence=0.95)
        edge = await suggestion(db_session, world, 1, confidence=0.9)
        low = await suggestion(db_session, world, 2, confidence=0.4)
        decided = await suggestion(db_session, world, 3, confidence=0.99)
        await review_link(db_session, decided, world.bob, ReviewDecision.REJECT)

        accepted = await bulk_accept(
            db_session, world.alice, [high, edge, low, decided], min_confidence=0.9
        )

        assert accepted == [high, edge]
        assert {link.accept_method for link in accepted} == {AcceptMethod.BULK}
        assert low.status == MappingStatus.SUGGESTED
        assert decided.status == MappingStatus.REJECTED
        assert len(await links_for_objective(db_session, world.objective.id)) == 4

    async def test_bulk_accept_in_four_eyes_mode(
        self, db_session: AsyncSession, world: World
    ) -> None:
        link = await suggestion(db_session, world, confidence=0.95)

        await bulk_accept(db_session, world.alice, [link], min_confidence=0.9, policy=FOUR_EYES)

        assert link.status == MappingStatus.NEEDS_SECOND_REVIEW
        assert link.accept_method is None


class TestReviewAssignments:
    async def test_assignments_are_unique(self, db_session: AsyncSession, world: World) -> None:
        module_id = world.objective.module_id
        version_id = world.objective.version_id
        framework_id = world.items[0].framework_id

        def assignment(**kwargs: object) -> ReviewAssignment:
            return ReviewAssignment(
                reviewer_id=world.alice.id,
                version_id=version_id,
                framework_id=framework_id,
                **kwargs,
            )

        await save(db_session, assignment(), assignment(module_id=module_id))
        await save(db_session, assignment(stage="second"))

        await must_fail(db_session, assignment())  # whole version again
        await must_fail(db_session, assignment(module_id=module_id))


class TestObjectiveScope:
    async def test_scope_per_level(self, db_session: AsyncSession) -> None:
        event = LearningEventFactory()
        await save(db_session, event)
        module = event.module
        version = module.version

        session_objective = await add_objective(db_session, event, "Session level.")
        module_objective = await add_objective(db_session, module, "Module level.")
        programme_outcome = await add_objective(db_session, version, "Programme level.")

        assert await objective_scope(db_session, session_objective) == ScopeRef(
            ScopeType.LEARNING_EVENT, event.id
        )
        assert await objective_scope(db_session, module_objective) == ScopeRef(
            ScopeType.MODULE, module.id
        )
        assert await objective_scope(db_session, programme_outcome) == ScopeRef(
            ScopeType.PROGRAMME, version.programme_id
        )


class TestMappingPolicy:
    def test_defaults(self) -> None:
        policy = parse_mapping_policy({})

        assert (policy.four_eyes, policy.second_review_for_rejects) == (False, False)

    def test_invalid_settings(self) -> None:
        with pytest.raises(InvalidRequestError, match="mapping settings"):
            parse_mapping_policy({"mapping": {"four_eyes": "yes please"}})

    async def test_read_from_the_objective_institution(
        self, db_session: AsyncSession, world: World
    ) -> None:
        from app.models import CurriculumVersion, Faculty, Institution, Programme

        version = await db_session.get(CurriculumVersion, world.objective.version_id)
        assert version is not None
        programme = await db_session.get(Programme, version.programme_id)
        assert programme is not None
        faculty = await db_session.get(Faculty, programme.faculty_id)
        assert faculty is not None
        institution = await db_session.get(Institution, faculty.institution_id)
        assert institution is not None
        assert await mapping_policy_for(db_session, world.objective) == MappingPolicy()

        institution.settings = {
            "mapping": {"four_eyes": True, "second_review_for_rejects": True},
            "terminology": {"module": "course"},
        }
        await db_session.flush()

        assert await mapping_policy_for(db_session, world.objective) == MappingPolicy(
            four_eyes=True, second_review_for_rejects=True
        )
