"""factory_boy factories for models.

Factories build unsaved instances; add them to an ``AsyncSession`` and flush.
Test data is fictional: emails use the reserved ``.test`` domain.
"""

import factory

from app.models import (
    CurriculumVersion,
    Department,
    Faculty,
    Institution,
    LearningEvent,
    Module,
    Phase,
    Programme,
    User,
)


class InstitutionFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Institution

    name = factory.Sequence(lambda n: f"Demo University {n}")
    short_code = factory.Sequence(lambda n: f"DU{n}")
    country = "ZA"
    settings = factory.LazyFunction(dict)


class FacultyFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Faculty

    institution = factory.SubFactory(InstitutionFactory)
    code = factory.Sequence(lambda n: f"FAC{n}")
    name = factory.Sequence(lambda n: f"Faculty of Demo Studies {n}")


class DepartmentFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Department

    faculty = factory.SubFactory(FacultyFactory)
    code = factory.Sequence(lambda n: f"DEP{n}")
    name = factory.Sequence(lambda n: f"Department of Demo {n}")


class UserFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    display_name = factory.Sequence(lambda n: f"Demo User {n}")
    is_active = True


class ProgrammeFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Programme

    faculty = factory.SubFactory(FacultyFactory)
    code = factory.Sequence(lambda n: f"PRG{n}")
    name = factory.Sequence(lambda n: f"BSc Health Sciences (Demo) {n}")
    nqf_exit_level = 7
    total_credits = 360


class CurriculumVersionFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = CurriculumVersion

    programme = factory.SubFactory(ProgrammeFactory)
    academic_year = factory.Sequence(lambda n: 2027 + n)


class PhaseFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Phase

    version = factory.SubFactory(CurriculumVersionFactory)
    name = factory.Sequence(lambda n: f"Year {n + 1}")
    position = factory.Sequence(lambda n: n)


class ModuleFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = Module

    version = factory.SubFactory(CurriculumVersionFactory)
    code = factory.Sequence(lambda n: f"MOD{n:03d}")
    name = factory.Sequence(lambda n: f"Demo Module {n}")
    credits = 12
    nqf_level = 5


class LearningEventFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = LearningEvent

    module = factory.SubFactory(ModuleFactory)
    title = factory.Sequence(lambda n: f"Demo session {n}")
    contact_minutes = 90
    self_study_minutes = 120
