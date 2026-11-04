"""Tests for the coverage report and the gap report (ADR 050)."""

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import Faculty, Framework, FrameworkItem, Institution, MappingLink, Objective, Phase
from app.models.curriculum import PhaseKind
from app.models.framework import FrameworkStatus
from app.models.mapping import AcceptMethod, DepthMatch, MappingSource, MappingStatus
from app.services.authorization import INSTANCE, ScopeRef
from tests.factories import FrameworkFactory
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


@dataclass
class Library:
    framework: Framework
    group: FrameworkItem
    one: FrameworkItem
    two: FrameworkItem
    three: FrameworkItem
    other: FrameworkItem  # a group with nothing below it


@pytest.fixture
async def library(db_session: AsyncSession) -> Library:
    framework = FrameworkFactory(status=FrameworkStatus.ACTIVE, name="Competencies")
    db_session.add(framework)
    await db_session.flush()
    group = FrameworkItem(
        framework_id=framework.id, code="G1", title="Clinical", depth=0, position=0
    )
    other = FrameworkItem(framework_id=framework.id, code="G2", title="Ethics", depth=0, position=1)
    db_session.add_all([group, other])
    await db_session.flush()
    kids = [
        FrameworkItem(
            framework_id=framework.id,
            code=f"G1.{n}",
            title=f"Skill {n}",
            parent_id=group.id,
            depth=1,
            position=n,
        )
        for n in (1, 2, 3)
    ]
    db_session.add_all(kids)
    await db_session.flush()
    return Library(framework, group, *kids, other)


async def accept(
    db: AsyncSession,
    objective: Objective,
    item: FrameworkItem,
    coverage: int = 4,
    depth: DepthMatch | None = DepthMatch.MATCHES,
    accept_method: AcceptMethod = AcceptMethod.INDIVIDUAL,
    **extra: object,
) -> MappingLink:
    link = MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=MappingSource.HUMAN,
        status=MappingStatus.ACCEPTED,
        accept_method=accept_method,
        coverage=coverage,
        depth_match=depth,
        **extra,  # type: ignore[arg-type]
    )
    db.add(link)
    await db.flush()
    return link


async def other_status(
    db: AsyncSession, objective: Objective, item: FrameworkItem, status: MappingStatus
) -> None:
    db.add(
        MappingLink(
            objective_id=objective.id,
            framework_item_id=item.id,
            source=MappingSource.HUMAN,
            status=status,
            coverage=3,
        )
    )
    await db.flush()


@pytest.fixture
async def admin(
    api_client: AsyncClient, db_session: AsyncSession, test_settings: Settings, world: World
) -> None:
    await sign_in(api_client, db_session, test_settings, "platform_admin")


def url(world: World, tail: str = "") -> str:
    return f"{API}/curriculum-versions/{world.draft.id}/coverage{tail}"


def rows(body: dict) -> dict:  # type: ignore[type-arg]
    return {r["code"]: r for r in body["items"]}


