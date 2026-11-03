"""Tests for the rules added in Slice 1.16b: cut-off answers, the depth rule, the minimum coverage,
the specific item before its parent, calls made again, stale runs and rewording (ADR 045)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AIRun, AIRunCall, FrameworkItem, MappingLink
from app.models.mapping import AIRunStatus, MappingSource, MappingStatus
from app.services import ai_mapping
from app.services.curriculum_objectives import update_objective
from tests.mapping_helpers import (
    Library,
    Model,
    good_answer,
    institution_of,
    make_library,
    offered_codes,
)
from tests.test_ai_mapping import a_user, links, start
from tests.test_ai_mapping import ready_world as ready_world  # fixture
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture
from tests.test_mapping_shortlist import link


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_mapping, "RETRY_DELAYS", (0.0, 0.0))


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


async def set_policy(db: AsyncSession, world: World, **mapping: object) -> None:
    institution = await institution_of(db, world)
    institution.settings = {**institution.settings, "mapping": mapping}
    await db.flush()


async def only_the_lecture(db: AsyncSession, world: World) -> None:
    """Leave one objective that shares words with the library: the lecture's."""
    world.cardio_outcome.soft_delete()
    await db.flush()


async def run_it(
    db: AsyncSession,
    settings: Settings,
    world: World,
    library: Library,
    model: Model,
) -> AIRun:
    run = await start(db, settings, world, library, module=world.cardio)
    return await ai_mapping.execute_run(db, settings, run.id, transport=model.transport)


