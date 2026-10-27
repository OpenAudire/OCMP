"""The mapping workspace API: reading objectives with links, and linking by hand (ADR 039)."""

from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    AIRun,
    AuditLog,
    CurriculumVersion,
    Faculty,
    Framework,
    FrameworkItem,
    Institution,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Programme,
    Role,
)
from app.models.curriculum import VersionStatus
from app.models.mapping import AcceptMethod, AIRunType, DepthMatch, MappingSource, MappingStatus
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective
from app.services.frameworks import add_item
from tests.authz_helpers import grant
from tests.factories import (
    CurriculumVersionFactory,
    FacultyFactory,
    FrameworkFactory,
    LearningEventFactory,
    ModuleFactory,
    ProgrammeFactory,
)
from tests.test_curriculum_edit_api import MISSING, sign_in

API = "/api/v1"


@dataclass
class World:
    framework: Framework
    item_a: FrameworkItem
    item_b: FrameworkItem
    faculty: Faculty
    programme: Programme
    draft: CurriculumVersion
    published: CurriculumVersion
    module: Module
    other_module: Module
    published_module: Module
    event: LearningEvent
    outcome: Objective  # programme outcome (draft)
    module_objective: Objective
    other_objective: Objective
    event_objective: Objective
    published_objective: Objective


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


@pytest.fixture
async def world(db_session: AsyncSession, system_roles: None) -> World:
    db = db_session
    faculty = FacultyFactory()
    framework = FrameworkFactory(name="Workspace framework", key="ws-fw")
    programme = ProgrammeFactory(faculty=faculty, code="BWS", name="BSc Workspace")
    published = CurriculumVersionFactory(
        programme=programme, academic_year=2026, status=VersionStatus.PUBLISHED
    )
    draft = CurriculumVersionFactory(programme=programme, academic_year=2027)
    await save(db, faculty, framework, programme, published, draft)
    module = ModuleFactory(version=draft, code="HSC101", name="Anatomy")
    other_module = ModuleFactory(version=draft, code="HSC102", name="Physiology")
    published_module = ModuleFactory(version=published, code="HSC101", name="Anatomy")
    await save(db, module, other_module, published_module)
    event = LearningEventFactory(module=module, title="Heart lecture")
    await save(db, event)
    item_a = await add_item(db, framework, code="A", title="Clinical reasoning")
    item_b = await add_item(db, framework, code="B", title="Communication", position=1)
    return World(
        framework=framework,
        item_a=item_a,
        item_b=item_b,
        faculty=faculty,
        programme=programme,
        draft=draft,
        published=published,
        module=module,
        other_module=other_module,
        published_module=published_module,
        event=event,
        outcome=await add_objective(db, draft, "Reason clinically."),
        module_objective=await add_objective(db, module, "Describe the heart."),
        other_objective=await add_objective(db, other_module, "Explain gas exchange."),
        event_objective=await add_objective(db, event, "Name the heart valves."),
        published_objective=await add_objective(db, published_module, "Published wording."),
    )


def module_scope(module: Module) -> ScopeRef:
    return ScopeRef(ScopeType.MODULE, module.id)


def body(
    item: FrameworkItem, coverage: int = 3, depth: str = "matches", **extra: Any
) -> dict[str, Any]:
    return {
        "framework_item_id": str(item.id),
        "coverage": coverage,
        "depth_match": depth,
        "rationale": "",
        **extra,
    }


async def add(client: AsyncClient, objective: Objective, **payload: Any) -> Any:
    return await client.post(f"{API}/objectives/{objective.id}/mapping-links", json=payload)


async def set_four_eyes(db: AsyncSession, world: World) -> None:
    institution = await db.get(Institution, world.faculty.institution_id)
    assert institution is not None
    institution.settings = {"mapping": {"four_eyes": True}}
    await db.flush()


async def editor_role(db: AsyncSession) -> None:
    """A role that may map but not review (no built-in role is that narrow)."""
    db.add(
        Role(
            key="mapping_only",
            name="Mapping only",
            permissions=["curriculum.view", "mapping.edit"],
            scope_types=["module", "programme"],
        )
    )
    await db.flush()


