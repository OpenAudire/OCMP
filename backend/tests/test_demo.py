"""Tests for the demo dataset."""

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.loader import load_data, load_demo
from app.models import (
    AuditLog,
    CurriculumVersion,
    Framework,
    Institution,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    ObjectiveLink,
    Tagging,
    TagList,
)
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.framework import FrameworkStatus
from app.models.mapping import MappingStatus
from app.services.authorization import ConflictError
from app.services.curriculum_diff import Change, ItemKind, diff_versions
from tests.factories import InstitutionFactory


async def count(db: AsyncSession, model: type, *where: object) -> int:
    query = select(func.count()).select_from(model)
    for condition in where:
        query = query.where(condition)  # type: ignore[arg-type]
    return int(await db.scalar(query) or 0)


@pytest.fixture(scope="module")
def data() -> Iterator[object]:
    yield load_data()


class TestData:
    def test_matches_the_brief(self) -> None:
        data = load_data()

        assert data.programme.name == "BSc Health Sciences (Demo)"
        assert len(data.modules) == 3
        assert sum(len(m.events) for m in data.modules) == 20
        objectives = len(data.programme.outcomes) + sum(
            len(m.outcomes) + sum(len(e.objectives) for e in m.events) for m in data.modules
        )
        assert objectives == 60

    def test_every_objective_has_domain_and_level(self) -> None:
        data = load_data()
        objectives = list(data.programme.outcomes)
        for module in data.modules:
            objectives += module.outcomes
            for event in module.events:
                objectives += event.objectives

        assert all(o.domain and o.level for o in objectives)


