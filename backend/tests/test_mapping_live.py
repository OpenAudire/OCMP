"""Mapping links go with their objective, come back with it, and deleted ones never count
(ADR 043)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    CurriculumVersion,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
)
from app.models.mapping import MappingSource, MappingStatus
from app.services.audit import audit_operation
from app.services.curriculum import add_objective
from app.services.curriculum_edit import delete_event, delete_module
from app.services.curriculum_objectives import delete_objective, restore_objective
from app.services.curriculum_versions import copy_forward, delete_draft, forward_preview
from app.services.frameworks import add_item
from app.services.mapping_live import clean_orphan_links, live_link, orphan_links
from tests.authz_helpers import new_user
from tests.factories import FrameworkFactory, LearningEventFactory


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


def link(objective: Objective, item: FrameworkItem) -> MappingLink:
    return MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=MappingSource.IMPORT,
        status=MappingStatus.SUGGESTED,
    )


class World:
    def __init__(self, event: LearningEvent, items: list[FrameworkItem]) -> None:
        self.event = event
        self.module: Module = event.module
        self.version: CurriculumVersion = event.module.version
        self.items = items


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    event = LearningEventFactory()
    framework = FrameworkFactory()
    await save(db_session, event, framework)
    items = [await add_item(db_session, framework, code=f"C{n}", title=f"C {n}") for n in range(3)]
    return World(event, items)


async def linked(db: AsyncSession, w: World, owner: object, text: str, *items: int) -> Objective:
    objective = await add_objective(db, owner, text)  # type: ignore[arg-type]
    await save(db, *[link(objective, w.items[n]) for n in items])
    return objective


async def live_count(db: AsyncSession, objective: Objective) -> int:
    return int(
        await db.scalar(
            select(func.count(MappingLink.id)).where(
                MappingLink.objective_id == objective.id, live_link()
            )
        )
        or 0
    )


async def all_links(db: AsyncSession, objective: Objective) -> list[MappingLink]:
    rows = await db.scalars(select(MappingLink).where(MappingLink.objective_id == objective.id))
    result = list(rows)
    for row in result:
        await db.refresh(row)
    return result


class TestDeletingGoesWithTheObjective:
    async def test_direct_delete_soft_deletes_the_links_under_one_label(
        self, db_session: AsyncSession, world: World
    ) -> None:
        objective = await linked(db_session, world, world.module, "Describe.", 0, 1)

        with audit_operation("curriculum.objective_delete"):
            await delete_objective(db_session, objective, world.version)

        links = await all_links(db_session, objective)
        assert len(links) == 2
        assert {row.deleted_at for row in links} == {objective.deleted_at}
        assert await live_count(db_session, objective) == 0
        logged = list(
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "mapping_links",
                    AuditLog.action == "soft_delete",
                    AuditLog.entity_id.in_([row.id for row in links]),
                )
            )
        )
        assert len(logged) == 2
        assert {row.context["operation"] for row in logged} == {"curriculum.objective_delete"}

    async def test_deleting_a_session_a_module_or_a_draft_version_cascades(
        self, db_session: AsyncSession, world: World
    ) -> None:
        in_event = await linked(db_session, world, world.event, "Session aim.", 0)
        in_module = await linked(db_session, world, world.module, "Module aim.", 1)
        in_version = await linked(db_session, world, world.version, "Programme aim.", 2)
        other = LearningEventFactory(module=world.module)
        await save(db_session, other)
        in_other_event = await linked(db_session, world, other, "Other session aim.", 0)

        await delete_event(db_session, other, world.version)
        assert await live_count(db_session, in_other_event) == 0
        assert await live_count(db_session, in_event) == 1

        await delete_module(db_session, world.module, world.version)
        assert await live_count(db_session, in_event) == 0
        assert await live_count(db_session, in_module) == 0
        assert await live_count(db_session, in_version) == 1

        await delete_draft(db_session, world.version)
        assert await live_count(db_session, in_version) == 0
        assert await orphan_links(db_session) == []

    async def test_a_link_a_person_removed_is_gone_and_not_restored(
        self, db_session: AsyncSession, world: World
    ) -> None:
        objective = await linked(db_session, world, world.module, "Describe.", 0, 1)
        removed = (await all_links(db_session, objective))[0]
        await db_session.delete(removed)
        await db_session.flush()

        await delete_objective(db_session, objective, world.version)
        await restore_objective(db_session, objective, world.version)

        assert objective.deleted_at is None
        assert await live_count(db_session, objective) == 1


class TestRestoring:
    async def test_restores_only_the_links_deleted_with_the_objective(
        self, db_session: AsyncSession, world: World
    ) -> None:
        objective = await linked(db_session, world, world.module, "Describe.", 0, 1)
        earlier = (await all_links(db_session, objective))[0]
        earlier.deleted_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.flush()
        await delete_objective(db_session, objective, world.version)

        with audit_operation("curriculum.objective_restore"):
            await restore_objective(db_session, objective, world.version)

        assert objective.deleted_at is None
        assert await live_count(db_session, objective) == 1
        await db_session.refresh(earlier)
        assert earlier.deleted_at is not None
        restores = list(
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "mapping_links", AuditLog.action == "restore"
                )
            )
        )
        assert len(restores) == 1
        assert restores[0].context["operation"] == "curriculum.objective_restore"

    async def test_a_pair_that_is_live_again_is_not_restored(
        self, db_session: AsyncSession, world: World
    ) -> None:
        objective = await linked(db_session, world, world.module, "Describe.", 0)
        await delete_objective(db_session, objective, world.version)
        # Collision rule: one live link per pair, so a newer live link wins.
        await save(db_session, link(objective, world.items[0]))

        await restore_objective(db_session, objective, world.version)

        assert await live_count(db_session, objective) == 1
        assert len(await all_links(db_session, objective)) == 2


class TestTheOnePairRule:
    async def test_a_deleted_link_does_not_block_a_new_one_but_two_live_ones_do(
        self, db_session: AsyncSession, world: World
    ) -> None:
        objective = await linked(db_session, world, world.module, "Describe.", 0)
        first = (await all_links(db_session, objective))[0]
        first.deleted_at = datetime.now(UTC)
        await db_session.flush()

        await save(db_session, link(objective, world.items[0]))  # allowed

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await save(db_session, link(objective, world.items[0]))


class TestReadsLeaveDeletedLinksOut:
    async def test_forward_preview_and_copy_forward_skip_them(
        self, db_session: AsyncSession, world: World
    ) -> None:
        kept = await linked(db_session, world, world.module, "Kept.", 0)
        gone = await linked(db_session, world, world.module, "Gone.", 1, 2)
        await delete_objective(db_session, gone, world.version)
        extra = link(kept, world.items[1])
        await save(db_session, extra)
        extra.deleted_at = datetime.now(UTC)
        await db_session.flush()
        actor = await new_user(db_session)

        preview = await forward_preview(db_session, actor, world.version)
        assert preview.mappings == 1  # only kept -> C0

        copied = await copy_forward(
            db_session, actor, world.version, academic_year=world.version.academic_year + 1
        )
        count = await db_session.scalar(
            select(func.count(MappingLink.id))
            .join(Objective, Objective.id == MappingLink.objective_id)
            .where(Objective.version_id == copied.id)
        )
        assert count == 1


class TestCleaningUpOrphans:
    async def test_dry_run_changes_nothing_and_apply_soft_deletes_with_a_label(
        self, db_session: AsyncSession, world: World
    ) -> None:
        # An orphan as old installs have them: the objective deleted, its links left live.
        objective = await linked(db_session, world, world.module, "Old.", 0, 1)
        objective.soft_delete()
        live = await linked(db_session, world, world.module, "Live.", 2)
        await db_session.flush()

        assert await clean_orphan_links(db_session, apply=False) == 2
        assert len(await orphan_links(db_session)) == 2

        with audit_operation("mapping.orphan_cleanup"):
            assert await clean_orphan_links(db_session, apply=True) == 2

        assert await orphan_links(db_session) == []
        assert await clean_orphan_links(db_session, apply=True) == 0
        assert await live_count(db_session, live) == 1
        rows = await all_links(db_session, objective)
        assert {row.deleted_at for row in rows} == {objective.deleted_at}
        logged = await db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "mapping_links",
                AuditLog.context["operation"].astext == "mapping.orphan_cleanup",
            )
        )
        assert len(list(logged)) == 2
        # The cleaned links come back with the objective, like any other.
        await restore_objective(db_session, objective, world.version)
        assert await live_count(db_session, objective) == 2
