"""Tests for near-duplicate objectives: the stored pairs, the card endpoint and the bulk check."""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MODEL_KEY
from app.core.config import Settings, get_settings
from app.core.permissions import ScopeType
from app.models import Faculty, Institution, Objective
from app.models.curriculum import ObjectiveStatus
from app.models.embedding import EmbeddedType, Embedding, ObjectiveSimilarity
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum import add_objective
from app.services.objective_duplicates import pairs_among, refresh_similarities
from app.services.policies import (
    NEAR_DUPLICATE_DEFAULT_PERCENT,
    NEAR_DUPLICATE_FLOOR_PERCENT,
    parse_quality_policy,
)
from tests.fakes import angled
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World, programme_scope
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


async def embed(db: AsyncSession, objective: Objective, degrees: float) -> None:
    """Give an objective a vector at an angle (the cosine to angle 0 is cos(degrees))."""
    db.add(
        Embedding(
            entity_type=EmbeddedType.OBJECTIVE,
            entity_id=objective.id,
            model_key=MODEL_KEY,
            text_hash="test",
            vector=angled(degrees),
        )
    )
    await db.flush()


async def pairs(db: AsyncSession) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    rows = await db.scalars(select(ObjectiveSimilarity))
    return [(r.objective_id, r.other_objective_id, r.similarity) for r in rows]


@pytest.fixture
async def twins(db_session: AsyncSession, world: World) -> tuple[Objective, Objective, Objective]:
    """Three session objectives of the draft: a lecture one, a lab one 10 degrees away
    (98.5% similar), and an anatomy one 60 degrees away (50%)."""
    lab = await add_objective(db_session, world.lab, "Outline the cardiac cycle.")
    bones = await add_objective(db_session, world.anatomy_session, "Name the long bones.")
    await embed(db_session, world.lecture_objective, 0)
    await embed(db_session, lab, 10)
    await embed(db_session, bones, 60)
    return world.lecture_objective, lab, bones


class TestRefresh:
    async def test_a_close_pair_is_stored_once_smaller_id_first(
        self, db_session: AsyncSession, twins: tuple[Objective, Objective, Objective]
    ) -> None:
        lecture, lab, _ = twins

        stored = await refresh_similarities(db_session, lecture.id)

        assert stored == 1
        [(first, second, similarity)] = await pairs(db_session)
        assert (first, second) == tuple(sorted([lecture.id, lab.id]))
        assert similarity == pytest.approx(0.9848, abs=1e-3)

    async def test_pairs_below_the_floor_are_not_kept(
        self, db_session: AsyncSession, twins: tuple[Objective, Objective, Objective]
    ) -> None:
        lecture, _, bones = twins

        await refresh_similarities(db_session, lecture.id)

        assert all(bones.id not in (a, b) for a, b, _ in await pairs(db_session))
        assert NEAR_DUPLICATE_FLOOR_PERCENT > 50

    async def test_only_objectives_of_the_same_version_and_level_are_compared(
        self, db_session: AsyncSession, world: World
    ) -> None:
        # Same vector, but a module outcome (another level) and the published version's
        # outcome (another version): neither is a near-duplicate of the draft's programme outcome.
        await embed(db_session, world.programme_outcome, 0)
        await embed(db_session, world.cardio_outcome, 0)
        await embed(db_session, world.published_outcome, 0)

        stored = await refresh_similarities(db_session, world.programme_outcome.id)

        assert stored == 0

    async def test_refreshing_replaces_the_pairs_an_objective_was_in(
        self, db_session: AsyncSession, twins: tuple[Objective, Objective, Objective]
    ) -> None:
        lecture, lab, _ = twins
        await refresh_similarities(db_session, lecture.id)
        vector = await db_session.scalar(select(Embedding).where(Embedding.entity_id == lab.id))
        assert vector is not None
        vector.vector = angled(120)  # far from both the lecture (0) and the bones (60)
        await db_session.flush()

        # The lab objective changed: its refresh drops the pair it was in.
        stored = await refresh_similarities(db_session, lab.id)

        assert stored == 0
        assert await pairs(db_session) == []

    async def test_deleted_and_retired_objectives_have_no_pairs(
        self, db_session: AsyncSession, twins: tuple[Objective, Objective, Objective]
    ) -> None:
        lecture, lab, _ = twins
        await refresh_similarities(db_session, lecture.id)
        assert len(await pairs(db_session)) == 1

        lab.soft_delete()
        await db_session.flush()
        assert await refresh_similarities(db_session, lab.id) == 0
        assert await pairs(db_session) == []

        lab.restore()
        lab.status = ObjectiveStatus.RETIRED
        await db_session.flush()
        assert await refresh_similarities(db_session, lecture.id) == 0

    async def test_an_objective_without_a_vector_gets_no_pairs_and_no_error(
        self, db_session: AsyncSession, world: World
    ) -> None:
        assert await refresh_similarities(db_session, world.lecture_objective.id) == 0

    async def test_an_unknown_objective_is_ignored(self, db_session: AsyncSession) -> None:
        assert await refresh_similarities(db_session, uuid.uuid4()) == 0


