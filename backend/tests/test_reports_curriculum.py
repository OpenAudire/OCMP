"""Tests for the redundancy and traceability reports (ADR 052)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY
from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import LearningEvent, Objective
from app.models.embedding import ObjectiveSimilarity
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.report_docs_curriculum import unusual_threshold
from tests.factories import LearningEventFactory
from tests.test_coverage_report import Library, accept
from tests.test_coverage_report import library as library  # fixture
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def url(world: World, key: str) -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/reports/{key}"


def section(body: dict, start: str) -> dict:  # type: ignore[type-arg]
    return next(s for s in body["sections"] if s["title"].startswith(start))


async def session_with_objective(
    db: AsyncSession, world: World, module_name: str, title: str, week: int
) -> Objective:
    module = world.cardio if module_name == "cardio" else world.anatomy
    event: LearningEvent = LearningEventFactory(module=module, title=title, week=week)
    db.add(event)
    await db.flush()
    return await add_objective(db, event, f"Objective of {title}.")


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


def test_what_is_unusual_depends_on_how_many_items_there_are_to_compare() -> None:
    assert unusual_threshold([1, 2, 9]) == 4.0  # too few items for an average: the floor
    assert unusual_threshold([1, 1, 1, 1, 10]) == pytest.approx(8.2, abs=0.05)
    assert unusual_threshold([2, 2, 2, 2, 2, 2]) == 4.0  # never below the floor


@pytest.mark.usefixtures("admin")
class TestRedundancy:
    async def test_lists_framework_items_taught_in_unusually_many_sessions(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        for name, title, week in (
            ("cardio", "Heart one", 1),
            ("cardio", "Heart two", 2),
            ("anatomy", "Bones one", 3),
            ("anatomy", "Bones two", 4),
        ):
            objective = await session_with_objective(db_session, world, name, title, week)
            await accept(db_session, objective, library.one)
        three = await session_with_objective(db_session, world, "cardio", "Other", 5)
        await accept(db_session, three, library.two)

        response = await api_client.get(
            url(world, "redundancy"), params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 200
        body = response.json()
        taught = section(body, "Items taught in many sessions")
        [row] = taught["rows"]
        assert row[:5] == ["G1.1", "Skill 1", 4, 2, row[4]]
        assert row[4].startswith("HSC101 Bones one") and "HSC201 Heart two" in row[4]
        assert "at least 4.0 sessions" in taught["note"]
        assert body["method"].startswith("Sessions per framework item")

    async def test_a_few_sessions_is_not_flagged_and_unaccepted_links_do_not_count(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        from app.models.mapping import MappingStatus
        from tests.test_coverage_report import other_status

        for index in range(3):
            objective = await session_with_objective(
                db_session, world, "cardio", f"S{index}", index
            )
            await accept(db_session, objective, library.one)
        fourth = await session_with_objective(db_session, world, "cardio", "S3", 3)
        await other_status(db_session, fourth, library.one, MappingStatus.SUGGESTED)

        body = (
            await api_client.get(
                url(world, "redundancy"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        assert section(body, "Items taught")["rows"] == []

    async def test_near_duplicates_in_different_modules_are_listed_most_similar_first(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        def pair(a: Objective, b: Objective, similarity: float) -> ObjectiveSimilarity:
            first, second = sorted([a.id, b.id])
            return ObjectiveSimilarity(
                objective_id=first,
                other_objective_id=second,
                model_key=MODEL_KEY,
                similarity=similarity,
            )

        same_module = await add_objective(db_session, world.cardio, "Interpret cardiac tests.")
        db_session.add_all(
            [
                pair(world.cardio_outcome, world.anatomy_outcome, 0.97),
                pair(world.cardio_outcome, same_module, 0.99),  # the same module
                pair(world.anatomy_outcome, same_module, 0.90),  # under the 95% default
            ]
        )
        await db_session.flush()

        body = (
            await api_client.get(
                url(world, "redundancy"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        [row] = section(body, "Near-duplicate")["rows"]
        assert row[0] == 0.97
        assert {row[2], row[4]} == {"Interpret cardiac investigations.", "Name the bones."}
        assert {row[1], row[3]} == {"HSC201", "HSC101"}

    async def test_needs_a_framework(self, api_client: AsyncClient, world: World) -> None:
        assert (await api_client.get(url(world, "redundancy"))).status_code == 422


@pytest.mark.usefixtures("admin")
class TestTraceability:
    async def test_follows_the_upward_links_down_to_the_framework_items(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await link_objectives(db_session, world.cardio_outcome, world.programme_outcome)
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.cardio_outcome, library.two)

        body = (
            await api_client.get(
                url(world, "traceability"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        traced = section(body, "From programme outcome")
        rows = {tuple(r[:5]): r[5] for r in traced["rows"]}
        # programme outcome > module outcome > session objective, and the direct link of the
        # session objective to the programme outcome.
        assert (
            rows[
                (
                    "Practise safely.",
                    "Interpret cardiac investigations.",
                    "HSC201",
                    "Describe the cardiac cycle.",
                    "HSC201 Cardiac cycle",
                )
            ]
            == "G1.1"
        )
        assert (
            rows[
                (
                    "Practise safely.",
                    None,
                    None,
                    "Describe the cardiac cycle.",
                    "HSC201 Cardiac cycle",
                )
            ]
            == "G1.1"
        )
        loose = section(body, "Not linked upward")
        assert [r[3] for r in loose["rows"]] == ["Name the bones."]
        assert loose["rows"][0][:3] == ["Module outcome", "HSC101", None]

    async def test_a_programme_outcome_with_nothing_below_it_says_so(
        self, api_client: AsyncClient, world: World
    ) -> None:
        body = (await api_client.get(url(world, "traceability"))).json()

        # In the shared world only the session objective is linked up; two outcomes are loose.
        traced = section(body, "From programme outcome")
        assert len(traced["rows"]) == 1
        loose = section(body, "Not linked upward")
        assert {r[3] for r in loose["rows"]} == {
            "Interpret cardiac investigations.",
            "Name the bones.",
        }

    async def test_without_a_framework_every_framework_is_named(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)

        body = (await api_client.get(url(world, "traceability"))).json()

        assert section(body, "From programme outcome")["rows"][0][5] == "Competencies: G1.1"
        assert {a["label"]: a["value"] for a in body["about"]}["Framework"] == "All frameworks"

    async def test_a_module_coordinator_sees_only_their_part_and_is_told(
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
            ScopeRef(ScopeType.MODULE, world.anatomy.id),
        )

        body = (await api_client.get(url(world, "traceability"))).json()

        assert section(body, "From programme outcome")["rows"] == []
        assert [r[3] for r in section(body, "Not linked upward")["rows"]] == ["Name the bones."]
        about = {a["label"] for a in body["about"]}
        assert "Only part of the curriculum" in about
