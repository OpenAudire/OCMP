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

        # Counts from the brief.
        assert (summary.modules, summary.learning_events, summary.objectives) == (3, 20, 60)
        assert (summary.framework_items, summary.mappings, summary.tag_lists) == (8, 13, 3)
        assert await count(db_session, Module) == 3
        assert await count(db_session, Module, Module.phase_id.is_(None)) == 1  # longitudinal
        assert await count(db_session, LearningEvent) == 20
        by_level = {
            level: await count(db_session, Objective, Objective.level == level)
            for level in ObjectiveLevel
        }
        assert by_level == {
            ObjectiveLevel.PROGRAMME: 6,
            ObjectiveLevel.MODULE: 12,
            ObjectiveLevel.LEARNING_EVENT: 42,
        }

        # Published version; every non-programme objective linked upward and classified.
        version = (await db_session.execute(select(CurriculumVersion))).scalar_one()
        assert version.status == VersionStatus.PUBLISHED
        assert await count(db_session, ObjectiveLink) == summary.objective_links
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
        assert await count(db_session, Tagging, Tagging.module_id.is_not(None)) == 6
        assert await count(db_session, Tagging, Tagging.learning_event_id.is_not(None)) > 0
        accepted = MappingLink.status == MappingStatus.ACCEPTED
        assert await count(db_session, MappingLink, accepted) == 13
        framework = (await db_session.execute(select(Framework))).scalar_one()
        assert framework.status == FrameworkStatus.ACTIVE

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
        assert await count(db_session, Module) == 3

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