@pytest.mark.usefixtures("admin")
class TestCoverage:
    async def test_only_accepted_links_count_and_the_report_says_what_it_is(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await other_status(db_session, world.cardio_outcome, library.two, MappingStatus.SUGGESTED)
        await other_status(
            db_session, world.cardio_outcome, library.three, MappingStatus.NEEDS_SECOND_REVIEW
        )
        await other_status(db_session, world.anatomy_outcome, library.one, MappingStatus.REJECTED)

        response = await api_client.get(
            url(world), params={"framework_id": str(library.framework.id), "method": "single"}
        )

        assert response.status_code == 200
        body = response.json()
        got = rows(body)
        assert (got["G1.1"]["links"], got["G1.1"]["status"]) == (1, "covered")
        assert (got["G1.2"]["links"], got["G1.2"]["waiting"], got["G1.2"]["status"]) == (
            0,
            1,
            "none",
        )
        assert got["G1.3"]["waiting"] == 1  # a link waiting for a second review is still waiting
        assert body["summary"]["waiting_links"] == 2  # the rejected one is nobody's concern
        assert body["method"] == "single" and body["partial"] is False
        assert body["framework"]["name"] == "Competencies"
        assert body["version"]["academic_year"] == 2027 and body["version"]["status"] == "draft"
        assert body["definition"].startswith(
            "An item (one with nothing below it) is covered when at least one accepted link"
        )
        assert body["generated_at"]
        assert body["objectives_in_scope"] == 4

    async def test_a_group_is_built_up_from_its_items_and_links_made_to_it_are_apart(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.cardio_outcome, library.two)
        await accept(db_session, world.anatomy_outcome, library.group)  # made to the group itself
        params = {"framework_id": str(library.framework.id)}

        single = (await api_client.get(url(world), params={**params, "method": "single"})).json()
        subordinate = (
            await api_client.get(url(world), params={**params, "method": "subordinate"})
        ).json()

        group = rows(single)["G1"]
        assert group["value"] == pytest.approx(0.6667, abs=1e-4) and group["status"] == "partial"
        assert group["links"] == 1  # shown on its row, not counted in the figure
        assert single["summary"]["group_links"] == 1
        assert rows(subordinate)["G1"]["status"] == "covered"  # 67% of its items, from 50%
        assert rows(subordinate)["G1"]["leaves_covered"] == 2
        assert "50%" in subordinate["definition"] and "not counted" in subordinate["definition"]
        # Headline of subordinate match: the average over the groups (there is one).
        figure = subordinate["summary"]["methods"]["subordinate"]
        assert figure["unit"] == "groups" and figure["headline"] == pytest.approx(0.6667, abs=1e-4)

    async def test_weighted_coverage_reduces_a_depth_below_the_target(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one, 5, DepthMatch.MATCHES)
        await accept(db_session, world.cardio_outcome, library.two, 5, DepthMatch.BELOW)
        await accept(db_session, world.anatomy_outcome, library.three, 1, DepthMatch.MATCHES)

        got = rows(
            (
                await api_client.get(
                    url(world),
                    params={"framework_id": str(library.framework.id), "method": "weighted"},
                )
            ).json()
        )

        assert got["G1.1"]["value"] == 1.0 and got["G1.1"]["status"] == "covered"
        assert got["G1.2"]["value"] == 0.8 and got["G1.2"]["status"] == "covered"  # 5, less one
        assert got["G1.3"]["value"] == 0.2 and got["G1.3"]["status"] == "partial"

    async def test_a_link_that_covers_nothing_does_not_cover(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one, 0)

        got = rows(
            (
                await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
            ).json()
        )

        assert got["G1.1"]["links"] == 0 and got["G1.1"]["status"] == "none"

    async def test_bulk_accepted_and_recheck_links_are_flagged_not_hidden(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(
            db_session, world.lecture_objective, library.one, accept_method=AcceptMethod.BULK
        )
        await accept(
            db_session,
            world.cardio_outcome,
            library.two,
            accept_method=AcceptMethod.BULK,
            needs_recheck=True,
        )
        await accept(db_session, world.anatomy_outcome, library.two)

        body = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()

        got = rows(body)
        assert (got["G1.1"]["bulk_links"], got["G1.1"]["only_bulk"]) == (1, True)
        assert (got["G1.2"]["bulk_links"], got["G1.2"]["only_bulk"]) == (1, False)
        assert got["G1.2"]["recheck_links"] == 1
        assert (body["summary"]["bulk_links"], body["summary"]["recheck_links"]) == (2, 1)

    async def test_the_summary_gives_every_method_for_the_whole_framework(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.cardio_outcome, library.one)
        await accept(db_session, world.anatomy_outcome, library.one)
        await accept(db_session, world.lecture_objective, library.other)

        summary = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()["summary"]

        assert summary["leaves"] == 4  # three skills and the group with nothing below it
        assert summary["groups"] == 1
        assert summary["methods"]["single"] == {
            "headline": 0.5,
            "unit": "items",
            "total": 4,
            "covered": 2,
            "partial": 0,
            "uncovered": 2,
        }
        multiple = summary["methods"]["multiple"]
        assert multiple["headline"] == 0.25 and multiple["partial"] == 0  # no partial credit
        assert multiple["covered"] == 1 and multiple["uncovered"] == 3
        assert summary["methods"]["subordinate"]["headline"] == pytest.approx(0.3333, abs=1e-4)
        # G1.1 has three links (capped at 1), G2 one link of 0.8, the other two nothing.
        assert summary["methods"]["weighted"]["headline"] == pytest.approx(0.45)

    async def test_the_settings_of_the_institution_set_the_numbers(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,
        library: Library,
    ) -> None:
        faculty = await db_session.get(Faculty, world.programme.faculty_id)
        institution = await db_session.get(Institution, faculty.institution_id)  # type: ignore[union-attr]
        institution.settings = {"coverage": {"multiple_match_n": 1}}  # type: ignore[union-attr]
        await db_session.flush()
        await accept(db_session, world.lecture_objective, library.one)

        body = (
            await api_client.get(
                url(world),
                params={"framework_id": str(library.framework.id), "method": "multiple"},
            )
        ).json()

        assert rows(body)["G1.1"]["status"] == "covered"
        assert body["params"]["multiple_match_n"] == 1
        assert "at least 1 accepted" in body["definition"]

    async def test_the_heatmap_puts_links_in_the_phase_of_their_module(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        phase = Phase(version_id=world.draft.id, name="Year 2", position=0, kind=PhaseKind.YEAR)
        db_session.add(phase)
        await db_session.flush()
        world.cardio.phase_id = phase.id
        await db_session.flush()
        await accept(db_session, world.lecture_objective, library.one)  # a session of cardio
        await accept(db_session, world.cardio_outcome, library.two)  # a module outcome of cardio
        await accept(db_session, world.anatomy_outcome, library.three)  # a module with no phase
        await accept(db_session, world.programme_outcome, library.other)

        body = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()

        assert [(c["kind"], c["label"]) for c in body["columns"]] == [
            ("phase", "Year 2"),
            ("programme", ""),
            ("none", ""),
        ]
        heat = {r["code"]: r["cells"] for r in body["heatmap"]}
        year = str(phase.id)
        assert heat["G1"]["all"] == pytest.approx(1.0)
        assert heat["G1"][year] == pytest.approx(2 / 3, abs=1e-4)
        assert heat["G1"]["none"] == pytest.approx(1 / 3, abs=1e-4)
        assert heat["G1"]["programme"] == 0
        assert heat["G2"]["programme"] == 1.0 and heat["G2"][year] == 0

    async def test_unknown_or_draft_frameworks_and_methods_are_refused(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        library.framework.status = FrameworkStatus.DRAFT
        await db_session.flush()

        draft = await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        missing = await api_client.get(url(world), params={"framework_id": str(uuid.uuid4())})
        no_framework = await api_client.get(url(world))
        bad_method = await api_client.get(
            url(world), params={"framework_id": str(library.framework.id), "method": "magic"}
        )

        assert (draft.status_code, missing.status_code) == (404, 404)
        assert (no_framework.status_code, bad_method.status_code) == (422, 422)


class TestWhoMaySee:
    async def test_signed_out_is_refused(self, api_client: AsyncClient, world: World) -> None:
        response = await api_client.get(url(world), params={"framework_id": str(uuid.uuid4())})

        assert response.status_code == 401

    async def test_a_person_who_sees_the_version_but_may_not_read_reports_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lecture.id),
        )

        for tail in ("", "/gaps"):
            response = await api_client.get(
                url(world, tail), params={"framework_id": str(library.framework.id)}
            )
            assert response.status_code == 403, tail

    async def test_a_version_that_cannot_be_seen_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student", INSTANCE)

        response = await api_client.get(
            url(world), params={"framework_id": str(library.framework.id)}
        )

        assert response.status_code == 404

    async def test_a_module_coordinator_gets_a_report_on_their_module_and_is_told_it_is_partial(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
        library: Library,
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)  # a cardio session
        await accept(db_session, world.anatomy_outcome, library.two)
        await accept(db_session, world.programme_outcome, library.three)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.anatomy.id),
        )

        body = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()

        assert body["partial"] is True and body["objectives_in_scope"] == 1
        got = rows(body)
        assert got["G1.2"]["links"] == 1
        assert got["G1.1"]["links"] == 0 and got["G1.3"]["links"] == 0
        gaps = await api_client.get(
            url(world, "/gaps"), params={"framework_id": str(library.framework.id)}
        )
        assert gaps.status_code == 200 and gaps.json()["partial"] is True
        assert gaps.json()["unlinked"] == [] and gaps.json()["only_waiting"] == []


