"""Tests for core models: institution, faculty, department and user."""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Faculty, Institution, User
from tests.factories import (
    DepartmentFactory,
    FacultyFactory,
    InstitutionFactory,
    UserFactory,
)


class TestCoreColumns:
    """Columns shared by every table via CoreModel."""

    async def test_defaults_are_populated_on_insert(self, db_session: AsyncSession) -> None:
        institution = InstitutionFactory()
        db_session.add(institution)
        await db_session.flush()

        assert isinstance(institution.id, uuid.UUID)
        assert institution.created_at is not None
        assert institution.updated_at is not None
        assert institution.created_at.tzinfo is not None
        assert institution.created_by_id is None
        assert institution.deleted_at is None

    async def test_server_defaults_apply_to_raw_inserts(self, db_session: AsyncSession) -> None:
        institution = Institution(name="Raw Insert University", short_code="RAW")
        db_session.add(institution)
        await db_session.flush()

        assert institution.country == "ZA"
        assert institution.settings == {}

    async def test_updated_at_is_readable_after_update(self, db_session: AsyncSession) -> None:
        institution = InstitutionFactory()
        db_session.add(institution)
        await db_session.flush()

        institution.name = "Renamed University"
        await db_session.flush()

        # Eager defaults fetch the new value with RETURNING; no lazy load needed.
        assert institution.updated_at >= institution.created_at

    async def test_created_by_is_cleared_when_user_is_removed(
        self, db_session: AsyncSession
    ) -> None:
        creator = UserFactory()
        db_session.add(creator)
        await db_session.flush()
        institution = InstitutionFactory(created_by_id=creator.id)
        db_session.add(institution)
        await db_session.flush()

        await db_session.execute(delete(User).where(User.id == creator.id))
        await db_session.refresh(institution)

        assert institution.created_by_id is None


class TestSoftDelete:
    async def test_soft_delete_and_restore(self, db_session: AsyncSession) -> None:
        institution = InstitutionFactory()
        db_session.add(institution)
        await db_session.flush()

        institution.soft_delete()
        await db_session.flush()
        assert institution.is_deleted
        assert institution.deleted_at is not None

        institution.restore()
        await db_session.flush()
        assert not institution.is_deleted


class TestOrganisation:
    async def test_hierarchy_loads_with_explicit_eager_loading(
        self, db_session: AsyncSession
    ) -> None:
        department = DepartmentFactory()
        db_session.add(department)
        await db_session.flush()
        institution_id = department.faculty.institution.id
        db_session.expunge_all()

        result = await db_session.execute(
            select(Institution)
            .where(Institution.id == institution_id)
            .options(selectinload(Institution.faculties).selectinload(Faculty.departments))
        )
        institution = result.scalar_one()

        assert [f.code for f in institution.faculties] == [department.faculty.code]
        assert [d.code for d in institution.faculties[0].departments] == [department.code]

    async def test_relationships_refuse_implicit_lazy_loading(
        self, db_session: AsyncSession
    ) -> None:
        faculty = FacultyFactory()
        db_session.add(faculty)
        await db_session.flush()
        institution_id = faculty.institution.id
        db_session.expunge_all()

        institution = await db_session.get(Institution, institution_id)
        assert institution is not None
        with pytest.raises(InvalidRequestError):
            _ = institution.faculties

    async def test_faculty_code_unique_within_institution(self, db_session: AsyncSession) -> None:
        institution = InstitutionFactory()
        db_session.add(FacultyFactory(institution=institution, code="HS"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(FacultyFactory(institution=institution, code="HS"))

    async def test_faculty_code_may_repeat_across_institutions(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add_all([FacultyFactory(code="HS"), FacultyFactory(code="HS")])
        await db_session.flush()

    async def test_department_code_unique_within_faculty(self, db_session: AsyncSession) -> None:
        faculty = FacultyFactory()
        db_session.add(DepartmentFactory(faculty=faculty, code="PHYS"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(DepartmentFactory(faculty=faculty, code="PHYS"))

    async def test_institution_with_faculties_cannot_be_hard_deleted(
        self, db_session: AsyncSession
    ) -> None:
        faculty = FacultyFactory()
        db_session.add(faculty)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    delete(Institution).where(Institution.id == faculty.institution_id)
                )


class TestUser:
    async def test_defaults(self, db_session: AsyncSession) -> None:
        user = UserFactory()
        db_session.add(user)
        await db_session.flush()

        assert user.is_active
        assert user.last_login_at is None

    async def test_email_unique_regardless_of_case(self, db_session: AsyncSession) -> None:
        db_session.add(UserFactory(email="Lecturer@Example.test"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(UserFactory(email="lecturer@example.TEST"))

    def test_repr_does_not_expose_personal_data(self) -> None:
        user = UserFactory(id=uuid.uuid4(), email="someone@example.test")

        assert "someone" not in repr(user)
        assert "Demo User" not in repr(user)