@pytest.mark.usefixtures("system_roles")
class TestLoad:
    async def test_loads_a_complete_linked_curriculum(self, db_session: AsyncSession) -> None:
        """One load, checked from every side (each load takes seconds)."""
        summary = await load_demo(db_session)

        # Counts from the brief, in the published version.
        assert (summary.modules, summary.learning_events, summary.objectives) == (3, 20, 60)
        assert (summary.framework_items, summary.mappings, summary.tag_lists) == (8, 13, 3)
        version = (
            await db_session.execute(
                select(CurriculumVersion).where(CurriculumVersion.status == VersionStatus.PUBLISHED)
            )
        ).scalar_one()
        in_version = Module.version_id == version.id
        modules = select(Module.id).where(in_version)
        assert await count(db_session, Module, in_version) == 3
        assert await count(db_session, Module, in_version, Module.phase_id.is_(None)) == 1
        assert await count(db_session, LearningEvent, LearningEvent.module_id.in_(modules)) == 20
        by_level = {
            level: await count(
                db_session, Objective, Objective.level == level, Objective.version_id == version.id
            )
            for level in ObjectiveLevel
        }
        assert by_level == {
            ObjectiveLevel.PROGRAMME: 6,
            ObjectiveLevel.MODULE: 12,
            ObjectiveLevel.LEARNING_EVENT: 42,
        }

        # Every non-programme objective linked upward and classified.
        unlinked = await db_session.scalar(
            select(func.count())
            .select_from(Objective)
            .where(
                Objective.level != ObjectiveLevel.PROGRAMME,
                ~Objective.id.in_(select(ObjectiveLink.child_id)),
            )
        )
        assert unlinked == 0
        assert await count(db_session, Objective, Objective.taxonomy_level_id.is_(None)) == 0
        assert await count(db_session, Objective, Objective.domain.is_(None)) == 0

        # Formats, tags, mappings, active framework.
        assert await count(db_session, LearningEvent, LearningEvent.format_value_id.is_(None)) == 0
        assert await count(db_session, Tagging, Tagging.module_id.in_(modules)) == 6
        assert await count(db_session, Tagging, Tagging.learning_event_id.is_not(None)) > 0
        accepted = MappingLink.status == MappingStatus.ACCEPTED
        published_objectives = select(Objective.id).where(Objective.version_id == version.id)
        assert (
            await count(
                db_session,
                MappingLink,
                accepted,
                MappingLink.objective_id.in_(published_objectives),
            )
            == 13
        )
        framework = (await db_session.execute(select(Framework))).scalar_one()
        assert framework.status == FrameworkStatus.ACTIVE

        # The next year's draft, copied forward and changed.
        draft = (
            await db_session.execute(
                select(CurriculumVersion).where(CurriculumVersion.status == VersionStatus.DRAFT)
            )
        ).scalar_one()
        assert summary.draft_year == draft.academic_year == version.academic_year + 1
        assert draft.based_on_id == version.id
        draft_modules = select(Module.id).where(Module.version_id == draft.id)
        live_events = (
            LearningEvent.module_id.in_(draft_modules),
            LearningEvent.deleted_at.is_(None),
        )
        assert await count(db_session, LearningEvent, *live_events) == 20
        titles = set(await db_session.scalars(select(LearningEvent.title).where(*live_events)))
        assert "Reading and summarising a research paper" in titles
        assert "The nervous system" in titles
        assert "Portfolio reflection" not in titles
        assert await count(db_session, MappingLink, accepted) == 26
        diff = await diff_versions(db_session, version, draft)
        assert {(c.kind, c.change) for c in diff.changes} == {
            (ItemKind.LEARNING_EVENT, Change.CHANGED),
            (ItemKind.LEARNING_EVENT, Change.ADDED),
            (ItemKind.LEARNING_EVENT, Change.REMOVED),
            (ItemKind.OBJECTIVE, Change.ADDED),
            (ItemKind.OBJECTIVE, Change.REMOVED),
            (ItemKind.OBJECTIVE, Change.CHANGED),
        }
        assert diff.count(ItemKind.LEARNING_EVENT, Change.CHANGED) == 2

        # A bare install gets the demo institution, with the health profile.
        institution = (await db_session.execute(select(Institution))).scalar_one()
        assert institution.short_code == "DEMO-UNI"
        assert "health" in institution.settings["profiles"]

        # Recorded in the audit log as one operation.
        demo_entries = await count(
            db_session, AuditLog, AuditLog.context["operation"].astext == "demo.load"
        )
        assert demo_entries > 100

        # Loading again is refused and changes nothing.
        with pytest.raises(ConflictError, match="already loaded"):
            await load_demo(db_session)
        assert await count(db_session, Module) == 6

    async def test_adds_the_draft_to_an_earlier_load(self, db_session: AsyncSession) -> None:
        """Installs that loaded the demo before it had a draft get the draft added."""
        await load_demo(db_session)
        draft = (
            await db_session.execute(
                select(CurriculumVersion).where(CurriculumVersion.status == VersionStatus.DRAFT)
            )
        ).scalar_one()
        draft.soft_delete()
        await db_session.flush()

        summary = await load_demo(db_session)

        assert summary.draft_only is True
        drafts = await count(
            db_session,
            CurriculumVersion,
            CurriculumVersion.status == VersionStatus.DRAFT,
            CurriculumVersion.deleted_at.is_(None),
        )
        assert drafts == 1
        assert summary.draft_year == draft.academic_year

    async def test_uses_the_existing_institution(self, db_session: AsyncSession) -> None:
        mine = InstitutionFactory(name="My University", short_code="MINE")
        db_session.add(mine)
        await db_session.flush()

        await load_demo(db_session)

        assert await count(db_session, Institution) == 1

    async def test_reuses_existing_tag_lists_and_framework(self, db_session: AsyncSession) -> None:
        await load_demo(db_session)
        programme = (await db_session.execute(select(Module.version_id))).scalars().first()
        assert programme is not None
        # Remove the programme (soft delete) and load again.
        from app.models import Programme

        for p in (await db_session.execute(select(Programme))).scalars():
            p.soft_delete()
        await db_session.flush()

        await load_demo(db_session)

        assert await count(db_session, Framework) == 1
        assert await count(db_session, TagList) == 3
