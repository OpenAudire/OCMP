"""Tests for minimal assessments: items, objective links, copying, diffs and permissions."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    AuditLog,
    Module,
    Objective,
    TagValue,
)
from app.models.tagging import TagListKind
from app.services.authorization import ScopeRef
from app.services.curriculum import add_objective
from app.services.tagging import add_tag_value
from tests.factories import LearningEventFactory, TagListFactory
from tests.test_curriculum_edit_api import (
    API,
    MISSING,
    World,
    programme_scope,
    save,
    sign_in,
    world,  # noqa: F401  (fixture)
)


async def new_method(db: AsyncSession, label: str = "OSCE", active: bool = True) -> TagValue:
    tag_list = TagListFactory(
        key=f"assess-{uuid.uuid4().hex[:6]}", kind=TagListKind.ASSESSMENT_METHOD, name="Methods"
    )
    await save(db, tag_list)
    value = await add_tag_value(db, tag_list, label)
    value.is_active = active
    await db.flush()
    return value


async def add_assessment(
    client: AsyncClient, module_id: uuid.UUID, **fields: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/modules/{module_id}/assessments", json={"name": "Final exam", **fields}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def module_assessments(client: AsyncClient, module_id: uuid.UUID) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/modules/{module_id}")
    assert response.status_code == 200
    found: list[dict[str, Any]] = response.json()["assessments"]
    return found


async def operations(db: AsyncSession, entity_type: str, operation: str) -> int:
    count = await db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.entity_type == entity_type,
            AuditLog.context["operation"].astext == operation,
        )
    )
    return count or 0


class TestSignInRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", f"/modules/{MISSING}/assessments"),
            ("PATCH", f"/assessments/{MISSING}"),
            ("DELETE", f"/assessments/{MISSING}"),
            ("POST", f"/assessments/{MISSING}/items"),
            ("PATCH", f"/assessment-items/{MISSING}"),
            ("DELETE", f"/assessment-items/{MISSING}"),
            ("GET", "/assessment-methods"),
            ("GET", f"/modules/{MISSING}/assessable-objectives"),
            ("GET", f"/curriculum-versions/{MISSING}/credit-check"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={})
        assert response.status_code == 401


class TestProgrammeDirector:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    async def test_adds_and_changes_an_assessment(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        method = await new_method(db_session)

        created = await add_assessment(
            api_client,
            world.cardio.id,
            method_value_id=str(method.id),
            weight="60",
            timing="End of semester",
            time_minutes=180,
        )

        assert created["method"] == "OSCE"
        assert float(created["weight"]) == 60
        assert created["items"] == []
        second = await add_assessment(api_client, world.cardio.id, name="Class test")
        assert (created["position"], second["position"]) == (0, 1)

        response = await api_client.patch(
            f"{API}/assessments/{created['id']}",
            json={"name": "Final OSCE", "weight": None, "method_value_id": None},
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["name"], body["weight"], body["method"]) == ("Final OSCE", None, None)
        assert body["time_minutes"] == 180
        listed = await module_assessments(api_client, world.cardio.id)
        assert [a["name"] for a in listed] == ["Final OSCE", "Class test"]
        assert await operations(db_session, "assessments", "curriculum.assessment_create") == 3
        assert await operations(db_session, "assessments", "curriculum.assessment_update") == 1

    async def test_method_must_come_from_an_active_assessment_list(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        retired = await new_method(db_session, "Retired", active=False)
        for value_id in (world.lecture_format.id, world.theme.id, retired.id, uuid.uuid4()):
            response = await api_client.post(
                f"{API}/modules/{world.cardio.id}/assessments",
                json={"name": "Exam", "method_value_id": str(value_id)},
            )
            assert response.status_code == 422, value_id

    async def test_rejects_bad_values(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        for body in (
            {"name": "  "},
            {"name": "Exam", "weight": "100.5"},
            {"name": "Exam", "weight": "-1"},
            {"name": "Exam", "time_minutes": -5},
        ):
            response = await api_client.post(
                f"{API}/modules/{world.cardio.id}/assessments", json=body
            )
            assert response.status_code == 422, body
        created = await add_assessment(api_client, world.cardio.id)
        cleared = await api_client.patch(f"{API}/assessments/{created['id']}", json={"name": None})
        assert cleared.status_code == 422

    async def test_items_assess_objectives_of_the_module_and_its_sessions(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        exam = await add_assessment(api_client, world.cardio.id)
        url = f"{API}/assessments/{exam['id']}/items"

        added = await api_client.post(
            url,
            json={
                "label": "Question 1",
                "marks": "10",
                "objective_ids": [
                    str(world.cardio_outcome.id),
                    str(world.lecture_objective.id),
                    str(world.lecture_objective.id),
                ],
            },
        )

        assert added.status_code == 201
        [item] = added.json()["items"]
        assert item["marks"] == "10.0"
        assert item["objective_ids"] == [
            str(world.cardio_outcome.id),
            str(world.lecture_objective.id),
        ]
        options = await api_client.get(f"{API}/modules/{world.cardio.id}/assessable-objectives")
        assert [(o["level"], o["event_title"]) for o in options.json()] == [
            ("module", None),
            ("learning_event", "Cardiac cycle"),
        ]

        # Replace the links; other items keep theirs.
        await api_client.post(url, json={"label": "Question 2"})
        changed = await api_client.patch(
            f"{API}/assessment-items/{item['id']}",
            json={"label": "Q1", "objective_ids": [str(world.lecture_objective.id)]},
        )
        assert changed.status_code == 200
        items = changed.json()["items"]
        assert [i["label"] for i in items] == ["Q1", "Question 2"]
        assert items[0]["objective_ids"] == [str(world.lecture_objective.id)]
        assert items[1]["objective_ids"] == []
        links = await db_session.scalar(select(func.count(AssessmentItemObjective.id)))
        assert links == 1
        assert (
            await operations(
                db_session, "assessment_item_objectives", "curriculum.assessment_item_update"
            )
            == 1
        )

    async def test_cannot_assess_objectives_of_other_modules(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        other_event = LearningEventFactory(module=world.anatomy, title="Bones")
        await save(db_session, other_event)
        foreign = [
            await add_objective(db_session, world.anatomy, "Name the bones."),
            await add_objective(db_session, other_event, "Identify the femur."),
            world.cardio_outcome,
        ]
        exam = await add_assessment(api_client, world.cardio.id)

        for objective in foreign[:2]:
            response = await api_client.post(
                f"{API}/assessments/{exam['id']}/items",
                json={"label": "Q", "objective_ids": [str(objective.id)]},
            )
            assert response.status_code == 422
        fine = await api_client.post(
            f"{API}/assessments/{exam['id']}/items",
            json={"label": "Q", "objective_ids": [str(foreign[2].id)]},
        )
        assert fine.status_code == 201
        refused = await api_client.patch(
            f"{API}/assessment-items/{fine.json()['items'][0]['id']}",
            json={"objective_ids": [str(foreign[0].id)]},
        )
        assert refused.status_code == 422

    async def test_deleted_objectives_drop_out_of_reads(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        exam = await add_assessment(api_client, world.cardio.id)
        await api_client.post(
            f"{API}/assessments/{exam['id']}/items",
            json={"label": "Q", "objective_ids": [str(world.lecture_objective.id)]},
        )

        deleted = await api_client.delete(f"{API}/objectives/{world.lecture_objective.id}")
        assert deleted.status_code == 204

        [found] = await module_assessments(api_client, world.cardio.id)
        assert found["items"][0]["objective_ids"] == []
        options = await api_client.get(f"{API}/modules/{world.cardio.id}/assessable-objectives")
        assert [o["id"] for o in options.json()] == [str(world.cardio_outcome.id)]

    async def test_deletes_items_and_assessments(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        exam = await add_assessment(api_client, world.cardio.id)
        one = (
            await api_client.post(f"{API}/assessments/{exam['id']}/items", json={"label": "Q1"})
        ).json()["items"][0]
        await api_client.post(f"{API}/assessments/{exam['id']}/items", json={"label": "Q2"})

        removed = await api_client.delete(f"{API}/assessment-items/{one['id']}")
        assert removed.status_code == 204
        [found] = await module_assessments(api_client, world.cardio.id)
        assert [i["label"] for i in found["items"]] == ["Q2"]
        again = await api_client.delete(f"{API}/assessment-items/{one['id']}")
        assert again.status_code == 404

        gone = await api_client.delete(f"{API}/assessments/{exam['id']}")
        assert gone.status_code == 204
        assert await module_assessments(api_client, world.cardio.id) == []
        live = await db_session.scalar(
            select(func.count(AssessmentItem.id)).where(AssessmentItem.deleted_at.is_(None))
        )
        assert live == 0
        assert await operations(db_session, "assessments", "curriculum.assessment_delete") == 1

    async def test_deleting_a_module_removes_its_assessments(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        exam = await add_assessment(api_client, world.cardio.id)
        await api_client.post(f"{API}/assessments/{exam['id']}/items", json={"label": "Q1"})

        assert (await api_client.delete(f"{API}/modules/{world.cardio.id}")).status_code == 204

        rows = (await db_session.scalars(select(Assessment))).all()
        assert [a.deleted_at is not None for a in rows] == [True]
        items = (await db_session.scalars(select(AssessmentItem))).all()
        assert [i.deleted_at is not None for i in items] == [True]

    async def test_deleting_a_draft_version_removes_its_assessments(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await add_assessment(api_client, world.cardio.id)

        deleted = await api_client.delete(f"{API}/curriculum-versions/{world.draft.id}")

        assert deleted.status_code == 204
        rows = (await db_session.scalars(select(Assessment))).all()
        assert [a.deleted_at is not None for a in rows] == [True]

    async def test_published_and_archived_versions_are_read_only(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        exam = Assessment(module_id=world.published_module.id, name="Exam")
        await save(db_session, exam)
        item = AssessmentItem(assessment_id=exam.id, label="Q1")
        await save(db_session, item)

        for module in (world.published_module, world.archived_module):
            response = await api_client.post(
                f"{API}/modules/{module.id}/assessments", json={"name": "New"}
            )
            assert response.status_code == 409
        for method, path, body in (
            ("PATCH", f"/assessments/{exam.id}", {"name": "Changed"}),
            ("DELETE", f"/assessments/{exam.id}", None),
            ("POST", f"/assessments/{exam.id}/items", {"label": "Q2"}),
            ("PATCH", f"/assessment-items/{item.id}", {"label": "Changed"}),
            ("DELETE", f"/assessment-items/{item.id}", None),
        ):
            response = await api_client.request(method, f"{API}{path}", json=body)
            assert response.status_code == 409, path
        detail = await api_client.get(f"{API}/modules/{world.published_module.id}")
        assert detail.json()["can_edit_assessments"] is False
        assert [a["name"] for a in detail.json()["assessments"]] == ["Exam"]

    async def test_lists_assessment_methods(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await new_method(db_session, "Portfolio")
        await new_method(db_session, "Hidden", active=False)

        response = await api_client.get(f"{API}/assessment-methods")

        assert response.status_code == 200
        assert [m["label"] for m in response.json()] == ["Portfolio"]

    async def test_module_detail_reports_edit_rights(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        detail = await api_client.get(f"{API}/modules/{world.cardio.id}")
        assert detail.json()["can_edit_assessments"] is True

    async def test_unknown_targets_are_not_found(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        assert (
            await api_client.post(f"{API}/modules/{MISSING}/assessments", json={"name": "x"})
        ).status_code == 404
        assert (await api_client.patch(f"{API}/assessments/{MISSING}", json={})).status_code == 404
        assert (
            await api_client.patch(f"{API}/assessment-items/{MISSING}", json={})
        ).status_code == 404
        assert (
            await api_client.get(f"{API}/modules/{MISSING}/assessable-objectives")
        ).status_code == 404


class TestWhoMayChange:
    async def test_module_coordinator_changes_only_their_module(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        exam = Assessment(module_id=world.anatomy.id, name="Anatomy exam")
        await save(db_session, exam)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "module_coordinator",
            ScopeRef(ScopeType.MODULE, world.cardio.id),
        )

        own = await api_client.post(
            f"{API}/modules/{world.cardio.id}/assessments", json={"name": "Exam"}
        )
        other = await api_client.post(
            f"{API}/modules/{world.anatomy.id}/assessments", json={"name": "Exam"}
        )
        other_edit = await api_client.patch(f"{API}/assessments/{exam.id}", json={"name": "x"})

        assert own.status_code == 201
        # Not even visible to them: not found, not forbidden.
        assert other.status_code == 404
        assert other_edit.status_code == 404

    async def test_lecturer_sees_but_cannot_change(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        exam = Assessment(module_id=world.cardio.id, name="Exam")
        await save(db_session, exam)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.MODULE, world.cardio.id),
        )

        detail = await api_client.get(f"{API}/modules/{world.cardio.id}")
        add = await api_client.post(
            f"{API}/modules/{world.cardio.id}/assessments", json={"name": "New"}
        )
        change = await api_client.patch(f"{API}/assessments/{exam.id}", json={"name": "x"})
        remove = await api_client.delete(f"{API}/assessments/{exam.id}")

        assert detail.status_code == 200
        assert detail.json()["can_edit_assessments"] is False
        assert [a["name"] for a in detail.json()["assessments"]] == ["Exam"]
        assert (add.status_code, change.status_code, remove.status_code) == (403, 403, 403)

    async def test_session_lecturer_does_not_see_the_module_assessments(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        exam = Assessment(module_id=world.cardio.id, name="Exam")
        await save(db_session, exam)
        await sign_in(
            api_client,
            db_session,
            test_settings,
            "lecturer",
            ScopeRef(ScopeType.LEARNING_EVENT, world.lecture.id),
        )

        assert (await api_client.get(f"{API}/modules/{world.cardio.id}")).status_code == 404
        assert (
            await api_client.get(f"{API}/modules/{world.cardio.id}/assessable-objectives")
        ).status_code == 404
        assert (await api_client.patch(f"{API}/assessments/{exam.id}", json={})).status_code == 404


class TestCopying:
    @pytest.fixture(autouse=True)
    async def director(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )

    async def exam_with_item(
        self,
        client: AsyncClient,
        world: World,  # noqa: F811
    ) -> dict[str, Any]:
        exam = await add_assessment(
            client, world.cardio.id, weight="50", timing="Week 8", time_minutes=120
        )
        added = await client.post(
            f"{API}/assessments/{exam['id']}/items",
            json={
                "label": "Q1",
                "marks": "5",
                "objective_ids": [str(world.cardio_outcome.id), str(world.lecture_objective.id)],
            },
        )
        body: dict[str, Any] = added.json()
        return body

    async def test_copying_a_module_copies_assessments_and_links_the_copied_objectives(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await self.exam_with_item(api_client, world)

        response = await api_client.post(
            f"{API}/modules/{world.cardio.id}/copy", json={"code": "HSC202", "name": "Copy"}
        )

        assert response.status_code == 201
        [copy] = await module_assessments(api_client, response.json()["id"])
        assert (copy["name"], copy["weight"], copy["timing"], copy["time_minutes"]) == (
            "Final exam",
            "50.0",
            "Week 8",
            120,
        )
        [item] = copy["items"]
        assert (item["label"], item["marks"]) == ("Q1", "5.0")
        copied_objectives = (
            await db_session.scalars(
                select(Objective.id).where(
                    Objective.id.in_([uuid.UUID(i) for i in item["objective_ids"]]),
                    Objective.id.notin_([world.cardio_outcome.id, world.lecture_objective.id]),
                )
            )
        ).all()
        assert len(item["objective_ids"]) == 2
        assert len(copied_objectives) == 2
        # The original keeps its own links and has no lineage recorded.
        [original] = await module_assessments(api_client, world.cardio.id)
        assert original["items"][0]["objective_ids"] == [
            str(world.cardio_outcome.id),
            str(world.lecture_objective.id),
        ]
        copied = await db_session.get(Assessment, uuid.UUID(copy["id"]))
        assert copied is not None and copied.based_on_id is None

    async def test_copy_forward_records_lineage(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        world: World,  # noqa: F811
    ) -> None:
        await self.exam_with_item(api_client, world)

        response = await api_client.post(
            f"{API}/curriculum-versions/{world.draft.id}/copy-forward",
            json={"academic_year": 2028},
        )

        assert response.status_code == 201
        new_module = await db_session.scalar(
            select(Module).where(Module.based_on_id == world.cardio.id)
        )
        assert new_module is not None
        [copy] = await module_assessments(api_client, new_module.id)
        original = await db_session.scalar(
            select(Assessment).where(Assessment.module_id == world.cardio.id)
        )
        assert original is not None
        copied = await db_session.get(Assessment, uuid.UUID(copy["id"]))
        assert copied is not None and copied.based_on_id == original.id
        item = await db_session.get(AssessmentItem, uuid.UUID(copy["items"][0]["id"]))
        original_item = await db_session.scalar(
            select(AssessmentItem).where(AssessmentItem.assessment_id == original.id)
        )
        assert item is not None and original_item is not None
        assert item.based_on_id == original_item.id
        # The copy assesses the copied objectives, not the originals.
        new_objectives = set(copy["items"][0]["objective_ids"])
        assert len(new_objectives) == 2
        assert not new_objectives & {
            str(world.cardio_outcome.id),
            str(world.lecture_objective.id),
        }

    async def test_the_version_diff_lists_assessment_changes(
        self,
        api_client: AsyncClient,
        world: World,  # noqa: F811
    ) -> None:
        await self.exam_with_item(api_client, world)
        await add_assessment(api_client, world.anatomy.id, name="Practical")
        new_id = (
            await api_client.post(
                f"{API}/curriculum-versions/{world.draft.id}/copy-forward",
                json={"academic_year": 2028},
            )
        ).json()["id"]
        [copied] = [
            a
            for module in (
                await api_client.get(f"{API}/curriculum-versions/{new_id}/structure")
            ).json()["phases"][1]["modules"]
            for a in await module_assessments(api_client, module["id"])
        ]
        await api_client.patch(
            f"{API}/assessments/{copied['id']}", json={"name": "Final OSCE", "weight": "40"}
        )
        await api_client.post(f"{API}/assessments/{copied['id']}/items", json={"label": "Q2"})
        anatomy = (await api_client.get(f"{API}/curriculum-versions/{new_id}/structure")).json()[
            "phases"
        ][0]["modules"][0]
        [practical] = await module_assessments(api_client, anatomy["id"])
        await api_client.delete(f"{API}/assessments/{practical['id']}")
        await add_assessment(api_client, anatomy["id"], name="Portfolio")

        response = await api_client.get(
            f"{API}/curriculum-versions/{new_id}/diff", params={"base": str(world.draft.id)}
        )

        assert response.status_code == 200
        body = response.json()
        changes = [c for c in body["changes"] if c["kind"] == "assessment"]
        assert sorted((c["change"], c["label"]) for c in changes) == [
            ("added", "Portfolio"),
            ("changed", "Final OSCE"),
            ("removed", "Practical"),
        ]
        changed = next(c for c in changes if c["change"] == "changed")
        assert changed["context"] == f"HSC201 {world.cardio.name}"
        assert {f["field"]: (f["before"], f["after"]) for f in changed["fields"]} == {
            "name": ("Final exam", "Final OSCE"),
            "weight": ("50", "40"),
            "items": (1, 2),
        }
        assert body["summary"]["assessment"] == {"added": 1, "removed": 1, "changed": 1}


class TestMethodsInUse:
    async def test_a_method_in_use_cannot_be_deleted(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,  # noqa: F811
    ) -> None:
        method = await new_method(db_session)
        await sign_in(
            api_client, db_session, test_settings, "programme_director", programme_scope(world)
        )
        await add_assessment(api_client, world.cardio.id, method_value_id=str(method.id))
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

        response = await api_client.delete(f"{API}/tag-values/{method.id}")

        assert response.status_code == 409