async def stored(db: AsyncSession, link_id: str) -> MappingLink:
    link = await db.scalar(select(MappingLink).where(MappingLink.id == link_id))
    assert link is not None
    await db.refresh(link)
    return link


class TestReading:
    async def test_lists_objectives_with_links_and_permissions(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )
        made = await add(api_client, world.module_objective, **body(world.item_a, 4, "above"))
        assert made.status_code == 201

        response = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/mapping")

        assert response.status_code == 200
        data = response.json()
        assert data["editable"] is True and data["four_eyes"] is False
        by_text = {o["text"]: o for o in data["objectives"]}
        # A module coordinator sees their module, not the programme outcome or other modules.
        assert set(by_text) == {"Describe the heart.", "Name the heart valves."}
        mine = by_text["Describe the heart."]
        assert (mine["can_edit"], mine["can_review"]) == (True, True)
        assert mine["module_code"] == "HSC101"
        [shown] = mine["links"]
        assert (shown["item_code"], shown["coverage"], shown["depth_match"]) == ("A", 4, "above")
        assert shown["framework_name"] == "Workspace framework"

    async def test_rejected_links_are_hidden(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await save(
            db_session,
            MappingLink(
                objective_id=world.module_objective.id,
                framework_item_id=world.item_a.id,
                source=MappingSource.IMPORT,
                status=MappingStatus.REJECTED,
            ),
        )
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        data = (await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/mapping")).json()

        assert all(o["links"] == [] for o in data["objectives"])
        assert {o["level"] for o in data["objectives"]} == {"programme", "module", "learning_event"}

    async def test_hidden_version_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, None)
        for version_id in (world.draft.id, MISSING):
            response = await api_client.get(f"{API}/curriculum-versions/{version_id}/mapping")
            assert response.status_code == 404

    async def test_published_version_is_read_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        data = (
            await api_client.get(f"{API}/curriculum-versions/{world.published.id}/mapping")
        ).json()
        assert data["editable"] is False
        assert [o["text"] for o in data["objectives"]] == ["Published wording."]


class TestAddingLinks:
    async def test_reviewer_link_is_accepted_and_audited(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        user = await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )

        response = await add(
            api_client,
            world.module_objective,
            **body(world.item_a, 5, "not_applicable", rationale=" Why "),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert (data["status"], data["source"], data["rationale"]) == ("accepted", "human", "Why")
        assert data["depth_match"] == "not_applicable"
        link = await stored(db_session, data["id"])
        assert link.accept_method == AcceptMethod.INDIVIDUAL
        assert (link.first_reviewer_id, link.created_by_id) == (user.id, user.id)
        operations = await db_session.scalars(select(AuditLog.context["operation"].as_string()))
        assert "mapping.link_add" in set(operations)

    async def test_four_eyes_sends_a_reviewers_link_to_a_second_review(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await set_four_eyes(db_session, world)
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )

        response = await add(api_client, world.module_objective, **body(world.item_a))

        assert response.json()["status"] == "needs_second_review"
        link = await stored(db_session, response.json()["id"])
        assert link.accept_method is None and link.second_reviewer_id is None

    async def test_editor_without_review_makes_a_suggestion(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await editor_role(db_session)
        user = await sign_in(api_client, db_session, test_settings, None)
        await grant(db_session, user, "mapping_only", module_scope(world.module))

        response = await add(api_client, world.module_objective, **body(world.item_a))

        assert response.status_code == 201
        assert response.json()["status"] == "suggested"
        link = await stored(db_session, response.json()["id"])
        assert link.first_reviewer_id is None and link.created_by_id == user.id

    async def test_same_pair_twice_is_a_conflict(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        assert (
            await add(api_client, world.module_objective, **body(world.item_a))
        ).status_code == 201
        again = await add(api_client, world.module_objective, **body(world.item_a, 1))
        assert again.status_code == 409

    async def test_rejected_pair_is_reopened(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        rejected = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.IMPORT,
            status=MappingStatus.REJECTED,
            coverage=1,
            confidence=0.5,
            evidence_quote="Describe",
            needs_recheck=True,
        )
        await save(db_session, rejected)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await add(api_client, world.module_objective, **body(world.item_a, 2))

        assert response.status_code == 201
        assert response.json()["id"] == str(rejected.id)
        link = await stored(db_session, str(rejected.id))
        assert (link.status, link.source, link.coverage) == (
            MappingStatus.ACCEPTED,
            MappingSource.HUMAN,
            2,
        )
        assert (link.confidence, link.evidence_quote, link.needs_recheck) == (None, "", False)

    async def test_published_version_cannot_be_mapped(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await add(api_client, world.published_objective, **body(world.item_a))
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "change",
        [{"coverage": 6}, {"coverage": -1}, {"depth_match": "sideways"}, {"depth_match": None}],
    )
    async def test_invalid_values_are_refused(
        self,
        change: dict[str, Any],
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await add(api_client, world.module_objective, **body(world.item_a) | change)
        assert response.status_code == 422

    async def test_unknown_item_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await add(
            api_client,
            world.module_objective,
            **body(world.item_a) | {"framework_item_id": MISSING},
        )
        assert response.status_code == 422

    async def test_deleted_framework_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        world.framework.soft_delete()
        await db_session.flush()
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await add(api_client, world.module_objective, **body(world.item_a))
        assert response.status_code == 422

    async def test_permission_follows_the_objectives_scope(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )
        # Their own module's objective and session objective: allowed.
        assert (
            await add(api_client, world.event_objective, **body(world.item_a))
        ).status_code == 201
        # Programme outcome and another module: not visible to them, so 404, never 403.
        assert (await add(api_client, world.outcome, **body(world.item_a))).status_code == 404
        assert (
            await add(api_client, world.other_objective, **body(world.item_a))
        ).status_code == 404

    async def test_viewer_without_mapping_permission_is_forbidden(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "lecturer", module_scope(world.module))
        response = await add(api_client, world.module_objective, **body(world.item_a))
        assert response.status_code == 403

    async def test_missing_objective_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        response = await api_client.post(
            f"{API}/objectives/{MISSING}/mapping-links", json=body(world.item_a)
        )
        assert response.status_code == 404


class TestChangingLinks:
    async def make(self, client: AsyncClient, world: World) -> dict[str, Any]:
        response = await add(client, world.module_objective, **body(world.item_a))
        assert response.status_code == 201
        data: dict[str, Any] = response.json()
        return data

    async def test_reviewer_edit_keeps_it_accepted_and_the_flag(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await self.make(api_client, world)
        link = await stored(db_session, made["id"])
        link.needs_recheck = True
        await db_session.flush()

        response = await api_client.patch(
            f"{API}/mapping-links/{made['id']}",
            json={"coverage": 5, "depth_match": "below", "rationale": "Better"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert (data["status"], data["coverage"], data["depth_match"]) == ("accepted", 5, "below")
        # Editing never clears the wording-changed flag; only confirming does.
        assert data["needs_recheck"] is True

    async def test_four_eyes_edit_of_an_accepted_link_needs_a_second_review(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await self.make(api_client, world)
        assert made["status"] == "accepted"
        await set_four_eyes(db_session, world)

        response = await api_client.patch(
            f"{API}/mapping-links/{made['id']}",
            json={"coverage": 1, "depth_match": "matches", "rationale": ""},
        )

        assert response.json()["status"] == "needs_second_review"
        link = await stored(db_session, made["id"])
        assert link.accept_method is None

    async def test_unchanged_edit_leaves_the_status_alone(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = await self.make(api_client, world)
        await set_four_eyes(db_session, world)

        response = await api_client.patch(
            f"{API}/mapping-links/{made['id']}",
            json={"coverage": 3, "depth_match": "matches", "rationale": ""},
        )

        assert response.json()["status"] == "accepted"

    async def test_edit_by_a_non_reviewer_resets_to_suggested(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await editor_role(db_session)
        link = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.HUMAN,
            status=MappingStatus.ACCEPTED,
            accept_method=AcceptMethod.INDIVIDUAL,
            coverage=3,
            depth_match=DepthMatch.MATCHES,
        )
        await save(db_session, link)
        user = await sign_in(api_client, db_session, test_settings, None)
        await grant(db_session, user, "mapping_only", module_scope(world.module))

        response = await api_client.patch(
            f"{API}/mapping-links/{link.id}",
            json={"coverage": 2, "depth_match": "matches", "rationale": ""},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "suggested"
        fresh = await stored(db_session, str(link.id))
        assert (fresh.accept_method, fresh.first_reviewer_id) == (None, None)

    async def test_published_version_and_hidden_links(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        published = MappingLink(
            objective_id=world.published_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.IMPORT,
            status=MappingStatus.ACCEPTED,
            accept_method=AcceptMethod.IMPORTED,
            coverage=2,
            depth_match=DepthMatch.MATCHES,
        )
        rejected = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_b.id,
            source=MappingSource.IMPORT,
            status=MappingStatus.REJECTED,
        )
        await save(db_session, published, rejected)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        change = {"coverage": 1, "depth_match": "below", "rationale": ""}

        assert (
            await api_client.patch(f"{API}/mapping-links/{published.id}", json=change)
        ).status_code == 409
        assert (await api_client.delete(f"{API}/mapping-links/{published.id}")).status_code == 409
        assert (
            await api_client.patch(f"{API}/mapping-links/{rejected.id}", json=change)
        ).status_code == 404
        assert (
            await api_client.patch(f"{API}/mapping-links/{MISSING}", json=change)
        ).status_code == 404

    async def test_a_link_outside_the_users_scope_is_not_found(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        link = MappingLink(
            objective_id=world.other_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.IMPORT,
            status=MappingStatus.ACCEPTED,
            accept_method=AcceptMethod.IMPORTED,
        )
        await save(db_session, link)
        await sign_in(
            api_client, db_session, test_settings, "module_coordinator", module_scope(world.module)
        )
        response = await api_client.delete(f"{API}/mapping-links/{link.id}")
        assert response.status_code == 404


class TestRemovingAndRechecking:
    async def test_remove_deletes_a_hand_made_link(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = (await add(api_client, world.module_objective, **body(world.item_a))).json()

        response = await api_client.delete(f"{API}/mapping-links/{made['id']}")

        assert response.status_code == 200 and response.json() == {"deleted": True}
        assert await db_session.get(MappingLink, made["id"]) is None
        operations = set(
            await db_session.scalars(select(AuditLog.context["operation"].as_string()))
        )
        assert "mapping.link_remove" in operations

    async def test_remove_rejects_an_ai_suggestion_instead(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        run = AIRun(
            type=AIRunType.MAPPING, provider="null", model="test-model", prompt_version="v1"
        )
        await save(db_session, run)
        suggestion = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.AI,
            ai_run_id=run.id,
            status=MappingStatus.SUGGESTED,
        )
        await save(db_session, suggestion)
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.delete(f"{API}/mapping-links/{suggestion.id}")

        assert response.json() == {"deleted": False}
        assert (await stored(db_session, str(suggestion.id))).status == MappingStatus.REJECTED

    async def test_confirm_recheck_clears_only_the_flag(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        made = (await add(api_client, world.module_objective, **body(world.item_a))).json()
        link = await stored(db_session, made["id"])
        link.needs_recheck = True
        await db_session.flush()

        response = await api_client.post(f"{API}/mapping-links/{made['id']}/recheck")

        assert response.status_code == 200
        assert (response.json()["status"], response.json()["needs_recheck"]) == ("accepted", False)
        again = await api_client.post(f"{API}/mapping-links/{made['id']}/recheck")
        assert again.status_code == 409

    async def test_confirm_recheck_needs_review_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await editor_role(db_session)
        link = MappingLink(
            objective_id=world.module_objective.id,
            framework_item_id=world.item_a.id,
            source=MappingSource.HUMAN,
            status=MappingStatus.ACCEPTED,
            accept_method=AcceptMethod.INDIVIDUAL,
            needs_recheck=True,
        )
        await save(db_session, link)
        user = await sign_in(api_client, db_session, test_settings, None)
        await grant(db_session, user, "mapping_only", module_scope(world.module))

        response = await api_client.post(f"{API}/mapping-links/{link.id}/recheck")

        assert response.status_code == 403