class TestCutOffAnswers:
    async def test_an_answer_that_hit_the_token_limit_is_asked_for_again_shorter(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model(stop_reasons=["max_tokens"])

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert done.status is AIRunStatus.SUCCEEDED and done.failed_items == 0
        assert done.links_created == 1 and len(model.requests) == 2
        assert "cut off because it was too long" in model.prompts[1]
        calls = list(await db_session.scalars(select(AIRunCall).where(AIRunCall.run_id == done.id)))
        assert sorted(bool(c.valid) for c in calls) == [False, True]
        assert {c.error_message for c in calls if not c.valid} == {
            "the answer was cut off at the token limit"
        }

    async def test_an_answer_cut_off_twice_counts_as_failed(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model(stop_reasons=["max_tokens", "max_tokens"])

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert done.status is AIRunStatus.FAILED and done.failed_items == 1
        assert len(model.requests) == 2 and await links(db_session) == []

    async def test_the_prompt_asks_for_matches_only(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model()

        await run_it(db_session, test_settings, ready_world, library, model)

        assert "list ONLY the candidates the objective matches" in model.prompts[0]


class TestDepthRule:
    async def test_not_applicable_on_an_item_with_a_level_is_retried_with_the_reason(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        library.heart.description = "Describes the structure of the heart."  # states a level
        await db_session.flush()
        await only_the_lecture(db_session, ready_world)
        calls: list[int] = []

        def answer(prompt: str) -> str:
            calls.append(1)
            data = json.loads(good_answer(prompt))
            data["candidates"] = [c for c in data["candidates"] if c["code"] == "HRT1"]
            data["candidates"][0].update(
                is_match=True,
                coverage=3,
                evidence_quote="cardiac cycle",
                rationale="It covers the cycle.",
                depth_match="not_applicable" if len(calls) == 1 else "matches",
            )
            return json.dumps(data)

        model = Model(answer)
        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert len(model.requests) == 2 and done.failed_items == 0
        assert "not_applicable is only for an item that states no verb or level" in model.prompts[1]
        (made,) = await links(db_session)
        assert made.depth_match == "matches"

    async def test_an_item_with_no_verb_or_level_is_marked_and_may_be_not_applicable(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        keyword = FrameworkItem(
            framework_id=library.framework.id, code="KW1", title="Cardiac imaging", description=""
        )
        db_session.add(keyword)
        await db_session.flush()
        await only_the_lecture(db_session, ready_world)

        def answer(prompt: str) -> str:
            rows = [
                {
                    "code": "KW1",
                    "is_match": True,
                    "coverage": 2,
                    "depth_match": "not_applicable",
                    "confidence": 0.7,
                    "rationale": "It is about the cycle.",
                    "evidence_quote": "cardiac cycle",
                }
            ]
            return json.dumps({"candidates": rows})

        model = Model(answer)
        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert "KW1: Cardiac imaging [no verb or level]" in model.prompts[0]
        assert len(model.requests) == 1 and done.failed_items == 0
        (made,) = await links(db_session)
        assert made.framework_item_id == keyword.id


class TestMinimumCoverage:
    @pytest.mark.parametrize(("minimum", "expected"), [(None, 1), (4, 1), (5, 0)])
    async def test_suggestions_below_the_minimum_are_dropped(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
        minimum: int | None,
        expected: int,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        if minimum is not None:
            await set_policy(db_session, ready_world, ai_min_coverage=minimum)

        done = await run_it(db_session, test_settings, ready_world, library, Model())

        # The test model answers coverage 4 for the match.
        assert done.links_created == expected and len(await links(db_session)) == expected


class TestSpecificItemFirst:
    async def child(self, db: AsyncSession, library: Library) -> FrameworkItem:
        item = FrameworkItem(
            framework_id=library.framework.id,
            code="HRT1.1",
            title="Cardiac cycle phases",
            description="Names the phases of the cardiac cycle.",
            parent_id=library.heart.id,
            depth=1,
        )
        db.add(item)
        await db.flush()
        return item

    def everything_matches(self, prompt: str) -> str:
        return good_answer(prompt, matches=len(offered_codes(prompt)))

    async def test_a_parent_is_not_suggested_next_to_its_child(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        child = await self.child(db_session, library)
        await only_the_lecture(db_session, ready_world)

        await run_it(
            db_session, test_settings, ready_world, library, Model(self.everything_matches)
        )

        assert {link_.framework_item_id for link_ in await links(db_session)} == {child.id}

    async def test_switched_off_both_are_suggested(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        child = await self.child(db_session, library)
        await only_the_lecture(db_session, ready_world)
        await set_policy(db_session, ready_world, ai_prefer_specific_item=False)

        await run_it(
            db_session, test_settings, ready_world, library, Model(self.everything_matches)
        )

        assert {link_.framework_item_id for link_ in await links(db_session)} == {
            child.id,
            library.heart.id,
        }

    async def test_a_child_linked_earlier_keeps_its_parent_out(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        child = await self.child(db_session, library)
        await only_the_lecture(db_session, ready_world)
        await link(db_session, ready_world.lecture_objective, child, MappingStatus.ACCEPTED)

        await run_it(
            db_session, test_settings, ready_world, library, Model(self.everything_matches)
        )

        assert await links(db_session) == []  # the parent is the only candidate left, and dropped

    async def test_a_parent_without_a_matching_child_is_still_suggested(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await self.child(db_session, library)
        await only_the_lecture(db_session, ready_world)

        def parent_only(prompt: str) -> str:
            data = json.loads(good_answer(prompt, matches=len(offered_codes(prompt))))
            data["candidates"] = [c for c in data["candidates"] if c["code"] == "HRT1"]
            return json.dumps(data)

        await run_it(db_session, test_settings, ready_world, library, Model(parent_only))

        assert [link_.framework_item_id for link_ in await links(db_session)] == [library.heart.id]


class TestCallsMadeAgain:
    async def test_a_busy_provider_is_tried_again_and_then_succeeds(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model(statuses=[429, 529])

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert len(model.requests) == 3
        assert done.status is AIRunStatus.SUCCEEDED and done.failed_items == 0
        assert done.links_created == 1
        recorded = await db_session.scalar(
            select(AIRunCall).where(AIRunCall.run_id == done.id, AIRunCall.valid.is_(True))
        )
        assert recorded is not None

    async def test_it_gives_up_after_two_more_tries(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model(statuses=[503, 503, 503, 503])

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert len(model.requests) == 3
        assert done.status is AIRunStatus.FAILED and done.failed_items == 1

    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    async def test_a_refusal_is_not_tried_again(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
        status: int,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        model = Model(statuses=[status, status])

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert len(model.requests) == 1 and done.failed_items == 1


class TestStaleRuns:
    async def make(
        self,
        db: AsyncSession,
        settings: Settings,
        world: World,
        library: Library,
        status: AIRunStatus,
        *,
        updated: timedelta = timedelta(0),
        created: timedelta = timedelta(0),
    ) -> AIRun:
        run = await start(db, settings, world, library)
        now = datetime.now(UTC)
        await db.execute(
            update(AIRun)
            .where(AIRun.id == run.id)
            .values(status=status, updated_at=now - updated, created_at=now - created)
        )
        await db.refresh(run)
        return run

    async def test_a_running_run_without_progress_is_ended_and_a_new_one_may_start(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        run = await self.make(
            db_session,
            test_settings,
            ready_world,
            library,
            AIRunStatus.RUNNING,
            updated=timedelta(minutes=21),
        )

        again = await start(db_session, test_settings, ready_world, library)

        await db_session.refresh(run)
        assert run.status is AIRunStatus.FAILED and run.finished_at is not None
        assert run.error_message and "stopped without finishing" in run.error_message
        assert again.status is AIRunStatus.QUEUED

    async def test_a_run_with_recent_progress_is_left_alone(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        run = await self.make(
            db_session,
            test_settings,
            ready_world,
            library,
            AIRunStatus.RUNNING,
            updated=timedelta(minutes=5),
        )

        assert await ai_mapping.expire_stale_runs(db_session) == 0
        await db_session.refresh(run)
        assert run.status is AIRunStatus.RUNNING

    async def test_a_queued_run_is_ended_only_after_a_long_wait(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        recent = await self.make(
            db_session,
            test_settings,
            ready_world,
            library,
            AIRunStatus.QUEUED,
            created=timedelta(minutes=90),
        )
        assert await ai_mapping.expire_stale_runs(db_session) == 0

        await db_session.execute(
            update(AIRun)
            .where(AIRun.id == recent.id)
            .values(created_at=datetime.now(UTC) - timedelta(hours=3))
        )
        await db_session.refresh(recent)
        assert await ai_mapping.expire_stale_runs(db_session) == 1
        assert recent.status is AIRunStatus.FAILED

    async def test_a_job_that_is_still_alive_stops_when_its_run_was_ended(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        run = await start(db_session, test_settings, ready_world, library)
        steps: list[int] = []

        async def after() -> None:
            steps.append(1)
            if len(steps) == 2:  # after the first objective
                refreshed = await db_session.get(AIRun, run.id)
                assert refreshed is not None
                refreshed.status = AIRunStatus.FAILED
                await db_session.flush()  # as another process's commit would be seen

        done = await ai_mapping.execute_run(
            db_session, test_settings, run.id, transport=Model().transport, after_objective=after
        )

        assert done.status is AIRunStatus.FAILED
        assert done.done_items == 1 < done.total_items


class TestRewording:
    async def reject(
        self,
        db: AsyncSession,
        world: World,
        library: Library,
        *,
        decided: datetime,
        changed: datetime | None,
    ) -> MappingLink:
        rejected = await link(db, world.lecture_objective, library.heart, MappingStatus.REJECTED)
        rejected.first_reviewed_at = decided
        world.lecture_objective.text_changed_at = changed
        reviewer = await a_user(db)
        rejected.first_reviewer_id = reviewer
        rejected.first_decision = "reject"  # type: ignore[assignment]
        await db.flush()
        return rejected

    async def test_a_rejection_before_a_rewording_is_asked_again_and_suggested_anew(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        now = datetime.now(UTC)
        rejected = await self.reject(
            db_session,
            ready_world,
            library,
            decided=now - timedelta(days=2),
            changed=now - timedelta(days=1),
        )
        model = Model()

        done = await run_it(db_session, test_settings, ready_world, library, model)

        assert len(model.requests) == 1 and done.links_created == 1
        await db_session.refresh(rejected)
        assert rejected.status is MappingStatus.SUGGESTED
        assert rejected.source is MappingSource.AI and rejected.ai_run_id == done.id
        assert rejected.first_reviewer_id is None and rejected.first_decision is None

    async def test_a_rejection_after_the_rewording_stands(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        now = datetime.now(UTC)
        rejected = await self.reject(
            db_session,
            ready_world,
            library,
            decided=now - timedelta(days=1),
            changed=now - timedelta(days=2),
        )
        model = Model()

        await run_it(db_session, test_settings, ready_world, library, model)

        assert model.requests == []
        await db_session.refresh(rejected)
        assert rejected.status is MappingStatus.REJECTED

    async def test_a_rejection_of_words_never_changed_stands(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        await only_the_lecture(db_session, ready_world)
        rejected = await self.reject(
            db_session,
            ready_world,
            library,
            decided=datetime.now(UTC) - timedelta(days=1),
            changed=None,
        )
        model = Model()

        await run_it(db_session, test_settings, ready_world, library, model)

        assert model.requests == []
        await db_session.refresh(rejected)
        assert rejected.status is MappingStatus.REJECTED

    async def test_editing_the_wording_records_when(
        self, db_session: AsyncSession, ready_world: World
    ) -> None:
        objective = ready_world.lecture_objective
        assert objective.text_changed_at is None

        await update_objective(
            db_session,
            objective,
            ready_world.draft,
            {"status": objective.status},
            options=[],
        )
        assert objective.text_changed_at is None  # not a change of words

        await update_objective(
            db_session,
            objective,
            ready_world.draft,
            {"text": "Describe the heart's cycle."},
            options=[],
        )
        assert objective.text_changed_at is not None