@pytest.mark.usefixtures("admin")
class TestGaps:
    async def test_lists_items_that_are_not_covered_and_why(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await accept(db_session, world.cardio_outcome, library.two)
        await other_status(
            db_session, world.anatomy_outcome, library.three, MappingStatus.SUGGESTED
        )

        body = (
            await api_client.get(
                url(world, "/gaps"),
                params={"framework_id": str(library.framework.id), "method": "multiple"},
            )
        ).json()

        # Three links are needed and there is no partial credit: nothing is covered.
        assert [(g["code"], g["status"]) for g in body["gaps"]] == [
            ("G1.1", "none"),
            ("G1.2", "none"),
            ("G1.3", "none"),
            ("G2", "none"),
        ]
        assert body["gaps"][0]["reason"] == "1 of 3 accepted links"
        third = body["gaps"][2]
        assert third["waiting"] == 1 and third["reason"] == "no accepted link"
        assert [p["code"] for p in third["path"]] == ["G1"]
        assert body["group_gaps"] == []  # groups are listed for subordinate match only
        assert body["definition"].startswith("An item is covered when at least 3")

    async def test_subordinate_match_lists_the_groups_under_its_share(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)  # 1 of 3 items: 33%

        body = (
            await api_client.get(
                url(world, "/gaps"),
                params={"framework_id": str(library.framework.id), "method": "subordinate"},
            )
        ).json()

        [group] = body["group_gaps"]
        assert (group["code"], group["status"]) == ("G1", "partial")
        assert group["reason"] == "1 of 3 items below it covered"
        assert group["leaves"] == 3 and group["leaves_covered"] == 1
        assert {g["code"] for g in body["gaps"]} == {"G1.2", "G1.3", "G2"}

    async def test_lists_objectives_with_no_accepted_mapping_apart_from_those_with_suggestions(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        await accept(db_session, world.lecture_objective, library.one)
        await other_status(db_session, world.cardio_outcome, library.two, MappingStatus.SUGGESTED)

        body = (
            await api_client.get(
                url(world, "/gaps"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        assert {o["text"] for o in body["unlinked"]} == {"Practise safely.", "Name the bones."}
        assert [(o["text"], o["waiting"]) for o in body["only_waiting"]] == [
            ("Interpret cardiac investigations.", 1)
        ]
        assert (body["unlinked_total"], body["only_waiting_total"]) == (2, 1)
        anatomy = next(o for o in body["unlinked"] if o["text"] == "Name the bones.")
        assert anatomy["module_code"] == "HSC101"

    async def test_an_objective_is_mapped_only_by_a_link_to_this_framework(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        elsewhere = FrameworkFactory(status=FrameworkStatus.ACTIVE, name="Elsewhere")
        db_session.add(elsewhere)
        await db_session.flush()
        item = FrameworkItem(
            framework_id=elsewhere.id, code="E1", title="Other", depth=0, position=0
        )
        db_session.add(item)
        await db_session.flush()
        await accept(db_session, world.lecture_objective, item)

        body = (
            await api_client.get(
                url(world, "/gaps"), params={"framework_id": str(library.framework.id)}
            )
        ).json()

        assert "Describe the cardiac cycle." in {o["text"] for o in body["unlinked"]}

    async def test_deleted_and_retired_objectives_and_their_links_do_not_count(
        self, api_client: AsyncClient, db_session: AsyncSession, world: World, library: Library
    ) -> None:
        link = await accept(db_session, world.anatomy_outcome, library.one)
        world.anatomy_outcome.soft_delete()
        link.soft_delete()
        await db_session.flush()

        body = (
            await api_client.get(url(world), params={"framework_id": str(library.framework.id)})
        ).json()

        assert rows(body)["G1.1"]["links"] == 0
        assert body["objectives_in_scope"] == 3
