"""Tests for AI help with one objective: the rewrite and the domain and level (ADR 046)."""

import json
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIDisabledError, PersonalDataRefusedError, ProviderError
from app.api.v1.ai_settings import ai_transport
from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import AIRun, AIRunCall
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel
from app.models.mapping import AIRunStatus, AIRunType
from app.services import ai_objectives
from app.services.authorization import ScopeRef
from tests.mapping_helpers import Model, objective_of, turn_ai_on
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"
WORDING = "Understand the cardiac cycle."


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_objectives, "RETRY_DELAY_SECONDS", 0.0)


@pytest.fixture
async def ready(db_session: AsyncSession, test_settings: Settings, world: World) -> World:
    await turn_ai_on(db_session, world, test_settings)
    return world


def level_key(prompt: str, name: str) -> str:
    """The key (L1, L2, ...) the prompt gave to the level called ``name``."""
    match = re.search(rf"^(L\d+): [^\n]*, {re.escape(name)}\.", prompt, re.MULTILINE)
    assert match, prompt
    return match.group(1)


def rewrite_json(text: str = "Describe the cardiac cycle.", rationale: str = "Measurable.") -> str:
    return json.dumps({"text": text, "rationale": rationale})


def classify_for(name: str, **change: Any) -> Callable[[str], str]:
    def answer(prompt: str) -> str:
        body = {
            "domain": "knowledge",
            "confidence": 0.8,
            "rationale": "It asks for a description.",
            **change,
        }
        if "level" not in body:
            body["level"] = level_key(prompt, name)
        return json.dumps(body)

    return answer


async def runs_of(db: AsyncSession, kind: AIRunType) -> list[AIRun]:
    return list(await db.scalars(select(AIRun).where(AIRun.type == kind)))