class TestPairsAmong:
    async def test_threshold_and_membership(
        self, db_session: AsyncSession, twins: tuple[Objective, Objective, Objective]
    ) -> None:
        lecture, lab, bones = twins
        await refresh_similarities(db_session, lecture.id)

        assert len(await pairs_among(db_session, [lecture.id, lab.id], 95)) == 1
        assert await pairs_among(db_session, [lecture.id, lab.id], 99) == []
        # Both sides must be in the list.
        assert await pairs_among(db_session, [lecture.id, bones.id], 85) == []
        assert await pairs_among(db_session, [lecture.id], 85) == []


class TestPolicy:
    def test_the_default_comes_from_the_measurements(self) -> None:
        policy = parse_quality_policy({})

        assert policy.near_duplicate_min_percent == NEAR_DUPLICATE_DEFAULT_PERCENT == 95

    def test_values_below_the_floor_or_above_100_are_refused(self) -> None:
        for bad in (NEAR_DUPLICATE_FLOOR_PERCENT - 1, 101):
            with pytest.raises(Exception, match="quality"):
                parse_quality_policy({"quality": {"near_duplicate_min_percent": bad}})


@pytest.fixture
def embeddings_on(api_app: FastAPI, test_settings: Settings) -> Settings:
    settings = test_settings.model_copy(update={"embeddings_local": True})
    api_app.dependency_overrides[get_settings] = lambda: settings
    return settings


async def as_director(
    client: AsyncClient, db: AsyncSession, settings: Settings, world: World
) -> None:
    await sign_in(client, db, settings, "programme_director", programme_scope(world))


