"""Tests for curriculum versions: publishing, copy forward, deleting drafts and diffs."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    AuditLog,
    CurriculumVersion,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    Role,
    RoleAssignment,
    Tagging,
)
from app.models.mapping import MappingSource, MappingStatus
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective, link_objectives
from app.services.frameworks import add_item
from app.services.mapping import create_link
from app.services.tagging import tag_item
from tests.authz_helpers import grant, new_user
from tests.factories import FrameworkFactory, ModuleFactory
from tests.test_curriculum_edit_api import (
    API,
    MISSING,
    World,
    programme_scope,
    save,
    sign_in,
    world,  # noqa: F401  (fixture)
)
from tests.test_curriculum_reorder_copy_api import operations


async def set_status(
    client: AsyncClient, version_id: uuid.UUID, status: str, reason: str | None = None
) -> Any:
    body: dict[str, str] = {"status": status}
    if reason is not None:
        body["reason"] = reason
    return await client.post(f"{API}/curriculum-versions/{version_id}/status", json=body)


async def copy_forward(
    client: AsyncClient, version_id: uuid.UUID, year: int, roles: list[str] | None = None
) -> Any:
    return await client.post(
        f"{API}/curriculum-versions/{version_id}/copy-forward",
        json={"academic_year": year, "role_assignment_ids": roles or []},
    )


async def tree(client: AsyncClient, version_id: uuid.UUID | str) -> dict[str, Any]:
    response = await client.get(f"{API}/curriculum-versions/{version_id}/structure")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def diff(client: AsyncClient, version_id: uuid.UUID | str, base: uuid.UUID | str) -> Any:
    return await client.get(
        f"{API}/curriculum-versions/{version_id}/diff", params={"base": str(base)}
    )


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", f"/curriculum-versions/{MISSING}/status"),
            ("DELETE", f"/curriculum-versions/{MISSING}"),
            ("GET", f"/curriculum-versions/{MISSING}/copy-forward"),
            ("POST", f"/curriculum-versions/{MISSING}/copy-forward"),
            ("GET", f"/curriculum-versions/{MISSING}/diff?base={MISSING}"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={})
        assert response.status_code == 401


@pytest.fixture
async def director(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,  # noqa: F811
) -> None:
    await sign_in(
        api_client, db_session, test_settings, "programme_director", programme_scope(world)
    )


@pytest.mark.usefixtures("director")
class TestStatus:
    async def test_publishes_a_draft_and_makes_it_read_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        response = await set_status(api_client, world.draft.id, "published")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "published"
        assert body["published_at"] is not None
        assert (await tree(api_client, world.draft.id))["can_edit"] is False
        edit = await api_client.patch(f"{API}/modules/{world.cardio.id}", json={"name": "X"})
        assert edit.status_code == 409
        assert (
            await operations(db_session, "curriculum_versions", "curriculum.version_publish") == 1
        )

    async def test_returns_to_draft_archives_and_unarchives(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        unpublished = await set_status(
            api_client, world.published.id, "draft", "  Wrong module credits.  "
        )
        assert unpublished.status_code == 200
        assert unpublished.json()["published_at"] is None
        assert (await tree(api_client, world.published.id))["can_edit"] is True

        await set_status(api_client, world.published.id, "published")
        archived = await set_status(api_client, world.published.id, "archived")
        assert archived.status_code == 200
        assert archived.json()["published_at"] is not None

        again = await set_status(api_client, world.archived.id, "published")
        assert again.status_code == 200
        for name in ("unpublish", "archive", "unarchive"):
            label = f"curriculum.version_{name}"
            assert await operations(db_session, "curriculum_versions", label) == 1

    async def test_unpublishing_records_the_trimmed_reason_in_the_audit_log(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await set_status(api_client, world.published.id, "draft", "  Wrong module credits.  ")

        reasons = await db_session.scalars(
            select(AuditLog.context["reason"].astext).where(
                AuditLog.entity_type == "curriculum_versions",
                AuditLog.context["operation"].astext == "curriculum.version_unpublish",
            )
        )
        assert set(reasons) == {"Wrong module credits."}

    @pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501])
    async def test_unpublishing_needs_a_usable_reason(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        reason: str | None,
    ) -> None:
        response = await set_status(api_client, world.published.id, "draft", reason)

        assert response.status_code == 422
        assert (await tree(api_client, world.published.id))["version"]["status"] == "published"

    async def test_other_changes_need_no_reason(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        assert (await set_status(api_client, world.draft.id, "published")).status_code == 200
        assert (await set_status(api_client, world.draft.id, "archived")).status_code == 200

    async def test_flags_tell_who_may_unpublish(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        assert (await tree(api_client, world.published.id))["can_unpublish"] is True

    @pytest.mark.parametrize(
        ("which", "status"),
        [
            ("draft", "archived"),
            ("draft", "draft"),
            ("archived", "draft"),
            ("published", "published"),
        ],
    )
    async def test_refuses_other_changes(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        which: str,
        status: str,
    ) -> None:
        version = getattr(world, which)

        response = await set_status(api_client, version.id, status)

        assert response.status_code == 409

    async def test_needs_a_module_to_publish(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        for module in (world.anatomy, world.cardio):
            assert (await api_client.delete(f"{API}/modules/{module.id}")).status_code == 204

        response = await set_status(api_client, world.draft.id, "published")

        assert response.status_code == 409
        assert "module" in response.json()["detail"]

    async def test_unknown_status_is_invalid(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        response = await set_status(api_client, world.draft.id, "retired")

        assert response.status_code == 422


@pytest.mark.usefixtures("director")
class TestDeleteDraft:
    async def test_deletes_a_draft_with_its_contents(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        response = await api_client.delete(f"{API}/curriculum-versions/{world.draft.id}")

        assert response.status_code == 204
        for row in (world.draft, world.year1, world.cardio, world.lecture, world.lecture_objective):
            await db_session.refresh(row)
            assert row.deleted_at == world.draft.deleted_at is not None
        gone = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/structure")
        assert gone.status_code == 404
        # The year is free again.
        assert (await copy_forward(api_client, world.published.id, 2027)).status_code == 201
        assert await operations(db_session, "curriculum_versions", "curriculum.version_delete") == 1

    @pytest.mark.parametrize("which", ["published", "archived"])
    async def test_only_drafts_can_be_deleted(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        which: str,
    ) -> None:
        response = await api_client.delete(f"{API}/curriculum-versions/{getattr(world, which).id}")

        assert response.status_code == 409


async def rich_draft(db: AsyncSession, world: World) -> dict[str, Any]:  # noqa: F811
    """Programme outcome, links, a tag, a mapping and an LMS reference in the draft."""
    outcome = await add_objective(db, world.draft, "Practise safely and ethically.")
    await link_objectives(db, world.cardio_outcome, outcome)
    await link_objectives(db, world.lecture_objective, world.cardio_outcome)
    module_tag = await tag_item(db, world.theme, world.cardio)
    await tag_item(db, world.theme, world.lecture, inherited_from=module_tag)
    framework = FrameworkFactory()
    await save(db, framework)
    item = await add_item(db, framework, code="A1", title="Demo competency")
    await create_link(db, world.cardio_outcome, item, source=MappingSource.IMPORT, coverage=4)
    world.cardio.external_lms_ref = "LMS-1"
    await db.flush()
    return {"outcome": outcome, "item": item}


@pytest.mark.usefixtures("director")
class TestCopyForward:
    async def test_preview_counts_and_suggests_the_next_free_year(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await rich_draft(db_session, world)

        response = await api_client.get(
            f"{API}/curriculum-versions/{world.published.id}/copy-forward"
        )
        draft = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/copy-forward")

        assert response.status_code == 200
        # 2025, 2026 and 2027 exist: the suggestion follows the newest.
        assert response.json()["academic_year"] == 2028
        assert response.json()["taken_years"] == [2025, 2026, 2027]
        body = draft.json()
        assert (body["phases"], body["modules"], body["learning_events"]) == (2, 2, 2)
        assert (body["objectives"], body["mappings"]) == (3, 1)
        assert body["can_copy_roles"] is True
        assert body["role_assignments"] == []

    async def test_copies_everything_with_lineage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        extra = await rich_draft(db_session, world)
        gone = ModuleFactory(version=world.draft, code="OLD1")
        await save(db_session, gone)
        gone.soft_delete()
        await db_session.flush()

        response = await copy_forward(api_client, world.draft.id, 2028)

        assert response.status_code == 201
        body = response.json()
        assert (body["academic_year"], body["status"]) == (2028, "draft")
        assert body["based_on_id"] == str(world.draft.id)
        new_id = uuid.UUID(body["id"])
        copied = await tree(api_client, new_id)
        assert [p["name"] for p in copied["phases"]] == ["Year 1", "Year 2"]
        assert [m["code"] for p in copied["phases"] for m in p["modules"]] == ["HSC101", "HSC201"]
        cardio = copied["phases"][1]["modules"][0]
        assert [e["title"] for e in cardio["events"]] == ["Cardiac cycle", "Skills lab"]
        assert copied["outcome_count"] == 1
        assert copied["can_edit"] is True

        new_module = await db_session.get(Module, uuid.UUID(cardio["id"]))
        assert new_module is not None
        assert new_module.based_on_id == world.cardio.id
        assert new_module.external_lms_ref is None
        phases = await db_session.scalars(select(Phase).where(Phase.version_id == new_id))
        assert {p.based_on_id for p in phases} == {world.year1.id, world.year2.id}
        objectives = {
            o.based_on_id: o
            for o in await db_session.scalars(
                select(Objective).where(Objective.version_id == new_id)
            )
        }
        assert set(objectives) == {
            extra["outcome"].id,
            world.cardio_outcome.id,
            world.lecture_objective.id,
        }
        # Links point inside the new version.
        links = set(
            (
                await db_session.execute(
                    select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
                        ObjectiveLink.child_id.in_([o.id for o in objectives.values()])
                    )
                )
            ).tuples()
        )
        new_outcome = objectives[world.cardio_outcome.id]
        assert links == {
            (new_outcome.id, objectives[extra["outcome"].id].id),
            (objectives[world.lecture_objective.id].id, new_outcome.id),
        }
        # Tags, inherited ones from the copied source.
        new_event = objectives[world.lecture_objective.id].learning_event_id
        inherited = await db_session.scalar(
            select(Tagging).where(Tagging.learning_event_id == new_event)
        )
        assert inherited is not None
        source = await db_session.get(Tagging, inherited.inherited_from_id)
        assert source is not None and source.module_id == new_module.id
        # Mappings with their review state.
        mapping = await db_session.scalar(
            select(MappingLink).where(MappingLink.objective_id == new_outcome.id)
        )
        assert mapping is not None
        assert (mapping.status, mapping.coverage, mapping.source) == (
            MappingStatus.ACCEPTED,
            4,
            MappingSource.IMPORT,
        )
        # Deleted rows stay behind.
        assert (
            await db_session.scalar(
                select(func.count(Module.id)).where(
                    Module.version_id == new_id, Module.code == "OLD1"
                )
            )
            == 0
        )
        ops = await operations(db_session, "curriculum_versions", "curriculum.version_copy_forward")
        assert ops == 1

    async def test_year_must_be_free_and_in_range(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        taken = await copy_forward(api_client, world.published.id, 2027)
        too_late = await copy_forward(api_client, world.published.id, 2201)

        assert taken.status_code == 409
        assert too_late.status_code == 422

    async def test_copies_a_published_version_as_a_draft(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        response = await copy_forward(api_client, world.published.id, 2030)

        assert response.status_code == 201
        assert response.json()["status"] == "draft"
        assert response.json()["published_at"] is None


@pytest.mark.usefixtures("director")
class TestCopyRoleAssignments:
    @pytest.fixture
    async def assignments(
        self,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> dict[str, RoleAssignment]:
        db = db_session
        coordinator = await new_user(db, display_name="Lindiwe Dube")
        lecturer = await new_user(db, display_name="Pieter van Wyk")
        former = await new_user(db, display_name="Former Lecturer", is_active=False)
        guest = await new_user(db, display_name="Guest Lecturer")
        module = ScopeRef(ScopeType.MODULE, world.cardio.id)
        session = ScopeRef(ScopeType.LEARNING_EVENT, world.lab.id)
        found = {
            "coordinator": await grant(db, coordinator, "module_coordinator", module),
            "lecturer": await grant(db, lecturer, "lecturer", session),
            "former": await grant(db, former, "lecturer", module),
            "guest": await grant(
                db, guest, "lecturer", module, expires_at=datetime.now(UTC) + timedelta(days=1)
            ),
        }
        # Expired since it was granted.
        found["guest"].expires_at = datetime.now(UTC) - timedelta(minutes=1)
        special = Role(
            key="taglist_keeper",
            name="Tag list keeper",
            permissions=["taglists.manage"],
            scope_types=["module"],
        )
        await save(db, special)
        found["special"] = await grant(db, coordinator, "taglist_keeper", module)
        return found

    async def test_preview_lists_assignments_with_skip_reasons(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        assignments: dict[str, RoleAssignment],
    ) -> None:
        response = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/copy-forward")

        rows = {row["id"]: row for row in response.json()["role_assignments"]}
        reasons = {key: rows[str(a.id)]["skip_reason"] for key, a in assignments.items()}
        assert reasons == {
            "coordinator": None,
            "lecturer": None,
            "former": "account_inactive",
            "guest": "expired",
            "special": "not_allowed",
        }
        lecturer = rows[str(assignments["lecturer"].id)]
        assert lecturer["user_name"] == "Pieter van Wyk"
        assert lecturer["scope_type"] == "learning_event"
        assert lecturer["item"] == f"{world.cardio.code} · Skills lab"

    async def test_copies_the_chosen_assignments_to_the_new_items(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
        assignments: dict[str, RoleAssignment],
    ) -> None:
        response = await copy_forward(
            api_client, world.draft.id, 2028, [str(assignments["lecturer"].id)]
        )

        assert response.status_code == 201
        new_lab = await db_session.scalar(
            select(LearningEvent).where(LearningEvent.based_on_id == world.lab.id)
        )
        assert new_lab is not None
        copied = list(
            await db_session.scalars(
                select(RoleAssignment).where(RoleAssignment.scope_id == new_lab.id)
            )
        )
        assert [a.user_id for a in copied] == [assignments["lecturer"].user_id]
        new_cardio = await db_session.scalar(
            select(Module).where(Module.based_on_id == world.cardio.id)
        )
        assert new_cardio is not None
        # The unticked coordinator was not copied.
        assert (
            await db_session.scalar(
                select(func.count(RoleAssignment.id)).where(
                    RoleAssignment.scope_id == new_cardio.id
                )
            )
            == 0
        )

    @pytest.mark.parametrize("key", ["former", "guest", "special"])
    async def test_skipped_assignments_cannot_be_copied(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
        assignments: dict[str, RoleAssignment],
        key: str,
    ) -> None:
        response = await copy_forward(api_client, world.draft.id, 2028, [str(assignments[key].id)])

        assert response.status_code == 422
        assert (
            await db_session.scalar(
                select(func.count(CurriculumVersion.id)).where(
                    CurriculumVersion.academic_year == 2028
                )
            )
            == 0
        )

    async def test_assignments_elsewhere_cannot_be_copied(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
        assignments: dict[str, RoleAssignment],
    ) -> None:
        response = await copy_forward(
            api_client, world.published.id, 2028, [str(assignments["coordinator"].id)]
        )

        assert response.status_code == 422


async def test_editors_who_cannot_assign_roles_see_no_names(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,  # noqa: F811
) -> None:
    editor_role = Role(
        key="structure_editor",
        name="Structure editor",
        permissions=["curriculum.view", "curriculum.edit"],
        scope_types=["programme"],
    )
    await save(db_session, editor_role)
    coordinator = await new_user(db_session)
    await grant(
        db_session, coordinator, "module_coordinator", ScopeRef(ScopeType.MODULE, world.cardio.id)
    )
    editor = await sign_in(api_client, db_session, test_settings, None)
    await grant(db_session, editor, "structure_editor", programme_scope(world))

    preview = await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/copy-forward")
    assignment = await db_session.scalar(
        select(RoleAssignment.id).where(RoleAssignment.user_id == coordinator.id)
    )
    with_roles = await copy_forward(api_client, world.draft.id, 2028, [str(assignment)])
    without = await copy_forward(api_client, world.draft.id, 2028)
    publish = await set_status(api_client, world.draft.id, "published")

    assert preview.json()["can_copy_roles"] is False
    assert preview.json()["role_assignments"] == []
    assert with_roles.status_code == 422
    assert without.status_code == 201
    assert publish.status_code == 403


@pytest.mark.parametrize(
    ("role_key", "scope_of", "expected"),
    [
        ("module_coordinator", lambda w: ScopeRef(ScopeType.MODULE, w.cardio.id), 403),
        ("mapper", lambda w: ScopeRef(ScopeType.PROGRAMME, w.programme.id), 403),
        ("student", lambda w: ScopeRef(ScopeType.PROGRAMME, w.programme.id), 404),
    ],
)
async def test_other_roles_cannot_change_versions(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,  # noqa: F811
    role_key: str,
    scope_of: Any,
    expected: int,
) -> None:
    await sign_in(api_client, db_session, test_settings, role_key, scope_of(world))

    responses = [
        await set_status(api_client, world.draft.id, "published"),
        await api_client.get(f"{API}/curriculum-versions/{world.draft.id}/copy-forward"),
        await copy_forward(api_client, world.draft.id, 2028),
        await api_client.delete(f"{API}/curriculum-versions/{world.draft.id}"),
    ]

    assert [r.status_code for r in responses] == [expected] * 4
    if role_key == "module_coordinator":
        structure = await tree(api_client, world.draft.id)
        assert (structure["can_change_status"], structure["can_copy_forward"]) == (False, False)


async def test_publishing_rights_without_unpublish_cannot_return_to_draft(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,  # noqa: F811
) -> None:
    db_session.add(
        Role(
            key="publisher",
            name="Publisher",
            permissions=["curriculum.view", "curriculum.publish"],
            scope_types=["programme"],
        )
    )
    await db_session.flush()
    await sign_in(api_client, db_session, test_settings, "publisher", programme_scope(world))

    refused = await set_status(api_client, world.published.id, "draft", "A good reason.")
    archived = await set_status(api_client, world.published.id, "archived")

    assert refused.status_code == 403
    assert archived.status_code == 200
    assert (await tree(api_client, world.draft.id))["can_unpublish"] is False


def changes_of(body: dict[str, Any], kind: str) -> list[tuple[str, str]]:
    return [(c["change"], c["label"]) for c in body["changes"] if c["kind"] == kind]


@pytest.mark.usefixtures("director")
class TestDiff:
    async def test_follows_items_copied_forward_and_lists_changes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        new_id = (await copy_forward(api_client, world.draft.id, 2028)).json()["id"]
        copied = await tree(api_client, new_id)
        year1, year2 = copied["phases"]
        cardio = year2["modules"][0]
        lecture, lab = cardio["events"]
        # Rename a session (followed by lineage), change a module and its phase, delete a
        # session, add a module, rename a phase, reword an objective.
        await api_client.patch(
            f"{API}/learning-events/{lecture['id']}", json={"title": "Heart cycle"}
        )
        await api_client.patch(
            f"{API}/modules/{cardio['id']}", json={"credits": "15", "phase_id": year1["id"]}
        )
        await api_client.delete(f"{API}/learning-events/{lab['id']}")
        await api_client.post(
            f"{API}/curriculum-versions/{new_id}/modules",
            json={"code": "HSC301", "name": "Research"},
        )
        await api_client.patch(f"{API}/phases/{year2['id']}", json={"name": "Second year"})
        objective = await db_session.scalar(
            select(Objective).where(Objective.based_on_id == world.lecture_objective.id)
        )
        assert objective is not None
        objective.text = "Explain the cardiac cycle."
        await db_session.flush()

        response = await diff(api_client, new_id, world.draft.id)

        assert response.status_code == 200
        body = response.json()
        assert (body["base"]["academic_year"], body["version"]["academic_year"]) == (2027, 2028)
        assert changes_of(body, "phase") == [("changed", "Second year")]
        assert changes_of(body, "module") == [
            ("changed", f"HSC201 {world.cardio.name}"),
            ("added", "HSC301 Research"),
        ]
        module_fields = next(c for c in body["changes"] if c["kind"] == "module")["fields"]
        assert module_fields == [
            {"field": "phase", "before": "Second year", "after": "Year 1"},
            {"field": "credits", "before": "12", "after": "15"},
        ]
        assert sorted(changes_of(body, "learning_event")) == [
            ("changed", "Heart cycle"),
            ("removed", "Skills lab"),
        ]
        reworded = [c for c in body["changes"] if c["kind"] == "objective"]
        assert [(c["change"], c["level"]) for c in reworded] == [("changed", "learning_event")]
        assert reworded[0]["fields"] == [
            {
                "field": "text",
                "before": "Describe the cardiac cycle.",
                "after": "Explain the cardiac cycle.",
            }
        ]
        assert body["summary"]["learning_event"] == {"added": 0, "removed": 1, "changed": 1}

        # The other way round, removed and added swap.
        reverse = (await diff(api_client, world.draft.id, new_id)).json()
        assert ("added", "Skills lab") in changes_of(reverse, "learning_event")
        assert ("removed", "HSC301 Research") in changes_of(reverse, "module")

    async def test_follows_lineage_across_years(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        y2028 = (await copy_forward(api_client, world.draft.id, 2028)).json()["id"]
        y2029 = (await copy_forward(api_client, y2028, 2029)).json()["id"]
        lab = (await tree(api_client, y2029))["phases"][1]["modules"][0]["events"][1]
        await api_client.patch(
            f"{API}/learning-events/{lab['id']}", json={"title": "Clinical skills"}
        )

        body = (await diff(api_client, y2029, world.draft.id)).json()

        assert changes_of(body, "learning_event") == [("changed", "Clinical skills")]

    async def test_matches_unrelated_versions_by_code(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        body = (await diff(api_client, world.draft.id, world.published.id)).json()

        # HSC201 exists in both (matched by code); HSC101 is new; Year 1 matched by name.
        modules = {label.split()[0]: change for change, label in changes_of(body, "module")}
        assert modules["HSC101"] == "added"
        assert modules["HSC201"] == "changed"
        assert changes_of(body, "phase") == [("added", "Year 2")]

    async def test_needs_two_versions_of_one_programme(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        same = await diff(api_client, world.draft.id, world.draft.id)
        missing = await diff(api_client, world.draft.id, MISSING)
        other = await diff(api_client, world.draft.id, world.other_version.id)

        assert same.status_code == 422
        assert missing.status_code == 404
        # The director cannot see the other programme.
        assert other.status_code == 404


async def test_diff_needs_whole_versions(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_settings: Settings,
    world: World,  # noqa: F811
) -> None:
    await sign_in(
        api_client,
        db_session,
        test_settings,
        "module_coordinator",
        ScopeRef(ScopeType.MODULE, world.cardio.id),
    )

    response = await diff(api_client, world.draft.id, world.published.id)

    assert response.status_code == 404