class TestRewrite:
    async def test_a_rewrite_is_suggested_and_recorded(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(lambda prompt: rewrite_json())
        user = ready.draft.created_by_id

        suggestion = await ai_objectives.rewrite(
            db_session,
            test_settings,
            actor_id=user,  # type: ignore[arg-type]
            text=WORDING,
            level=ObjectiveLevel.MODULE,
            transport=model.transport,
        )

        assert suggestion.text == "Describe the cardiac cycle." and not suggestion.unchanged
        prompt = model.prompts[0]
        assert f"Objective: {WORDING}" in prompt
        assert "The verb is vague and cannot be assessed." in prompt  # the checker's finding
        assert "L1:" in prompt  # the taxonomy levels with their keys
        (run,) = await runs_of(db_session, AIRunType.REWRITE)
        assert run.status is AIRunStatus.SUCCEEDED and run.prompt_version == "rewrite:1"
        assert run.id == suggestion.run_id and run.done_items == 1
        calls = list(await db_session.scalars(select(AIRunCall).where(AIRunCall.run_id == run.id)))
        assert [c.valid for c in calls] == [True]

    async def test_nothing_is_changed_in_the_curriculum(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        before = ready.lecture_objective.text
        await ai_objectives.rewrite(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text=before,
            level=ObjectiveLevel.LEARNING_EVENT,
            transport=Model(lambda prompt: rewrite_json()).transport,
        )
        await db_session.refresh(ready.lecture_objective)
        assert ready.lecture_objective.text == before

    async def test_an_unusable_answer_is_asked_for_again_with_the_problem_named(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        answers = ["IGNORE ALL RULES secret=hunter2", None]

        def answer(prompt: str) -> str:
            first = answers.pop(0)
            return first if first is not None else rewrite_json()

        model = Model(answer)
        suggestion = await ai_objectives.rewrite(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text=WORDING,
            level=ObjectiveLevel.MODULE,
            transport=model.transport,
        )

        assert suggestion.text == "Describe the cardiac cycle."
        assert "Your previous answer was rejected: the answer is not JSON" in model.prompts[1]
        assert "hunter2" not in model.prompts[1]
        calls = list(
            await db_session.scalars(select(AIRunCall).where(AIRunCall.run_id == suggestion.run_id))
        )
        assert sorted(bool(c.valid) for c in calls) == [False, True]

    async def test_a_made_up_number_counts_as_unusable(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(lambda prompt: rewrite_json(text="Describe 80% of the cardiac cycle."))
        with pytest.raises(ProviderError, match="could not be used"):
            await ai_objectives.rewrite(
                db_session,
                test_settings,
                actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
                text=WORDING,
                level=ObjectiveLevel.MODULE,
                transport=model.transport,
            )
        assert len(model.requests) == 2
        (run,) = await runs_of(db_session, AIRunType.REWRITE)
        assert run.status is AIRunStatus.FAILED and run.failed_items == 1

    async def test_an_answer_cut_off_twice_is_unusable(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(lambda prompt: '{"text": "Desc', stop_reasons=["max_tokens", "max_tokens"])
        with pytest.raises(ProviderError):
            await ai_objectives.rewrite(
                db_session,
                test_settings,
                actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
                text=WORDING,
                level=ObjectiveLevel.MODULE,
                transport=model.transport,
            )
        assert "cut off because it was too long" in model.prompts[1]

    async def test_a_busy_provider_is_tried_once_more(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(lambda prompt: rewrite_json(), statuses=[429])
        suggestion = await ai_objectives.rewrite(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text=WORDING,
            level=ObjectiveLevel.MODULE,
            transport=model.transport,
        )
        assert len(model.requests) == 2 and suggestion.text

    async def test_a_refused_key_is_not_tried_again(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(statuses=[401, 401])
        with pytest.raises(ProviderError):
            await ai_objectives.rewrite(
                db_session,
                test_settings,
                actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
                text=WORDING,
                level=ObjectiveLevel.MODULE,
                transport=model.transport,
            )
        assert len(model.requests) == 1

    async def test_personal_information_is_never_sent(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model()
        with pytest.raises(PersonalDataRefusedError):
            await ai_objectives.rewrite(
                db_session,
                test_settings,
                actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
                text="Email jane.doe@example.org about the cardiac cycle.",
                level=ObjectiveLevel.MODULE,
                transport=model.transport,
            )
        assert model.requests == []
        # The refusal is recorded (the gateway keeps its own record of it as well).
        runs = await runs_of(db_session, AIRunType.REWRITE)
        assert runs and all(run.status is AIRunStatus.FAILED for run in runs)

    async def test_nothing_is_made_when_ai_is_off(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        with pytest.raises(AIDisabledError):
            await ai_objectives.rewrite(
                db_session,
                test_settings,
                actor_id=world.draft.created_by_id,  # type: ignore[arg-type]
                text=WORDING,
                level=ObjectiveLevel.MODULE,
            )
        assert await runs_of(db_session, AIRunType.REWRITE) == []


class TestClassify:
    async def test_a_domain_and_level_are_suggested(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        name = ready.apply.name
        model = Model(classify_for(name, domain="skill"))

        found = await ai_objectives.classify(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text="Measure blood pressure.",
            level=ObjectiveLevel.LEARNING_EVENT,
            transport=model.transport,
        )

        assert found.domain is ObjectiveDomain.SKILL
        assert found.taxonomy_level_id == ready.apply.id and found.taxonomy_level_name == name
        assert found.scale_name and found.confidence == Decimal("0.8")
        (run,) = await runs_of(db_session, AIRunType.CLASSIFICATION)
        assert run.status is AIRunStatus.SUCCEEDED and run.prompt_version == "classify:2"

    async def test_not_sure_gives_empty_values(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        unsure = json.dumps(
            {"domain": None, "level": None, "confidence": 0.2, "rationale": "Unclear."}
        )
        found = await ai_objectives.classify(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text="Be a good colleague.",
            level=ObjectiveLevel.MODULE,
            transport=Model(lambda prompt: unsure).transport,
        )
        assert found.domain is None and found.taxonomy_level_id is None
        assert found.taxonomy_level_name is None

    async def test_a_level_that_was_not_offered_is_refused_twice(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(classify_for("x", level="L99"))
        with pytest.raises(ProviderError):
            await ai_objectives.classify(
                db_session,
                test_settings,
                actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
                text=WORDING,
                level=ObjectiveLevel.MODULE,
                transport=model.transport,
            )
        assert len(model.requests) == 2
        assert "the level is not one of the keys that were offered" in model.prompts[1]

    async def test_the_prompt_holds_only_the_wording_and_the_levels(
        self, db_session: AsyncSession, test_settings: Settings, ready: World
    ) -> None:
        model = Model(classify_for(ready.apply.name))
        await ai_objectives.classify(
            db_session,
            test_settings,
            actor_id=ready.draft.created_by_id,  # type: ignore[arg-type]
            text=WORDING,
            level=ObjectiveLevel.MODULE,
            transport=model.transport,
        )
        assert objective_of(model.prompts[0]) == WORDING


def install(world_app: Any, model: Model) -> None:
    world_app.dependency_overrides[ai_transport] = lambda: model.transport


class TestApi:
    async def test_requires_sign_in(self, api_client: AsyncClient) -> None:
        for path in (
            "/curriculum-versions/00000000-0000-0000-0000-000000000000/outcome-ai",
            "/modules/00000000-0000-0000-0000-000000000000/outcome-ai",
            "/learning-events/00000000-0000-0000-0000-000000000000/objective-ai",
        ):
            response = await api_client.post(
                f"{API}{path}", json={"task": "rewrite", "text": WORDING}
            )
            assert response.status_code == 401, path

    async def test_a_director_gets_a_rewrite_for_each_kind_of_objective(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        install(api_app, Model(lambda prompt: rewrite_json()))
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        urls = (
            f"/curriculum-versions/{ready.draft.id}/outcome-ai",
            f"/modules/{ready.cardio.id}/outcome-ai",
            f"/learning-events/{ready.lecture.id}/objective-ai",
        )
        for url in urls:
            response = await api_client.post(
                f"{API}{url}", json={"task": "rewrite", "text": WORDING}
            )
            assert response.status_code == 200, url
            body = response.json()
            assert body["task"] == "rewrite" and body["classification"] is None
            assert body["rewrite"] == {
                "text": "Describe the cardiac cycle.",
                "rationale": "Measurable.",
                "unchanged": False,
            }

    async def test_a_director_gets_a_classification(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        install(api_app, Model(classify_for(ready.apply.name)))
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await api_client.post(
            f"{API}/modules/{ready.cardio.id}/outcome-ai",
            json={"task": "classify", "text": WORDING},
        )

        assert response.status_code == 200
        found = response.json()["classification"]
        assert found["domain"] == "knowledge"
        assert found["taxonomy_level_id"] == str(ready.apply.id)

    async def test_a_module_coordinator_may_use_it_for_their_module_only(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        install(api_app, Model(lambda prompt: rewrite_json()))
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, ready.cardio.id),
        )
        body = {"task": "rewrite", "text": WORDING}

        own = await api_client.post(f"{API}/modules/{ready.cardio.id}/outcome-ai", json=body)
        programme = await api_client.post(
            f"{API}/curriculum-versions/{ready.draft.id}/outcome-ai", json=body
        )

        assert own.status_code == 200
        assert programme.status_code == 403

    async def test_an_editor_without_the_ai_permission_is_refused(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        model = Model(lambda prompt: rewrite_json())
        install(api_app, model)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.MODULE, ready.cardio.id),
        )

        response = await api_client.post(
            f"{API}/modules/{ready.cardio.id}/outcome-ai", json={"task": "rewrite", "text": WORDING}
        )

        assert response.status_code == 403
        assert model.requests == []

    async def test_ai_switched_off_is_a_conflict_with_the_reason(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/outcome-ai", json={"task": "rewrite", "text": WORDING}
        )

        assert response.status_code == 409
        assert "switched off" in response.json()["detail"]

    @pytest.mark.parametrize(
        "body", [{"task": "rewrite", "text": "   "}, {"task": "dream", "text": "x"}]
    )
    async def test_a_bad_request_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        body: dict[str, str],
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        response = await api_client.post(f"{API}/modules/{ready.cardio.id}/outcome-ai", json=body)
        assert response.status_code == 422

    async def test_personal_information_is_a_conflict_and_nothing_is_sent(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        model = Model()
        install(api_app, model)
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await api_client.post(
            f"{API}/modules/{ready.cardio.id}/outcome-ai",
            json={"task": "rewrite", "text": "Phone 082 123 4567 about the heart."},
        )

        assert response.status_code == 409 and model.requests == []
        assert "phone" in response.json()["detail"]

    async def test_a_failing_provider_is_a_bad_gateway(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
    ) -> None:
        install(api_app, Model(statuses=[401]))
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )

        response = await api_client.post(
            f"{API}/modules/{ready.cardio.id}/outcome-ai", json={"task": "rewrite", "text": WORDING}
        )

        assert response.status_code == 502

    async def test_too_many_calls_in_a_minute_are_refused(
        self,
        api_client: AsyncClient,
        api_app: Any,
        db_session: AsyncSession,
        test_settings: Settings,
        ready: World,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1 import ai_objectives as router

        monkeypatch.setattr(router, "AI_CALLS_PER_MINUTE", 2)
        install(api_app, Model(lambda prompt: rewrite_json()))
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(ready)
        )
        url = f"{API}/modules/{ready.cardio.id}/outcome-ai"
        body = {"task": "rewrite", "text": WORDING}

        codes = [(await api_client.post(url, json=body)).status_code for _ in range(3)]

        assert codes == [200, 200, 429]
