"""Tests for reading study guides: the confirmation, the AI reading, and deciding the proposals
(ADR 047). The API tests are at the end."""

import json
import uuid

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIDisabledError
from app.core.config import Settings, get_settings
from app.core.permissions import ScopeType
from app.models import AIRun, AIRunCall, AuditLog, Objective, ObjectiveProposal, User
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, ObjectiveStatus
from app.models.mapping import AIRunStatus, AIRunType
from app.models.proposal import ProposalStatus
from app.services import ai_mapping
from app.services import study_guide_extraction as extraction
from app.services.authorization import ConflictError, InvalidRequestError, ScopeRef
from app.services.study_guide_confirmation import CONFIRMATION_VERSION, StudyGuideConfirmation
from tests.conftest import EnqueuedJob
from tests.factories import ModuleFactory, UserFactory
from tests.mapping_helpers import Model, turn_ai_on
from tests.study_guide_helpers import OUTCOMES, guide_lines, make_docx, make_pdf
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"
YES = StudyGuideConfirmation(confirmed=True, text_version=CONFIRMATION_VERSION)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ai_objectives

    monkeypatch.setattr(ai_objectives, "RETRY_DELAY_SECONDS", 0.0)


@pytest.fixture
async def ready(db_session: AsyncSession, test_settings: Settings, world: World) -> World:
    await turn_ai_on(db_session, world, test_settings)
    return world


async def a_user(db: AsyncSession) -> User:
    user: User = UserFactory.build()
    db.add(user)
    await db.flush()
    return user


def guide_text_of(prompt: str) -> str:
    return prompt.split("Study guide text:\n", 1)[1].split("\n\nReturn JSON", 1)[0]


def finds_the_outcomes(prompt: str) -> str:
    """An honest model: it proposes every outcome line it can see, quoting the line."""
    text = guide_text_of(prompt)
    rows = [
        {"text": line, "domain": "knowledge", "source_quote": line}
        for line in text.splitlines()
        if line in OUTCOMES
    ]
    return json.dumps({"objectives": rows})


async def queued(
    db: AsyncSession,
    settings: Settings,
    redis: FakeAsyncRedis,
    world: World,
    *,
    content: bytes | None = None,
    actor: User | None = None,
    confirmation: StudyGuideConfirmation | None = YES,
) -> AIRun:
    return await extraction.start_extraction(
        db,
        settings,
        redis,
        actor=actor or await a_user(db),
        module=world.cardio,
        version=world.draft,
        content=content or make_docx(),
        confirmation=confirmation,
    )


async def confirmations(db: AsyncSession) -> list[AuditLog]:
    return list(
        await db.scalars(select(AuditLog).where(AuditLog.action == "study_guide_confirmation"))
    )


async def proposals(db: AsyncSession) -> list[ObjectiveProposal]:
    return list(await db.scalars(select(ObjectiveProposal).order_by(ObjectiveProposal.text)))


@pytest.fixture
def redis(redis_client: FakeAsyncRedis) -> FakeAsyncRedis:
    return redis_client


