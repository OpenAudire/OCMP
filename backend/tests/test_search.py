"""Tests for searching a version and "Where do we teach X?" (ADR 049)."""

import uuid

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import Objective, User
from app.models.curriculum import ObjectiveDomain, ObjectiveStatus
from app.models.embedding import EmbeddedType
from app.models.mapping import MappingStatus
from app.services import search
from app.services.authorization import INSTANCE, ScopeRef
from app.services.curriculum_read import VisibleVersion, curriculum_access, visible_version
from app.services.retrieval import Mode, Notice
from app.services.search import Filters, Kind, Words
from tests.authz_helpers import grant
from tests.factories import UserFactory
from tests.mapping_helpers import Library, make_library
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture
from tests.test_mapping_shortlist import AtAngle, link, vector

API = "/api/v1"


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    return await make_library(db_session)


async def see(db: AsyncSession, world: World, role: str = "platform_admin") -> VisibleVersion:
    user = UserFactory.build()
    db.add(user)
    await db.flush()
    await grant(db, user, role, INSTANCE)
    visible = await visible_version(db, await curriculum_access(db, user), world.draft.id)
    assert visible is not None
    return visible


def texts(result: search.SearchResult, kind: Kind) -> list[str]:
    return [h.title for h in result.hits.get(kind, [])]


