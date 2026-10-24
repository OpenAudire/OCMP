"""factory_boy factories for models.

Factories build unsaved instances; add them to an ``AsyncSession`` and flush.
Test data is fictional: emails use the reserved ``.test`` domain.
"""

import factory

from app.models import Department, Faculty, Institution, User


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