class TestCardEndpoint:
    async def test_reports_off_while_embeddings_are_off(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        await refresh_similarities(db_session, twins[0].id)
        await as_director(api_client, db_session, test_settings, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/near-duplicates"
        )

        assert response.status_code == 200
        assert response.json() == {
            "version_id": str(world.draft.id),
            "enabled": False,
            "threshold_percent": 95,
            "objectives": [],
        }

    async def test_lists_each_side_of_a_pair_with_where_the_other_is(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        lecture, lab, _ = twins
        await refresh_similarities(db_session, lecture.id)
        await as_director(api_client, db_session, embeddings_on, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/near-duplicates"
        )

        body = response.json()
        assert body["enabled"] is True
        by_id = {o["objective_id"]: o["matches"] for o in body["objectives"]}
        assert set(by_id) == {str(lecture.id), str(lab.id)}
        [match] = by_id[str(lecture.id)]
        assert match["objective_id"] == str(lab.id)
        assert match["percent"] == 98
        assert match["text"] == "Outline the cardiac cycle."
        assert match["module_code"] == "HSC201"
        assert match["event_title"] == "Skills lab"

    async def test_the_institutions_threshold_decides_what_is_listed(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        lecture, lab, _ = twins
        vector = await db_session.scalar(select(Embedding).where(Embedding.entity_id == lab.id))
        assert vector is not None
        vector.vector = angled(20)  # cosine 0.940: 94%
        await db_session.flush()
        await refresh_similarities(db_session, lecture.id)
        await as_director(api_client, db_session, embeddings_on, world)
        url = f"{API}/curriculum-versions/{world.draft.id}/near-duplicates"

        assert (await api_client.get(url)).json()["objectives"] == []

        faculty = await db_session.get(Faculty, world.programme.faculty_id)
        assert faculty is not None
        institution = await db_session.get(Institution, faculty.institution_id)
        assert institution is not None
        institution.settings = {"quality": {"near_duplicate_min_percent": 90}}
        await db_session.flush()
        body = (await api_client.get(url)).json()
        assert body["threshold_percent"] == 90
        assert len(body["objectives"]) == 2

    async def test_a_pair_is_hidden_from_someone_who_sees_only_one_side(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        lecture, _, _ = twins
        await refresh_similarities(db_session, lecture.id)
        # A lecturer of the lab session sees the lab objective but not the lecture's.
        await sign_in(
            api_client,
            db_session,
            embeddings_on,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id),
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/near-duplicates"
        )

        assert response.status_code == 200
        assert response.json()["objectives"] == []

    async def test_people_without_edit_rights_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, embeddings_on, "student", INSTANCE)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/near-duplicates"
        )

        assert response.status_code == 403

    async def test_requires_sign_in_and_a_known_version(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
    ) -> None:
        url = f"{API}/curriculum-versions/{uuid.uuid4()}/near-duplicates"
        assert (await api_client.get(url)).status_code == 401

        await as_director(api_client, db_session, embeddings_on, world)

        assert (await api_client.get(url)).status_code == 404


class TestBulkCheck:
    @staticmethod
    def codes(body: dict, text: str) -> dict[str, dict]:  # type: ignore[type-arg]
        row = next(r for r in body["objectives"] if r["text"] == text)
        return {f["code"]: f for f in row["findings"]}

    async def test_reports_the_pair_as_an_info_finding_when_embeddings_are_on(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        embeddings_on: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        await refresh_similarities(db_session, twins[0].id)
        await as_director(api_client, db_session, embeddings_on, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        body = response.json()
        assert body["near_duplicates_checked"] is True
        finding = self.codes(body, "Describe the cardiac cycle.")["near_duplicate"]
        assert finding["severity"] == "info"
        assert finding["message_key"] == "curriculum.quality.near_duplicate.message"
        assert finding["params"] == {"percent": "98", "where": "HSC201 Skills lab"}
        row = next(r for r in body["objectives"] if r["text"] == "Describe the cardiac cycle.")
        assert row["near_duplicates"][0]["text"] == "Outline the cardiac cycle."
        assert "near_duplicate" not in self.codes(body, "Name the long bones.")

    async def test_reports_nothing_about_duplicates_while_embeddings_are_off(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        twins: tuple[Objective, Objective, Objective],
    ) -> None:
        await refresh_similarities(db_session, twins[0].id)
        await as_director(api_client, db_session, test_settings, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        assert response.json()["near_duplicates_checked"] is False
        assert all(
            "near_duplicate" not in [f["code"] for f in row["findings"]]
            for row in response.json()["objectives"]
        )

    async def test_lists_wording_the_privacy_detectors_flag_without_repeating_it(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        flagged = await add_objective(
            db_session, world.lab, "Phone the patient on 082 123 4567 after the lab."
        )
        await db_session.flush()
        await as_director(api_client, db_session, test_settings, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/objective-checks"
        )

        finding = self.codes(response.json(), flagged.text)["possible_personal_information"]
        assert finding["severity"] == "warning"
        assert finding["params"] == {"kinds": "phone"}
        assert "082" not in str(finding)
        # Ordinary curriculum text is not flagged.
        assert all(
            "possible_personal_information" not in [f["code"] for f in row["findings"]]
            for row in response.json()["objectives"]
            if row["text"] != flagged.text
        )
