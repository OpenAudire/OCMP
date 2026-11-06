"""Tests for removing the demo data: only the demo's own, a dry run changes nothing."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.loader import load_data, load_demo
from app.demo.remover import remove_demo
from app.models import (
    AuditLog,
    CurriculumVersion,
    Faculty,
    Framework,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Programme,
    TagList,
)
from app.services.mapping_live import live_link
from tests.factories import FacultyFactory, ProgrammeFactory


async def count(db: AsyncSession, model: type, *where: object) -> int:
    query = select(func.count()).select_from(model)
    for condition in where:
        query = query.where(condition)  # type: ignore[arg-type]
    return int(await db.scalar(query) or 0)


async def live_counts(db: AsyncSession) -> dict[str, int]:
    return {
        "programmes": await count(db, Programme, Programme.deleted_at.is_(None)),
        "versions": await count(db, CurriculumVersion, CurriculumVersion.deleted_at.is_(None)),
        "modules": await count(db, Module, Module.deleted_at.is_(None)),
        "events": await count(db, LearningEvent, LearningEvent.deleted_at.is_(None)),
        "objectives": await count(db, Objective, Objective.deleted_at.is_(None)),
        "links": await count(db, MappingLink, live_link()),
        "frameworks": await count(db, Framework, Framework.deleted_at.is_(None)),
        "lists": await count(db, TagList, TagList.deleted_at.is_(None)),
        "faculties": await count(db, Faculty, Faculty.deleted_at.is_(None)),
    }


@pytest.mark.usefixtures("system_roles")
class TestRemoveDemo:
    async def test_a_dry_run_lists_everything_and_changes_nothing(
        self, db_session: AsyncSession
    ) -> None:
        await load_demo(db_session)
        before = await live_counts(db_session)
        audit_before = await count(db_session, AuditLog)

        report = await remove_demo(db_session)

        assert await live_counts(db_session) == before
        assert await count(db_session, AuditLog) == audit_before
        text = "\n".join(report.removed)
        assert "programme BHS-DEMO with 2 versions" in text
        assert "faculty FHS-DEMO" in text and "framework" in text
        assert "tag list teaching-methods" in text

    async def test_the_demo_can_be_loaded_again_after_it_was_removed(
        self, db_session: AsyncSession
    ) -> None:
        """Removing the demo soft-deletes its faculty; loading it again must not clash with the
        deleted rows (codes are unique among live rows only)."""
        await load_demo(db_session)
        first = await live_counts(db_session)
        await remove_demo(db_session, apply=True)

        await load_demo(db_session)

        assert await live_counts(db_session) == first

    async def test_applying_removes_the_demo_and_leaves_the_rest_untouched(
        self, db_session: AsyncSession
    ) -> None:
        other_faculty = FacultyFactory()
        other = ProgrammeFactory(faculty=other_faculty, code="REAL-1")
        db_session.add_all([other_faculty, other])
        await db_session.flush()
        await load_demo(db_session)

        report = await remove_demo(db_session, apply=True)

        counts = await live_counts(db_session)
        assert counts["programmes"] == 1  # the real programme stays
        assert counts["versions"] == counts["modules"] == counts["events"] == 0
        assert counts["objectives"] == counts["links"] == 0
        assert counts["frameworks"] == 0 and counts["lists"] == 0
        assert counts["faculties"] == 1  # only the other faculty is left
        assert not report.kept
        removed = await db_session.get(Programme, other.id)
        assert removed is not None and removed.deleted_at is None
        # It is audited, as an operation named for it.
        operations = {
            row.context.get("operation")
            for row in await db_session.scalars(select(AuditLog))
            if row.context
        }
        assert "demo.remove" in operations

    async def test_a_second_run_finds_nothing(self, db_session: AsyncSession) -> None:
        await load_demo(db_session)
        await remove_demo(db_session, apply=True)

        report = await remove_demo(db_session, apply=True)

        assert report.nothing

    async def test_a_faculty_with_other_programmes_is_kept(self, db_session: AsyncSession) -> None:
        await load_demo(db_session)
        faculty = await db_session.scalar(
            select(Faculty).where(Faculty.code == load_data().faculty.code)
        )
        assert faculty is not None
        db_session.add(ProgrammeFactory(faculty=faculty, code="REAL-2"))
        await db_session.flush()

        report = await remove_demo(db_session, apply=True)

        assert any("faculty FHS-DEMO" in line for line in report.kept)
        assert (await db_session.get(Faculty, faculty.id)).deleted_at is None  # type: ignore[union-attr]

    async def test_nothing_is_removed_when_there_was_no_demo(
        self, db_session: AsyncSession
    ) -> None:
        report = await remove_demo(db_session, apply=True)

        assert report.nothing and not report.kept
