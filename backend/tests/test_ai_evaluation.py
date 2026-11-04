"""Tests for the evaluation harness (ADR 048): the run, what it must not touch, and the API."""

import io
import uuid
from typing import Any, ClassVar

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AIRun, EvalRun, GoldCase, GoldSet, MappingLink, Objective
from app.models.mapping import AIRunStatus, AIRunType, MappingStatus
from app.services import ai_mapping, eval_gold, eval_metrics, eval_run
from app.services.authorization import ConflictError, InvalidRequestError
from tests.conftest import EnqueuedJob
from tests.factories import UserFactory
from tests.mapping_helpers import Library, Model, good_answer, make_library, turn_ai_on
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture
from tests.test_mapping_shortlist import link

API = "/api/v1/ai/evaluation"


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_mapping, "RETRY_DELAYS", (0.0, 0.0))


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


@pytest.fixture
async def ready_world(
    db_session: AsyncSession, test_settings: Settings, world: World, library: Library
) -> World:
    await turn_ai_on(db_session, world, test_settings)
    return world


def sheet(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    page = book.active
    assert page is not None
    page.title = "Gold set"
    page.append(list(eval_gold.HEADERS))
    for row in rows:
        page.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# The world's objectives, as a person might have marked them. "Practise safely." shares no word
# with the framework, "Name the bones." maps to nothing, and the last wording is not in the version.
GOLD_ROWS: list[list[Any]] = [
    ["Describe the cardiac cycle.", "HRT1", 4, "matches"],
    ["Interpret cardiac investigations.", "HRT1", 2, "below"],
    ["Practise safely.", "HYG1", 4, "matches"],
    ["Name the bones.", None, None, None],
    ["An objective the version does not have.", "COM1", 3, None],
]


async def make_gold(
    db: AsyncSession, library: Library, rows: list[list[Any]] | None = None
) -> GoldSet:
    parsed = await eval_gold.preview(db, library.framework, sheet(rows or GOLD_ROWS))
    assert parsed.problems == []
    return await eval_gold.save_gold_set(
        db,
        actor_id=None,
        name="Test set",
        description="",
        framework=library.framework,
        parsed=parsed,
    )


async def start(
    db: AsyncSession, settings: Settings, world: World, gold: GoldSet, **kw: Any
) -> tuple[EvalRun, AIRun]:
    user = UserFactory.build()
    db.add(user)
    await db.flush()
    return await eval_run.start_eval(
        db, settings, actor_id=user.id, gold_set=gold, version=world.draft, **kw
    )


class TestStarting:
    async def test_queues_an_evaluation_run_that_is_not_a_mapping_run(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)

        evaluation, run = await start(db_session, test_settings, ready_world, gold, top_k=7)

        assert run.type is AIRunType.EVALUATION and run.status is AIRunStatus.QUEUED
        assert run.total_items == 5 and run.parameters == {"top_k": 7}
        assert run.prompt_version == "mapping:2"
        assert evaluation.gold_set_id == gold.id and evaluation.top_k == 7

    async def test_one_evaluation_of_a_gold_set_at_a_time(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        await start(db_session, test_settings, ready_world, gold)

        with pytest.raises(ConflictError):
            await start(db_session, test_settings, ready_world, gold)

    @pytest.mark.parametrize("k", [2, 21])
    async def test_the_shortlist_size_is_bounded(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
        k: int,
    ) -> None:
        gold = await make_gold(db_session, library)

        with pytest.raises(InvalidRequestError):
            await start(db_session, test_settings, ready_world, gold, top_k=k)


class TestRunning:
    async def run_it(
        self,
        db: AsyncSession,
        settings: Settings,
        world: World,
        gold: GoldSet,
        model: Model,
    ) -> tuple[EvalRun, AIRun]:
        evaluation, run = await start(db, settings, world, gold)
        done = await eval_run.execute_eval(db, settings, evaluation.id, transport=model.transport)
        await db.refresh(run)
        return done, run

    async def test_keeps_the_answers_and_saves_no_link_and_changes_no_objective(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        wording = {
            o.id: (o.text, o.updated_at) for o in await db_session.scalars(select(Objective))
        }

        done, run = await self.run_it(db_session, test_settings, ready_world, gold, Model())

        assert run.status is AIRunStatus.SUCCEEDED
        assert (run.total_items, run.done_items, run.failed_items) == (5, 5, 0)
        assert done.not_found == 1
        assert await db_session.scalar(select(func.count()).select_from(MappingLink)) == 0
        assert {
            o.id: (o.text, o.updated_at) for o in await db_session.scalars(select(Objective))
        } == wording
        by_text = {
            c.objective_text: e
            for e in done.results
            for c in await db_session.scalars(select(GoldCase).where(GoldCase.id == e["case_id"]))
        }
        cycle = by_text["Describe the cardiac cycle."]
        assert cycle["found"] and cycle["shortlist"] == ["HRT1"]
        assert cycle["matches"] == [
            {"code": "HRT1", "coverage": 4, "depth": "matches", "confidence": 0.9}
        ]
        assert by_text["Practise safely."]["shortlist"] == []  # nothing to ask about
        assert by_text["An objective the version does not have."]["found"] is False

    async def test_earlier_decisions_cannot_leak_into_the_measurement(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        # The objective already has an accepted link to the heart item and a rejected one.
        await link(db_session, ready_world.lecture_objective, library.heart, MappingStatus.ACCEPTED)
        await link(
            db_session, ready_world.lecture_objective, library.communication, MappingStatus.REJECTED
        )
        gold = await make_gold(db_session, library)
        model = Model()

        done, _run = await self.run_it(db_session, test_settings, ready_world, gold, model)

        # A mapping run would skip both items; the evaluation still shows the heart item,
        # and the prompt carries no "earlier decisions" examples.
        entry = next(e for e in done.results if e.get("shortlist") == ["HRT1"])
        assert entry["matches"][0]["code"] == "HRT1"
        assert all("Earlier decisions" not in prompt for prompt in model.prompts)

    async def test_the_figures_come_from_the_stored_answers(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        done, _run = await self.run_it(db_session, test_settings, ready_world, gold, Model())

        cases = await eval_run.case_results(db_session, done)
        result = eval_metrics.score(cases)

        # Four found objectives. Two have the heart item suggested and in the gold set; "Practise
        # safely." was never shown anything (a miss); "Name the bones." maps to nothing.
        assert result.objectives == 4
        assert (result.counts.tp, result.counts.fp, result.counts.fn) == (2, 0, 1)
        assert result.precision == 1.0 and result.recall == pytest.approx(2 / 3)
        assert result.shortlist_recall == pytest.approx(2 / 3)

    async def test_a_provider_that_fails_every_time_ends_the_run_failed(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        model = Model(statuses=[401] * 10)

        done, run = await self.run_it(db_session, test_settings, ready_world, gold, model)

        assert run.status is AIRunStatus.FAILED and run.failed_items >= 1
        failed = [e for e in done.results if e.get("failed")]
        assert failed and all(not e.get("matches") for e in failed)
        figures = eval_metrics.score(await eval_run.case_results(db_session, done))
        assert figures.failed == 2  # left out of the figures, not counted as wrong answers
        assert figures.counts.fp == 0

    async def test_an_unusable_answer_counts_as_failed_and_is_left_out_of_the_figures(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        model = Model(answer=lambda _prompt: "not json")

        done, run = await self.run_it(db_session, test_settings, ready_world, gold, model)

        assert run.failed_items == 2  # the two objectives that had something to ask about
        result = eval_metrics.score(await eval_run.case_results(db_session, done))
        assert result.failed == 2 and result.objectives == 2

    async def test_a_cancelled_run_stops(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        evaluation, run = await start(db_session, test_settings, ready_world, gold)
        await ai_mapping.cancel_run(db_session, run)

        with pytest.raises(InvalidRequestError):
            await eval_run.execute_eval(db_session, test_settings, evaluation.id)

    async def test_two_prompts_can_be_compared_on_the_same_gold_set(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        careless = Model(answer=lambda p: good_answer(p, matches=0))
        first, _ = await self.run_it(db_session, test_settings, ready_world, gold, Model())
        second, _ = await self.run_it(db_session, test_settings, ready_world, gold, careless)

        a = eval_metrics.score(await eval_run.case_results(db_session, first))
        b = eval_metrics.score(await eval_run.case_results(db_session, second))

        assert a.recall == pytest.approx(2 / 3) and b.recall == 0.0
        assert a.f1 is not None and a.f1 > 0 and b.f1 is None


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, system_roles: None
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


class TestAccess:
    ENDPOINTS: ClassVar[list[tuple[str, str]]] = [
        ("GET", "/gold-template"),
        ("GET", "/gold-sets"),
        ("POST", "/gold-sets"),
        ("GET", f"/gold-sets/{uuid.uuid4()}/export"),
        ("DELETE", f"/gold-sets/{uuid.uuid4()}"),
        ("POST", "/runs"),
        ("GET", "/runs"),
        ("GET", f"/runs/{uuid.uuid4()}"),
        ("POST", f"/runs/{uuid.uuid4()}/cancel"),
    ]

    @pytest.mark.parametrize(("method", "path"), ENDPOINTS)
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}")

        assert response.status_code == 401

    @pytest.mark.parametrize(("method", "path"), ENDPOINTS)
    @pytest.mark.parametrize("role", [None, "student"])
    async def test_needs_settings_manage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
        method: str,
        path: str,
        role: str | None,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, role)

        response = await api_client.request(method, f"{API}{path}")

        assert response.status_code == 403


def form(library: Library, **extra: str) -> dict[str, str]:
    return {"name": "Hand-made", "framework_id": str(library.framework.id), **extra}


def upload(content: bytes) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("anything.xlsx", content, eval_gold_xlsx())}


def eval_gold_xlsx() -> str:
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.usefixtures("admin")
class TestGoldSets:
    async def test_the_template_downloads_as_a_workbook(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        response = await api_client.get(
            f"{API}/gold-template", params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == eval_gold_xlsx()
        assert "Framework items" in load_workbook(io.BytesIO(response.content)).sheetnames

    async def test_a_dry_run_reports_counts_and_every_problem_and_saves_nothing(
        self, api_client: AsyncClient, db_session: AsyncSession, library: Library
    ) -> None:
        content = sheet([["A.", "HRT1", 4, None], ["B.", "NOPE", 3, None], ["C.", "COM1", 9, None]])

        response = await api_client.post(
            f"{API}/gold-sets", data=form(library, dry_run="true"), files=upload(content)
        )

        assert response.status_code == 200
        body = response.json()
        assert [p["row"] for p in body["problems"]] == [3, 4]
        assert "framework has no item" in body["problems"][0]["message"]
        assert "whole number" in body["problems"][1]["message"]
        assert body["saved"] is None
        assert await db_session.scalar(select(func.count()).select_from(GoldSet)) == 0

    async def test_a_sound_file_is_saved_and_listed(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        response = await api_client.post(
            f"{API}/gold-sets", data=form(library), files=upload(sheet(GOLD_ROWS))
        )

        assert response.status_code == 201
        saved = response.json()["saved"]
        assert (saved["objectives"], saved["mappings"], saved["without_mapping"]) == (5, 4, 1)
        assert saved["framework_name"] == "Graduate competencies" and saved["is_demo"] is False
        listed = (await api_client.get(f"{API}/gold-sets")).json()
        assert [g["name"] for g in listed] == ["Hand-made"]

    async def test_a_file_with_problems_is_refused_with_the_list(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        response = await api_client.post(
            f"{API}/gold-sets", data=form(library), files=upload(sheet([["A.", "HRT1", 9, None]]))
        )

        assert response.status_code == 422
        assert response.json()["problems"][0]["row"] == 2
        assert (await api_client.get(f"{API}/gold-sets")).json() == []

    async def test_a_repeated_name_is_a_conflict(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        files = upload(sheet(GOLD_ROWS))
        await api_client.post(f"{API}/gold-sets", data=form(library), files=files)

        again = await api_client.post(f"{API}/gold-sets", data=form(library), files=files)

        assert again.status_code == 409

    async def test_an_unknown_framework_is_not_found(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        data = {"name": "X", "framework_id": str(uuid.uuid4())}

        response = await api_client.post(
            f"{API}/gold-sets", data=data, files=upload(sheet(GOLD_ROWS))
        )

        assert response.status_code == 404

    async def test_an_export_is_a_workbook_that_can_be_imported_again(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        saved = (
            await api_client.post(
                f"{API}/gold-sets", data=form(library), files=upload(sheet(GOLD_ROWS))
            )
        ).json()["saved"]

        export = await api_client.get(f"{API}/gold-sets/{saved['id']}/export")

        assert export.status_code == 200
        again = await api_client.post(
            f"{API}/gold-sets",
            data=form(library, name="Copy", dry_run="true"),
            files=upload(export.content),
        )
        assert again.json()["problems"] == [] and again.json()["objectives"] == 5

    async def test_a_deleted_gold_set_leaves_the_list_and_frees_its_name(
        self, api_client: AsyncClient, library: Library
    ) -> None:
        saved = (
            await api_client.post(
                f"{API}/gold-sets", data=form(library), files=upload(sheet(GOLD_ROWS))
            )
        ).json()["saved"]

        assert (await api_client.delete(f"{API}/gold-sets/{saved['id']}")).status_code == 204

        assert (await api_client.get(f"{API}/gold-sets")).json() == []
        again = await api_client.post(
            f"{API}/gold-sets", data=form(library), files=upload(sheet(GOLD_ROWS))
        )
        assert again.status_code == 201


@pytest.mark.usefixtures("admin")
class TestRunsApi:
    async def test_starting_queues_the_job_and_reports_progress(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        enqueued_jobs: list[EnqueuedJob],
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)

        response = await api_client.post(
            f"{API}/runs",
            json={"gold_set_id": str(gold.id), "version_id": str(ready_world.draft.id)},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued" and body["total_items"] == 5
        assert body["prompt_version"] == "mapping:2"
        assert [(j.actor, j.args) for j in enqueued_jobs] == [("run_evaluation", (body["id"],))]

    async def test_a_second_start_while_one_is_going_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        payload = {"gold_set_id": str(gold.id), "version_id": str(ready_world.draft.id)}
        await api_client.post(f"{API}/runs", json=payload)

        again = await api_client.post(f"{API}/runs", json=payload)

        assert again.status_code == 409

    async def test_ai_must_be_on(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)

        response = await api_client.post(
            f"{API}/runs", json={"gold_set_id": str(gold.id), "version_id": str(world.draft.id)}
        )

        assert response.status_code == 409

    async def test_unknown_gold_set_or_version_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)

        no_gold = await api_client.post(
            f"{API}/runs",
            json={"gold_set_id": str(uuid.uuid4()), "version_id": str(ready_world.draft.id)},
        )
        no_version = await api_client.post(
            f"{API}/runs", json={"gold_set_id": str(gold.id), "version_id": str(uuid.uuid4())}
        )

        assert no_gold.status_code == 404 and no_version.status_code == 404

    async def test_the_detail_has_the_sweeps_and_the_disagreements(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        evaluation, _ = await start(db_session, test_settings, ready_world, gold)
        await eval_run.execute_eval(
            db_session, test_settings, evaluation.id, transport=Model().transport
        )

        response = await api_client.get(f"{API}/runs/{evaluation.id}", params={"min_coverage": 3})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "succeeded" and body["not_found"] == 1
        assert body["min_coverage"] == 3 and body["prefer_specific"] is True
        assert body["scores"]["objectives"] == 4
        assert [row["min_coverage"] for row in body["by_min_coverage"]] == [1, 2, 3, 4, 5]
        assert [row["floor"] for row in body["bulk_accept"]][:2] == [50, 60]
        # "Practise safely." is the only objective the AI and the gold set disagree about.
        assert [d["objective"] for d in body["disagreements"]] == ["Practise safely."]
        assert body["disagreements"][0]["not_shown"] == ["HYG1"]

    async def test_the_list_compares_runs_at_the_chosen_minimum_coverage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        first, _ = await start(db_session, test_settings, ready_world, gold)
        await eval_run.execute_eval(
            db_session, test_settings, first.id, transport=Model().transport
        )

        rows = (await api_client.get(f"{API}/runs", params={"gold_set_id": str(gold.id)})).json()
        high = (
            await api_client.get(
                f"{API}/runs", params={"gold_set_id": str(gold.id), "min_coverage": 5}
            )
        ).json()

        assert len(rows) == 1 and rows[0]["prompt_version"] == "mapping:2"
        assert rows[0]["model"] and rows[0]["gold_set_name"] == "Test set"
        assert rows[0]["scores"]["suggestions"] == 2
        assert high[0]["scores"]["suggestions"] == 0  # the mock answers with coverage 4

    async def test_an_unknown_run_is_not_found(self, api_client: AsyncClient) -> None:
        assert (await api_client.get(f"{API}/runs/{uuid.uuid4()}")).status_code == 404

    async def test_a_run_can_be_cancelled(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        ready_world: World,
        library: Library,
    ) -> None:
        gold = await make_gold(db_session, library)
        evaluation, _ = await start(db_session, test_settings, ready_world, gold)

        response = await api_client.post(f"{API}/runs/{evaluation.id}/cancel")

        assert response.status_code == 200 and response.json()["status"] == "cancelled"