class TestStarting:
    async def test_the_confirmation_is_recorded_and_the_text_is_kept_for_the_job(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        content = make_docx()

        run = await queued(db_session, test_settings, redis, ready, content=content)

        assert run.type is AIRunType.EXTRACTION and run.status is AIRunStatus.QUEUED
        assert run.total_items == 1 and run.prompt_version == "extract:1"
        (event,) = await confirmations(db_session)
        assert event.context["text_version"] == CONFIRMATION_VERSION
        assert event.context["size_bytes"] == len(content)
        assert event.context["document_sha256"] == run.scope["document_sha256"]
        # The file's name is not known to the service, so it cannot be in the record.
        assert not {"filename", "file_name", "name"} & set(event.context)
        raw = await redis.get(extraction.text_key(run.id))
        assert raw is not None
        stored = json.loads(raw)
        assert "\n".join(stored["chunks"]).count("Describe the structure") == 1
        assert 0 < await redis.ttl(extraction.text_key(run.id)) <= extraction.TEXT_TTL_SECONDS

    @pytest.mark.parametrize(
        "confirmation",
        [
            None,
            StudyGuideConfirmation(confirmed=False, text_version=CONFIRMATION_VERSION),
            StudyGuideConfirmation(confirmed=True, text_version="0"),
        ],
    )
    async def test_without_a_current_confirmation_nothing_is_read_or_recorded(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        redis: FakeAsyncRedis,
        ready: World,
        confirmation: StudyGuideConfirmation | None,
    ) -> None:
        with pytest.raises(InvalidRequestError):
            await queued(db_session, test_settings, redis, ready, confirmation=confirmation)

        assert await confirmations(db_session) == []
        assert await redis.keys("study-guide:*") == []
        assert (
            await db_session.scalar(
                select(func.count(AIRun.id)).where(AIRun.type == AIRunType.EXTRACTION)
            )
            == 0
        )

    async def test_a_file_that_cannot_be_read_makes_no_run_and_keeps_nothing(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        with pytest.raises(InvalidRequestError, match="PDF or a Word"):
            await queued(db_session, test_settings, redis, ready, content=b"just some text")

        assert await redis.keys("study-guide:*") == []
        assert (
            await db_session.scalar(
                select(func.count(AIRun.id)).where(AIRun.type == AIRunType.EXTRACTION)
            )
            == 0
        )

    async def test_ai_switched_off_records_nothing(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, world: World
    ) -> None:
        with pytest.raises(AIDisabledError):
            await queued(db_session, test_settings, redis, world)

        assert await confirmations(db_session) == []

    async def test_a_published_version_is_read_only(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        elsewhere = ModuleFactory(version=ready.published, code="HSC999")
        db_session.add(elsewhere)
        await db_session.flush()
        with pytest.raises(ConflictError):
            await extraction.start_extraction(
                db_session,
                test_settings,
                redis,
                actor=await a_user(db_session),
                module=elsewhere,
                version=ready.published,
                content=make_docx(),
                confirmation=YES,
            )

    async def test_one_reading_at_a_time_for_a_module(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        await queued(db_session, test_settings, redis, ready)

        with pytest.raises(ConflictError, match="already being read"):
            await queued(db_session, test_settings, redis, ready)

    async def test_a_reading_that_died_does_not_block_the_module_for_ever(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import update

        old = await queued(db_session, test_settings, redis, ready)
        await db_session.execute(
            update(AIRun)
            .where(AIRun.id == old.id)
            .values(created_at=datetime.now(UTC) - timedelta(hours=3))
        )
        await db_session.refresh(old)

        again = await queued(db_session, test_settings, redis, ready)

        await db_session.refresh(old)
        assert old.status is AIRunStatus.FAILED and again.status is AIRunStatus.QUEUED

    async def test_a_pdf_is_read_like_a_word_file(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await queued(db_session, test_settings, redis, ready, content=make_pdf())
        assert run.total_items == 1


async def read(
    db: AsyncSession,
    settings: Settings,
    redis: FakeAsyncRedis,
    world: World,
    model: Model,
    *,
    content: bytes | None = None,
) -> AIRun:
    run = await queued(db, settings, redis, world, content=content)
    return await extraction.execute_extraction(
        db, settings, redis, run.id, transport=model.transport
    )


class TestReading:
    async def test_the_outcomes_become_pending_proposals_with_their_quotes(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        model = Model(finds_the_outcomes)

        done = await read(db_session, test_settings, redis, ready, model)

        assert done.status is AIRunStatus.SUCCEEDED and done.done_items == done.total_items == 1
        found = await proposals(db_session)
        assert [p.text for p in found] == sorted(OUTCOMES)
        assert {p.status for p in found} == {ProposalStatus.PENDING}
        assert all(p.source_quote == p.text and p.module_id == ready.cardio.id for p in found)
        assert all(p.run_id == done.id for p in found)
        # The study-guide text went to the AI (the guard allowed it with the receipt)...
        assert "Describe the structure of the heart" in model.prompts[0]
        # ...and the text is no longer kept once the reading has ended.
        assert await redis.keys("study-guide:*") == []
        # Nothing became curriculum.
        assert (
            await db_session.scalar(
                select(func.count(Objective.id)).where(
                    Objective.module_id == ready.cardio.id, Objective.text.in_(OUTCOMES)
                )
            )
            == 0
        )

    async def test_every_call_is_recorded_on_the_run(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        done = await read(db_session, test_settings, redis, ready, Model(finds_the_outcomes))

        calls = list(await db_session.scalars(select(AIRunCall).where(AIRunCall.run_id == done.id)))
        assert [c.valid for c in calls] == [True]
        assert done.estimated_cost > 0

    async def test_wording_the_module_already_has_is_not_proposed_again(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        from app.services.curriculum import add_objective

        await add_objective(db_session, ready.cardio, OUTCOMES[0])
        await read(db_session, test_settings, redis, ready, Model(finds_the_outcomes))
        found = await proposals(db_session)
        assert OUTCOMES[0] not in [p.text for p in found] and len(found) == 2

        # Reading the same guide again adds nothing new.
        second = await read(db_session, test_settings, redis, ready, Model(finds_the_outcomes))
        assert second.status is AIRunStatus.SUCCEEDED
        assert len(await proposals(db_session)) == 2

    async def test_a_quote_that_is_not_in_the_guide_is_asked_for_again(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        answers = [
            json.dumps(
                {
                    "objectives": [
                        {
                            "text": "Name every bone.",
                            "domain": None,
                            "source_quote": "Name every bone.",
                        }
                    ]
                }
            ),
            None,
        ]

        def answer(prompt: str) -> str:
            first = answers.pop(0)
            return first if first is not None else finds_the_outcomes(prompt)

        model = Model(answer)
        done = await read(db_session, test_settings, redis, ready, model)

        assert done.status is AIRunStatus.SUCCEEDED and done.failed_items == 0
        assert "Your previous answer was rejected" in model.prompts[1]
        assert "not words of the study guide" in model.prompts[1]
        assert "Name every bone" not in model.prompts[1]  # the model's words are not fed back
        assert len(await proposals(db_session)) == 3

    async def test_an_answer_that_stays_unusable_fails_the_piece(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        model = Model(lambda prompt: "not json")

        done = await read(db_session, test_settings, redis, ready, model)

        assert len(model.requests) == 2
        assert done.status is AIRunStatus.FAILED and done.failed_items == 1
        assert done.error_message == "No part of the study guide could be read by the AI."
        assert await proposals(db_session) == []

    async def test_personal_information_in_the_guide_is_not_sent(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        lines = [*guide_lines(), "Contact the coordinator at jane.doe@example.org for questions."]
        model = Model(finds_the_outcomes)

        done = await read(db_session, test_settings, redis, ready, model, content=make_docx(lines))

        assert model.requests == []
        assert done.status is AIRunStatus.FAILED and done.failed_items == 1
        assert await proposals(db_session) == []

    async def test_a_long_guide_is_read_in_pieces_and_says_when_the_end_was_left_out(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        redis: FakeAsyncRedis,
        ready: World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services import study_guide_text

        monkeypatch.setattr(study_guide_text, "CHUNK_CHARS", 300)
        monkeypatch.setattr(study_guide_text, "MAX_CHUNKS", 2)
        filler = [
            f"Background paragraph {n} about the heart and the circulation." for n in range(30)
        ]
        model = Model(finds_the_outcomes)

        done = await read(
            db_session,
            test_settings,
            redis,
            ready,
            model,
            content=make_docx([*guide_lines(), *filler]),
        )

        assert done.total_items == 2 and len(model.requests) == 2
        assert done.status is AIRunStatus.SUCCEEDED
        assert done.error_message == "only the first part of a long study guide was read"

    async def test_the_text_having_expired_ends_the_run_with_a_reason(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await queued(db_session, test_settings, redis, ready)
        await redis.delete(extraction.text_key(run.id))

        done = await extraction.execute_extraction(
            db_session, test_settings, redis, run.id, transport=Model().transport
        )

        assert done.status is AIRunStatus.FAILED and "Upload the study guide again" in (
            done.error_message or ""
        )

    async def test_without_a_recorded_confirmation_nothing_is_sent(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await queued(db_session, test_settings, redis, ready)
        model = Model(finds_the_outcomes)
        # Make the run look like another person's: someone who confirmed nothing.
        run.created_by_id = (await a_user(db_session)).id
        await db_session.flush()

        done = await extraction.execute_extraction(
            db_session, test_settings, redis, run.id, transport=model.transport
        )

        assert model.requests == []
        assert done.status is AIRunStatus.FAILED

    async def test_the_budget_stops_the_reading_with_its_own_state(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, world: World
    ) -> None:
        await turn_ai_on(db_session, world, test_settings, monthly_call_cap=0)

        model = Model(finds_the_outcomes)
        done = await read(db_session, test_settings, redis, world, model)

        assert done.status is AIRunStatus.BUDGET_EXCEEDED and model.requests == []

    async def test_a_cancelled_reading_stops_before_the_next_piece(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        redis: FakeAsyncRedis,
        ready: World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services import study_guide_text

        monkeypatch.setattr(study_guide_text, "CHUNK_CHARS", 300)
        filler = [
            f"Background paragraph {n} about the heart and the circulation." for n in range(30)
        ]
        run = await queued(
            db_session, test_settings, redis, ready, content=make_docx([*guide_lines(), *filler])
        )
        assert run.total_items > 1
        model = Model(finds_the_outcomes)
        steps: list[int] = []

        async def after() -> None:
            steps.append(1)
            if len(steps) == 2:
                await ai_mapping.cancel_run(db_session, run)
                await db_session.flush()

        done = await extraction.execute_extraction(
            db_session, test_settings, redis, run.id, transport=model.transport, after_piece=after
        )

        assert done.status is AIRunStatus.CANCELLED and len(model.requests) == 1


async def one_proposal(
    db: AsyncSession, run: AIRun, world: World, **fields: object
) -> ObjectiveProposal:
    proposal = ObjectiveProposal(
        run_id=run.id,
        module_id=world.cardio.id,
        text="Describe the structure of the heart.",
        domain=ObjectiveDomain.KNOWLEDGE,
        source_quote="Describe the structure of the heart.",
        **fields,
    )
    db.add(proposal)
    await db.flush()
    return proposal


class TestDeciding:
    async def run_row(
        self, db: AsyncSession, settings: Settings, redis: FakeAsyncRedis, world: World
    ) -> AIRun:
        return await queued(db, settings, redis, world)

    async def test_accepting_makes_a_draft_objective_of_the_module(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await self.run_row(db_session, test_settings, redis, ready)
        proposal = await one_proposal(db_session, run, ready)
        actor = await a_user(db_session)

        objective = await extraction.accept_proposal(
            db_session, proposal, actor=actor, module=ready.cardio, version=ready.draft
        )

        assert objective.text == "Describe the structure of the heart."
        assert objective.level is ObjectiveLevel.MODULE and objective.module_id == ready.cardio.id
        assert objective.status is ObjectiveStatus.DRAFT
        assert objective.domain is ObjectiveDomain.KNOWLEDGE
        assert proposal.status is ProposalStatus.ACCEPTED
        assert proposal.objective_id == objective.id and proposal.decided_by_id == actor.id

    async def test_corrections_made_while_accepting_are_applied(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await self.run_row(db_session, test_settings, redis, ready)
        proposal = await one_proposal(db_session, run, ready)

        objective = await extraction.accept_proposal(
            db_session,
            proposal,
            actor=await a_user(db_session),
            module=ready.cardio,
            version=ready.draft,
            text="  Name the chambers of the heart. ",
            domain=None,
            change_domain=True,
        )

        assert objective.text == "Name the chambers of the heart." and objective.domain is None
        assert proposal.text == "Describe the structure of the heart."  # what was proposed stays

    async def test_a_proposal_is_decided_once(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await self.run_row(db_session, test_settings, redis, ready)
        proposal = await one_proposal(db_session, run, ready)
        actor = await a_user(db_session)
        await extraction.reject_proposal(db_session, proposal, actor=actor)

        with pytest.raises(ConflictError):
            await extraction.accept_proposal(
                db_session, proposal, actor=actor, module=ready.cardio, version=ready.draft
            )
        with pytest.raises(ConflictError):
            await extraction.reject_proposal(db_session, proposal, actor=actor)
        assert proposal.status is ProposalStatus.REJECTED and proposal.objective_id is None

    async def test_blank_wording_is_refused(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        run = await self.run_row(db_session, test_settings, redis, ready)
        proposal = await one_proposal(db_session, run, ready)

        with pytest.raises(InvalidRequestError):
            await extraction.accept_proposal(
                db_session,
                proposal,
                actor=await a_user(db_session),
                module=ready.cardio,
                version=ready.draft,
                text="   ",
            )
        assert proposal.status is ProposalStatus.PENDING

    async def test_a_rejected_wording_is_not_proposed_again(
        self, db_session: AsyncSession, test_settings: Settings, redis: FakeAsyncRedis, ready: World
    ) -> None:
        await read(db_session, test_settings, redis, ready, Model(finds_the_outcomes))
        first = (await proposals(db_session))[0]
        await extraction.reject_proposal(db_session, first, actor=await a_user(db_session))
        # A rejection is a person's "no": reading the same guide again does not ask again.
        again = await read(db_session, test_settings, redis, ready, Model(finds_the_outcomes))
        assert again.status is AIRunStatus.SUCCEEDED
        texts = [p.text for p in await proposals(db_session)]
        assert texts.count(first.text) == 1 and len(texts) == 3


async def upload(
    client: AsyncClient,
    world: World,
    content: bytes,
    *,
    confirmed: str | None = "true",
    text_version: str | None = CONFIRMATION_VERSION,
    module_id: object = None,
) -> Response:
    data: dict[str, str] = {}
    if confirmed is not None:
        data["confirmed"] = confirmed
    if text_version is not None:
        data["text_version"] = text_version
    return await client.post(
        f"{API}/modules/{module_id or world.cardio.id}/study-guides",
        files={"file": ("secret-patient-name.docx", content, "application/octet-stream")},
        data=data,
    )


class TestApi:
    async def test_requires_sign_in(self, api_client: AsyncClient, world: World) -> None:
        for method, path in (
            ("POST", f"/modules/{world.cardio.id}/study-guides"),
            ("GET", f"/modules/{world.cardio.id}/study-guide-runs"),
            ("GET", f"/modules/{world.cardio.id}/objective-proposals"),
            ("POST", f"/objective-proposals/{world.cardio.id}/accept"),
            ("POST", f"/objective-proposals/{world.cardio.id}/reject"),
            ("POST", f"/study-guide-runs/{world.cardio.id}/cancel"),
        ):
            response = await api_client.request(method, f"{API}{path}")
            assert response.status_code == 401, path

    async def test_a_director_uploads_a_guide_and_a_job_is_queued(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
        ready: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await upload(api_client, ready, make_docx())

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "queued" and body["module_id"] == str(ready.cardio.id)
        assert (body["total_items"], body["proposals_created"], body["truncated"]) == (1, 0, False)
        assert [(j.actor, j.args) for j in enqueued_jobs if j.actor == "run_study_guide"] == [
            ("run_study_guide", (body["id"],))
        ]
        # The file name the browser sent is nowhere in what was recorded.
        (event,) = await confirmations(db_session)
        assert "secret-patient-name" not in json.dumps(event.context)
        assert "secret-patient-name" not in json.dumps(body)

    @pytest.mark.parametrize(
        ("confirmed", "text_version"),
        [
            (None, CONFIRMATION_VERSION),
            ("true", None),
            ("false", CONFIRMATION_VERSION),
            ("true", "0"),
        ],
    )
    async def test_an_upload_without_the_confirmation_is_422_and_writes_nothing(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        enqueued_jobs: list[EnqueuedJob],
        redis_client: FakeAsyncRedis,
        ready: World,
        confirmed: str | None,
        text_version: str | None,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await upload(
            api_client, ready, make_docx(), confirmed=confirmed, text_version=text_version
        )

        assert response.status_code == 422
        assert await confirmations(db_session) == []
        assert await redis_client.keys("study-guide:*") == []
        assert [j for j in enqueued_jobs if j.actor == "run_study_guide"] == []
        assert (
            await db_session.scalar(
                select(func.count(AIRun.id)).where(AIRun.type == AIRunType.EXTRACTION)
            )
            == 0
        )

    @pytest.mark.parametrize("content", [b"plain text, not a document", b""])
    async def test_something_that_is_not_a_pdf_or_word_file_is_422(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        content: bytes,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        response = await upload(api_client, ready, content)
        assert response.status_code == 422

    async def test_a_file_over_the_limit_is_413(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import study_guides

        monkeypatch.setattr(study_guides, "MAX_UPLOAD_BYTES", 100)
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await upload(api_client, ready, make_docx())

        assert response.status_code == 413
        assert await confirmations(db_session) == []

    @pytest.mark.parametrize("role", ["lecturer", "mapper"])
    async def test_people_without_both_permissions_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        role: str,
    ) -> None:
        scope = (
            ScopeRef(ScopeType.MODULE, ready.cardio.id)
            if role == "lecturer"
            else programme_scope(ready)
        )
        await sign_in(api_client, db_session, test_settings, role, scope)

        response = await upload(api_client, ready, make_docx())

        assert response.status_code == 403
        assert await confirmations(db_session) == []

    async def test_a_module_coordinator_may_use_their_own_module_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, ready.cardio.id),
        )

        own = await upload(api_client, ready, make_docx())
        other = await upload(api_client, ready, make_docx(), module_id=ready.anatomy.id)

        assert own.status_code == 202
        assert other.status_code in (403, 404)

    async def test_ai_switched_off_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

        response = await upload(api_client, world, make_docx())

        assert response.status_code == 409
        assert await confirmations(db_session) == []

    async def test_runs_and_proposals_are_listed_and_decided(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        redis_client: FakeAsyncRedis,
        ready: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        started = (await upload(api_client, ready, make_docx())).json()
        run = await db_session.get(AIRun, uuid.UUID(started["id"]))
        assert run is not None
        await extraction.execute_extraction(
            db_session,
            test_settings,
            redis_client,
            run.id,
            transport=Model(finds_the_outcomes).transport,
        )

        runs = (await api_client.get(f"{API}/modules/{ready.cardio.id}/study-guide-runs")).json()
        pending = (
            await api_client.get(f"{API}/modules/{ready.cardio.id}/objective-proposals")
        ).json()

        assert [r["status"] for r in runs] == ["succeeded"]
        assert runs[0]["proposals_created"] == 3 and runs[0]["done_items"] == 1
        assert sorted(p["text"] for p in pending) == sorted(OUTCOMES)
        first, second = pending[0], pending[1]

        accepted = await api_client.post(
            f"{API}/objective-proposals/{first['id']}/accept",
            json={
                "text": "Describe the heart and its cycle.",
                "set_domain": True,
                "domain": "skill",
            },
        )
        rejected = await api_client.post(f"{API}/objective-proposals/{second['id']}/reject")
        again = await api_client.post(f"{API}/objective-proposals/{first['id']}/accept", json={})

        assert accepted.status_code == 200, accepted.text
        objective = await db_session.get(Objective, uuid.UUID(accepted.json()["objective_id"]))
        assert objective is not None
        assert objective.text == "Describe the heart and its cycle."
        assert (
            objective.domain is ObjectiveDomain.SKILL and objective.status is ObjectiveStatus.DRAFT
        )
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
        assert again.status_code == 409
        left = (await api_client.get(f"{API}/modules/{ready.cardio.id}/objective-proposals")).json()
        assert len(left) == 1

    async def test_a_proposal_of_a_module_one_does_not_hold_is_not_found_or_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        redis_client: FakeAsyncRedis,
        ready: World,
    ) -> None:
        run = await queued(db_session, test_settings, redis_client, ready)
        proposal = await one_proposal(db_session, run, ready)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, ready.anatomy.id),
        )

        response = await api_client.post(f"{API}/objective-proposals/{proposal.id}/accept", json={})

        assert response.status_code in (403, 404)
        await db_session.refresh(proposal)
        assert proposal.status is ProposalStatus.PENDING

    async def test_a_reading_can_be_cancelled(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        started = (await upload(api_client, ready, make_docx())).json()

        response = await api_client.post(f"{API}/study-guide-runs/{started['id']}/cancel")

        assert response.status_code == 200 and response.json()["status"] == "cancelled"
        again = await upload(api_client, ready, make_docx())
        assert again.status_code == 202  # the module is free again


class TestAcceptedProposalIsEmbedded:
    async def test_accepting_a_proposal_queues_the_embedding_of_the_new_objective(
        self,
        api_app: FastAPI,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        redis_client: FakeAsyncRedis,
        enqueued_jobs: list[EnqueuedJob],
        ready: World,
    ) -> None:
        on = test_settings.model_copy(update={"embeddings_local": True})
        api_app.dependency_overrides[get_settings] = lambda: on
        await sign_in(api_client, db_session, on, "programme_director", programme_scope(ready))
        started = (await upload(api_client, ready, make_docx())).json()
        run = await db_session.get(AIRun, uuid.UUID(started["id"]))
        assert run is not None
        await extraction.execute_extraction(
            db_session, on, redis_client, run.id, transport=Model(finds_the_outcomes).transport
        )
        [first, *_] = (
            await api_client.get(f"{API}/modules/{ready.cardio.id}/objective-proposals")
        ).json()

        accepted = await api_client.post(f"{API}/objective-proposals/{first['id']}/accept", json={})

        assert accepted.status_code == 200, accepted.text
        queued = [j for j in enqueued_jobs if j.actor == "embed_objective"]
        assert [j.args for j in queued] == [(accepted.json()["objective_id"],)]