class TestWords:
    @pytest.fixture(autouse=True)
    async def _roles(self, system_roles: None) -> None:
        return None

    async def test_finds_objectives_sessions_and_modules_by_their_words(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        visible = await see(db_session, world)

        found = await search.search(db_session, test_settings, visible, "cardiac")

        assert set(texts(found, Kind.OBJECTIVE)) == {
            "Describe the cardiac cycle.",
            "Interpret cardiac investigations.",
        }
        assert texts(found, Kind.EVENT) == ["Cardiac cycle"]
        # The cardiology module has an outcome that matches, so the module is found through it.
        [module] = found.hits[Kind.MODULE]
        assert module.module_code == "HSC201" and module.matched_by == ("objective",)
        assert found.words is Words.ALL and found.mode is Mode.KEYWORD
        assert found.notice is Notice.EMBEDDINGS_OFF

    async def test_the_session_shows_where_an_objective_is_taught(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        visible = await see(db_session, world)

        found = await search.search(db_session, test_settings, visible, "cardiac cycle")

        [objective] = found.hits[Kind.OBJECTIVE]
        assert objective.title == "Describe the cardiac cycle."
        assert (objective.module_code, objective.event_title) == ("HSC201", "Cardiac cycle")
        # The session matches by its own title and through its objective.
        [event] = found.hits[Kind.EVENT]
        assert set(event.matched_by) == {"words", "objective"}

    async def test_a_prefix_finds_the_longer_word(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.search(
            db_session, test_settings, await see(db_session, world), "cardi"
        )

        assert "Describe the cardiac cycle." in texts(found, Kind.OBJECTIVE)

    async def test_when_no_result_has_every_word_results_with_some_are_shown_and_said_so(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.search(
            db_session, test_settings, await see(db_session, world), "cardiac bones"
        )

        assert found.words is Words.SOME
        assert {"Name the bones.", "Describe the cardiac cycle."} <= set(
            texts(found, Kind.OBJECTIVE)
        )

    async def test_nothing_found_is_an_empty_answer(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.search(
            db_session, test_settings, await see(db_session, world), "zebra"
        )

        assert found.words is Words.NONE
        assert all(hits == [] for hits in found.hits.values())

    @pytest.mark.parametrize("query", ["", " ", "a"])
    async def test_a_query_that_is_too_short_is_refused(
        self, db_session: AsyncSession, test_settings: Settings, world: World, query: str
    ) -> None:
        from app.services.authorization import InvalidRequestError

        with pytest.raises(InvalidRequestError):
            await search.search(db_session, test_settings, await see(db_session, world), query)

    async def test_a_query_that_is_too_long_is_refused(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        from app.services.authorization import InvalidRequestError

        with pytest.raises(InvalidRequestError):
            await search.search(db_session, test_settings, await see(db_session, world), "x" * 201)

    @pytest.mark.parametrize(
        "query", ["cardiac & !(bones", "cardiac | | )", "'; drop table objectives; --", "ca:*rdiac"]
    )
    async def test_query_syntax_is_just_words(
        self, db_session: AsyncSession, test_settings: Settings, world: World, query: str
    ) -> None:
        found = await search.search(db_session, test_settings, await see(db_session, world), query)

        assert isinstance(found.hits, dict)  # no database error

    def test_the_query_is_reduced_to_words_before_it_reaches_the_database(self) -> None:
        assert search.query_words("ECG: Interpret (12-lead) ECG!") == [
            "ecg",
            "interpret",
            "12",
            "lead",
        ]
        assert search.tsquery(["cardiac", "cyc"], every=True) == "cardiac & cyc:*"
        assert search.tsquery(["cardiac", "bones"], every=False) == "cardiac | bones:*"
        assert search.tsquery([], every=True) is None
        # Function words are left out, unless nothing else is left.
        assert search.query_words("Where do we teach the heart?") == ["teach", "heart"]
        assert search.query_words("How is it?") == ["how", "is", "it"]

    async def test_retired_deleted_and_other_versions_are_not_searched(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        world.anatomy_outcome.status = ObjectiveStatus.RETIRED
        world.programme_outcome.soft_delete()
        await db_session.flush()
        visible = await see(db_session, world)

        bones = await search.search(db_session, test_settings, visible, "bones")
        safely = await search.search(db_session, test_settings, visible, "practise safely")
        published = await search.search(db_session, test_settings, visible, "published")

        assert texts(bones, Kind.OBJECTIVE) == []
        assert texts(safely, Kind.OBJECTIVE) == []
        assert texts(published, Kind.OBJECTIVE) == []


class TestFilters:
    @pytest.fixture(autouse=True)
    async def _roles(self, system_roles: None) -> None:
        return None

    async def test_a_module_filter_limits_everything_to_that_module(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        visible = await see(db_session, world)

        found = await search.search(
            db_session,
            test_settings,
            visible,
            "the",
            filters=Filters(module_id=world.anatomy.id),
            mode="words",
        )

        # "the" matches "Describe the cardiac cycle." (cardio) and "Name the bones." (anatomy).
        assert texts(found, Kind.OBJECTIVE) == ["Name the bones."]

    async def test_programme_outcomes_have_no_module_so_a_module_filter_leaves_them_out(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        visible = await see(db_session, world)

        everywhere = await search.search(db_session, test_settings, visible, "practise safely")
        in_module = await search.search(
            db_session,
            test_settings,
            visible,
            "practise safely",
            filters=Filters(module_id=world.cardio.id),
        )

        assert texts(everywhere, Kind.OBJECTIVE) == ["Practise safely."]
        assert texts(in_module, Kind.OBJECTIVE) == []

    async def test_a_domain_filter_leaves_out_what_has_no_domain_and_says_which_kinds(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        world.lecture_objective.domain = ObjectiveDomain.KNOWLEDGE
        await db_session.flush()

        found = await search.search(
            db_session,
            test_settings,
            await see(db_session, world),
            "cardiac",
            filters=Filters(domain=ObjectiveDomain.KNOWLEDGE),
        )

        assert texts(found, Kind.OBJECTIVE) == ["Describe the cardiac cycle."]
        assert set(found.left_out) == {Kind.EVENT, Kind.MODULE, Kind.FRAMEWORK_ITEM}
        assert Kind.EVENT not in found.hits

    async def test_a_taxonomy_level_filter(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        world.cardio_outcome.taxonomy_level_id = world.apply.id
        await db_session.flush()

        found = await search.search(
            db_session,
            test_settings,
            await see(db_session, world),
            "cardiac",
            filters=Filters(taxonomy_level_id=world.apply.id),
        )

        assert texts(found, Kind.OBJECTIVE) == ["Interpret cardiac investigations."]

    async def test_kinds_can_be_chosen(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.search(
            db_session,
            test_settings,
            await see(db_session, world),
            "cardiac",
            kinds=frozenset({Kind.EVENT}),
        )

        assert list(found.hits) == [Kind.EVENT]

    async def test_the_limit_is_applied_and_more_is_reported(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.search(
            db_session, test_settings, await see(db_session, world), "cardiac", limit=1
        )

        assert len(found.hits[Kind.OBJECTIVE]) == 1 and found.more[Kind.OBJECTIVE] is True


class TestFrameworkItems:
    @pytest.fixture(autouse=True)
    async def _roles(self, system_roles: None) -> None:
        return None

    async def test_finds_framework_items_by_code_title_and_description(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        visible = await see(db_session, world)

        by_title = await search.search(db_session, test_settings, visible, "hand hygiene")
        by_code = await search.search(db_session, test_settings, visible, "ETH1")

        [item] = by_title.hits[Kind.FRAMEWORK_ITEM]
        assert (item.code, item.framework_name) == ("HYG1", "Graduate competencies")
        assert [h.code for h in by_code.hits[Kind.FRAMEWORK_ITEM]] == ["ETH1"]

    async def test_a_framework_filter_keeps_only_objectives_linked_to_it(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        await link(db_session, world.lecture_objective, library.heart, MappingStatus.ACCEPTED)
        await link(db_session, world.cardio_outcome, library.heart, MappingStatus.REJECTED)

        found = await search.search(
            db_session,
            test_settings,
            await see(db_session, world),
            "cardiac",
            filters=Filters(framework_id=library.framework.id),
        )

        assert texts(found, Kind.OBJECTIVE) == ["Describe the cardiac cycle."]
        assert set(found.left_out) == {Kind.EVENT, Kind.MODULE}

    async def test_people_who_may_not_read_the_library_get_no_framework_items(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        found = await search.search(
            db_session,
            test_settings,
            await see(db_session, world),
            "hygiene",
            frameworks_allowed=False,
        )

        assert Kind.FRAMEWORK_ITEM not in found.hits


class TestMeaning:
    @pytest.fixture(autouse=True)
    async def _roles(self, system_roles: None) -> None:
        return None

    @pytest.fixture
    def on(self, test_settings: Settings) -> Settings:
        return test_settings.model_copy(update={"embeddings_local": True})

    async def test_meaning_finds_what_the_words_do_not(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
        library: Library,
    ) -> None:
        await redis_client.set("embeddings:ready", "1", ex=30)
        # The query is at 0 degrees. The bones objective is close in meaning and shares no word
        # with "heart rhythm"; the programme outcome is far away.
        await vector(db_session, EmbeddedType.OBJECTIVE, world.anatomy_outcome, 5)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.programme_outcome, 80)
        await vector(db_session, EmbeddedType.FRAMEWORK_ITEM, library.heart, 3)

        found = await search.search(
            db_session,
            on,
            await see(db_session, world),
            "heart rhythm",
            redis=redis_client,
            embedder=AtAngle(0),
        )

        assert found.mode is Mode.MEANING and found.notice is None
        [bones] = found.hits[Kind.OBJECTIVE]
        assert (bones.title, bones.matched_by) == ("Name the bones.", ("meaning",))
        assert [h.code for h in found.hits[Kind.FRAMEWORK_ITEM]] == ["HRT1"]
        # Meaning reaches the module through its outcome.
        assert [m.module_code for m in found.hits[Kind.MODULE]] == ["HSC101"]

    async def test_words_and_meaning_agreeing_rank_first(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
    ) -> None:
        await redis_client.set("embeddings:ready", "1", ex=30)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.lecture_objective, 4)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.cardio_outcome, 40)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.anatomy_outcome, 6)

        found = await search.search(
            db_session,
            on,
            await see(db_session, world),
            "cardiac",
            redis=redis_client,
            embedder=AtAngle(0),
        )

        ranked = found.hits[Kind.OBJECTIVE]
        assert ranked[0].title == "Describe the cardiac cycle."
        assert set(ranked[0].matched_by) == {"words", "meaning"}
        assert ranked[0].score > ranked[1].score

    async def test_words_only_mode_ignores_the_vectors(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
    ) -> None:
        await redis_client.set("embeddings:ready", "1", ex=30)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.anatomy_outcome, 5)

        found = await search.search(
            db_session,
            on,
            await see(db_session, world),
            "heart rhythm",
            mode="words",
            redis=redis_client,
            embedder=AtAngle(0),
        )

        assert found.mode is Mode.KEYWORD and found.hits[Kind.OBJECTIVE] == []

    async def test_a_server_that_is_not_answering_is_said_and_words_still_work(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
    ) -> None:
        await redis_client.set("embeddings:ready", "0", ex=30)

        found = await search.search(
            db_session, on, await see(db_session, world), "cardiac", redis=redis_client
        )

        assert found.notice is Notice.EMBEDDINGS_UNREACHABLE
        assert texts(found, Kind.EVENT) == ["Cardiac cycle"]

    async def test_a_server_with_nothing_embedded_yet_is_said(
        self,
        db_session: AsyncSession,
        on: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
    ) -> None:
        await redis_client.set("embeddings:ready", "1", ex=30)

        found = await search.search(
            db_session,
            on,
            await see(db_session, world),
            "cardiac",
            redis=redis_client,
            embedder=AtAngle(0),
        )

        assert found.notice is Notice.NOT_EMBEDDED_YET and found.mode is Mode.MEANING


class TestWhereTaught:
    @pytest.fixture(autouse=True)
    async def _roles(self, system_roles: None) -> None:
        return None

    async def test_lists_sessions_with_the_objectives_that_matched_and_why(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        found = await search.where_taught(
            db_session, test_settings, await see(db_session, world), "cardiac"
        )

        [session] = found.sessions
        assert (session.event_title, session.module_code) == ("Cardiac cycle", "HSC201")
        assert set(session.why) == {"title", "objective"}
        assert [o.text for o in session.objectives] == ["Describe the cardiac cycle."]
        # The module's own outcome is listed under the module, not under a session.
        [module] = found.modules
        assert module.event_id is None
        assert [o.text for o in module.objectives] == ["Interpret cardiac investigations."]

    async def test_sessions_come_in_the_order_they_are_taught(
        self, db_session: AsyncSession, test_settings: Settings, world: World
    ) -> None:
        # Two matching sessions in the cardio module: week 3 first, then no week, then week 9.
        world.lab.title = "Cardiac skills lab"
        world.lab.week = 9
        world.lecture.week = 3
        await db_session.flush()

        found = await search.where_taught(
            db_session, test_settings, await see(db_session, world), "cardiac"
        )

        assert [(s.event_title, s.week) for s in found.sessions] == [
            ("Cardiac cycle", 3),
            ("Cardiac skills lab", 9),
        ]

    async def test_follows_accepted_links_from_matching_framework_items(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        # "hygiene" appears in no objective or session; an objective taught in the anatomy
        # session is accepted for the hygiene item, so the session is where it is taught.
        anatomy_objective = Objective(
            version_id=world.draft.id,
            level=world.lecture_objective.level,
            learning_event_id=world.anatomy_session.id,
            text="Wash hands before touching a specimen.",
        )
        db_session.add(anatomy_objective)
        await db_session.flush()
        await link(db_session, anatomy_objective, library.hygiene, MappingStatus.ACCEPTED)
        await link(db_session, world.lecture_objective, library.hygiene, MappingStatus.SUGGESTED)

        found = await search.where_taught(
            db_session, test_settings, await see(db_session, world), "hygiene"
        )

        [session] = found.sessions
        assert session.event_title == "Bones"
        assert session.why == ["framework HYG1"]
        assert [i.code for i in found.items] == ["HYG1"]

    async def test_without_library_access_the_framework_route_is_not_taken(
        self, db_session: AsyncSession, test_settings: Settings, world: World, library: Library
    ) -> None:
        await link(db_session, world.lecture_objective, library.hygiene, MappingStatus.ACCEPTED)

        found = await search.where_taught(
            db_session,
            test_settings,
            await see(db_session, world),
            "hygiene",
            frameworks_allowed=False,
        )

        assert found.sessions == [] and found.items == []

    async def test_meaning_finds_sessions_whose_objectives_are_close(
        self,
        db_session: AsyncSession,
        test_settings: Settings,
        redis_client: FakeAsyncRedis,
        world: World,
    ) -> None:
        on = test_settings.model_copy(update={"embeddings_local": True})
        await redis_client.set("embeddings:ready", "1", ex=30)
        await vector(db_session, EmbeddedType.OBJECTIVE, world.lecture_objective, 4)

        found = await search.where_taught(
            db_session,
            on,
            await see(db_session, world),
            "how the heart pumps",
            redis=redis_client,
            embedder=AtAngle(0),
        )

        [session] = found.sessions
        assert session.event_title == "Cardiac cycle"
        assert session.objectives[0].via == "meaning" and found.mode is Mode.MEANING


class TestVisibility:
    """A person finds only what their roles show of the version (ADR 027)."""

    async def test_a_module_coordinator_finds_only_their_module(
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

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params={"q": "cardiac bones"}
        )

        assert response.status_code == 200
        groups = {g["kind"]: g["hits"] for g in response.json()["groups"]}
        assert [h["title"] for h in groups["objective"]] == ["Name the bones."]
        assert groups["event"] == [] or all(h["module_code"] != "HSC201" for h in groups["event"])
        # The programme outcome and the other module's outcomes are not theirs to find.
        everything = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params={"q": "practise safely"}
        )
        assert all(
            g["hits"] == [] for g in everything.json()["groups"] if g["kind"] != "framework_item"
        )

    async def test_a_lecturer_finds_only_their_session_and_its_objectives(
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
            ScopeRef(ScopeType.LEARNING_EVENT, world.lecture.id),
        )

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params={"q": "cardiac"}
        )

        groups = {g["kind"]: g["hits"] for g in response.json()["groups"]}
        assert [h["title"] for h in groups["objective"]] == ["Describe the cardiac cycle."]
        assert [h["title"] for h in groups["event"]] == ["Cardiac cycle"]
        # The module is context for them, not something to search.
        assert groups["module"] == []
        taught = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/where-taught", params={"q": "cardiac"}
        )
        assert [s["event_title"] for s in taught.json()["sessions"]] == ["Cardiac cycle"]
        assert taught.json()["modules"] == []

    async def test_a_version_the_user_cannot_see_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        for path in ("search", "where-taught", "search-filters"):
            response = await api_client.get(
                f"{API}/curriculum-versions/{world.draft.id}/{path}", params={"q": "cardiac"}
            )
            assert response.status_code == 404, path


class TestApi:
    @pytest.fixture(autouse=True)
    async def _admin(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> User:
        return await sign_in(api_client, db_session, test_settings, "platform_admin")

    async def test_requires_sign_in(self, api_client: AsyncClient, world: World) -> None:
        api_client.cookies.clear()

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params={"q": "cardiac"}
        )

        assert response.status_code == 401

    async def test_answers_in_groups_with_where_each_hit_sits(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params={"q": "cardiac cycle"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "cardiac cycle" and body["words"] == "all"
        assert body["mode"] == "keyword" and body["notice"] == "embeddings_off"
        groups = {g["kind"]: g for g in body["groups"]}
        [objective] = groups["objective"]["hits"]
        assert objective["module_code"] == "HSC201" and objective["event_title"] == "Cardiac cycle"
        assert 0 < objective["score"] <= 1 and groups["objective"]["more"] is False

    @pytest.mark.parametrize(
        "params",
        [
            {"q": ""},
            {"q": "a"},
            {"q": "x" * 201},
            {"q": "ok", "limit": 0},
            {"q": "ok", "limit": 51},
        ],
    )
    async def test_bad_queries_are_refused(
        self, api_client: AsyncClient, world: World, params: dict[str, object]
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search", params=params
        )

        assert response.status_code == 422

    async def test_filters_and_kinds_are_taken_from_the_query_string(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search",
            params=[
                ("q", "the"),
                ("types", "objective"),
                ("module_id", str(world.anatomy.id)),
                ("mode", "words"),
            ],
        )

        groups = response.json()["groups"]
        assert [g["kind"] for g in groups] == ["objective"]
        assert [h["title"] for h in groups[0]["hits"]] == ["Name the bones."]

    async def test_an_unknown_filter_value_is_refused(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search",
            params={"q": "ok", "domain": "everything"},
        )

        assert response.status_code == 422

    async def test_where_taught_answers_with_sessions_in_order(
        self, api_client: AsyncClient, world: World
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/where-taught", params={"q": "cardiac"}
        )

        assert response.status_code == 200
        body = response.json()
        [session] = body["sessions"]
        assert session["event_title"] == "Cardiac cycle"
        assert set(session["why"]) == {"title", "objective"}
        assert session["objectives"][0]["text"] == "Describe the cardiac cycle."

    async def test_the_filter_options_list_what_can_be_chosen(
        self, api_client: AsyncClient, world: World, library: Library
    ) -> None:
        response = await api_client.get(
            f"{API}/curriculum-versions/{world.draft.id}/search-filters"
        )

        assert response.status_code == 200
        body = response.json()
        assert {m["label"].split()[0] for m in body["modules"]} == {"HSC201", "HSC101"}
        assert [f["label"] for f in body["frameworks"]] == ["Graduate competencies"]
        assert {"Bloom"} <= {level["label"].split(" · ")[0] for level in body["taxonomy_levels"]}
        assert body["domains"] == ["knowledge", "skill", "attitude"]

    async def test_searching_is_rate_limited(
        self, api_client: AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.api.v1 import search as search_api

        monkeypatch.setattr(search_api, "SEARCHES_PER_MINUTE", 2)
        url = f"{API}/curriculum-versions/{world.draft.id}/search"

        codes = [(await api_client.get(url, params={"q": "cardiac"})).status_code for _ in range(3)]

        assert codes == [200, 200, 429]


_ = uuid
