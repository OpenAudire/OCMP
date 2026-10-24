"""Tests for the curriculum models, their rules and their authorization scopes."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import Permission, ScopeType
from app.models import (
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    Programme,
    QualificationType,
)
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, PhaseKind, VersionStatus
from app.services.authorization import (
    INSTANCE,
    InvalidRequestError,
    ScopeRef,
    has_permission,
    lineage,
)
from app.services.curriculum import ConflictError, add_objective, link_objectives
from tests.authz_helpers import grant, new_user
from tests.factories import (
    CurriculumVersionFactory,
    LearningEventFactory,
    ModuleFactory,
    PhaseFactory,
    ProgrammeFactory,
)

# Objects rejected by the database in `must_fail` stay in their parent's in-memory
# collection after the savepoint rolls back; SQLAlchemy then warns it will not save them.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Object of type .* not in session:sqlalchemy.exc.SAWarning"
)


async def save(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    await db.flush()


async def must_fail(db: AsyncSession, *objects: object) -> None:
    """Adding these must violate a database constraint."""
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add_all(objects)
            await db.flush()


class TestQualificationTypes:
    async def test_heqsf_defaults_are_seeded(self, db_session: AsyncSession) -> None:
        rows = {
            q.key: (q.nqf_exit_level, q.min_total_credits)
            for q in (await db_session.execute(select(QualificationType))).scalars()
        }

        assert rows["bachelors"] == (7, 360)
        assert rows["bachelors_professional"] == (8, 480)
        assert rows["doctoral"] == (10, 360)
        assert len(rows) == 10

    async def test_seeded_values_say_they_need_verification(self, db_session: AsyncSession) -> None:
        notes = (await db_session.execute(select(QualificationType.notes))).scalars()

        assert all("verify" in note for note in notes)


class TestStructure:
    async def test_full_tree_loads(self, db_session: AsyncSession) -> None:
        version = CurriculumVersionFactory()
        year_one = PhaseFactory(version=version, name="Year 1", kind=PhaseKind.YEAR)
        module = ModuleFactory(version=version, phase_id=None)
        event = LearningEventFactory(module=module)
        await save(db_session, version, year_one, module, event)
        module.phase_id = year_one.id
        await db_session.flush()
        db_session.expunge_all()

        loaded = (
            await db_session.execute(
                select(CurriculumVersion)
                .where(CurriculumVersion.id == version.id)
                .options(
                    selectinload(CurriculumVersion.phases),
                    selectinload(CurriculumVersion.modules).selectinload(Module.learning_events),
                )
            )
        ).scalar_one()

        assert loaded.status == VersionStatus.DRAFT
        assert [p.name for p in loaded.phases] == ["Year 1"]
        assert loaded.modules[0].phase_id == year_one.id
        assert loaded.modules[0].learning_events[0].contact_minutes == 90

    async def test_longitudinal_module_has_no_phase(self, db_session: AsyncSession) -> None:
        module = ModuleFactory(phase_id=None, credits=Decimal("7.5"))
        await save(db_session, module)

        assert module.phase_id is None
        assert module.credits == Decimal("7.5")

    async def test_module_phase_must_be_in_same_version(self, db_session: AsyncSession) -> None:
        phase = PhaseFactory()
        other_version = CurriculumVersionFactory(programme=phase.version.programme)
        await save(db_session, phase, other_version)

        await must_fail(db_session, ModuleFactory(version=other_version, phase_id=phase.id))

    async def test_programme_codes_unique_per_faculty_among_live_rows(
        self, db_session: AsyncSession
    ) -> None:
        first = ProgrammeFactory(code="BHS")
        await save(db_session, first)

        await must_fail(db_session, ProgrammeFactory(faculty=first.faculty, code="BHS"))

        first.soft_delete()
        await db_session.flush()
        await save(db_session, ProgrammeFactory(faculty=first.faculty, code="BHS"))

    async def test_one_version_per_programme_and_year(self, db_session: AsyncSession) -> None:
        version = CurriculumVersionFactory(academic_year=2027)
        await save(db_session, version)

        await must_fail(
            db_session, CurriculumVersionFactory(programme=version.programme, academic_year=2027)
        )

    async def test_version_copied_forward(self, db_session: AsyncSession) -> None:
        old = CurriculumVersionFactory(academic_year=2027)
        await save(db_session, old)
        new = CurriculumVersionFactory(
            programme=old.programme, academic_year=2028, based_on_id=old.id
        )
        await save(db_session, new)

        assert new.based_on_id == old.id

    async def test_module_codes_unique_per_version(self, db_session: AsyncSession) -> None:
        module = ModuleFactory(code="ANAT101")
        await save(db_session, module)

        await must_fail(db_session, ModuleFactory(version=module.version, code="ANAT101"))

    @pytest.mark.parametrize(
        "make",
        [
            lambda: ProgrammeFactory(nqf_exit_level=11),
            lambda: ProgrammeFactory(total_credits=-1),
            lambda: ProgrammeFactory(minimum_duration_years=Decimal(0)),
            lambda: CurriculumVersionFactory(academic_year=1800),
            lambda: ModuleFactory(nqf_level=0),
            lambda: ModuleFactory(credits=Decimal(-5)),
            lambda: LearningEventFactory(contact_minutes=-1),
            lambda: LearningEventFactory(self_study_minutes=-10),
            lambda: LearningEventFactory(week=-1),
        ],
        ids=[
            "nqf-exit-level",
            "programme-credits",
            "duration",
            "academic-year",
            "module-nqf",
            "module-credits",
            "contact-minutes",
            "self-study",
            "week",
        ],
    )
    async def test_value_ranges(self, db_session: AsyncSession, make) -> None:  # type: ignore[no-untyped-def]
        await must_fail(db_session, make())

    async def test_status_values_are_checked_in_database(self, db_session: AsyncSession) -> None:
        programme = ProgrammeFactory()
        await save(db_session, programme)

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    text("UPDATE programmes SET status = 'bogus' WHERE id = :id"),
                    {"id": programme.id},
                )

    async def test_deleting_a_version_removes_its_contents(self, db_session: AsyncSession) -> None:
        version = CurriculumVersionFactory()
        phase = PhaseFactory(version=version)
        module = ModuleFactory(version=version)
        event = LearningEventFactory(module=module)
        await save(db_session, version, phase, module, event)
        await add_objective(db_session, event, "Describe the cardiac cycle.")
        await db_session.flush()

        await db_session.execute(
            delete(CurriculumVersion).where(CurriculumVersion.id == version.id)
        )

        for model in (Module, LearningEvent, Objective):
            assert (await db_session.execute(select(model))).first() is None

    async def test_programme_with_versions_cannot_be_hard_deleted(
        self, db_session: AsyncSession
    ) -> None:
        version = CurriculumVersionFactory()
        await save(db_session, version)

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    delete(Programme).where(Programme.id == version.programme_id)
                )


class TestObjectives:
    @pytest.fixture
    async def tree(
        self, db_session: AsyncSession
    ) -> tuple[CurriculumVersion, Module, LearningEvent]:
        version = CurriculumVersionFactory()
        module = ModuleFactory(version=version)
        event = LearningEventFactory(module=module)
        await save(db_session, version, module, event)
        return version, module, event

    async def test_level_and_version_follow_owner(
        self, db_session: AsyncSession, tree: tuple[CurriculumVersion, Module, LearningEvent]
    ) -> None:
        version, module, event = tree

        programme_outcome = await add_objective(db_session, version, "  Practise ethically.  ")
        module_outcome = await add_objective(
            db_session, module, "Explain homeostasis.", domain=ObjectiveDomain.KNOWLEDGE
        )
        session_objective = await add_objective(db_session, event, "Measure blood pressure.")

        assert (programme_outcome.level, programme_outcome.text) == (
            ObjectiveLevel.PROGRAMME,
            "Practise ethically.",
        )
        assert (module_outcome.level, module_outcome.module_id) == (
            ObjectiveLevel.MODULE,
            module.id,
        )
        assert session_objective.learning_event_id == event.id
        assert {o.version_id for o in (programme_outcome, module_outcome, session_objective)} == {
            version.id
        }
        assert session_objective.quality_flags == []

    async def test_blank_text_and_deleted_owner_rejected(
        self, db_session: AsyncSession, tree: tuple[CurriculumVersion, Module, LearningEvent]
    ) -> None:
        _, module, event = tree

        with pytest.raises(InvalidRequestError, match="empty"):
            await add_objective(db_session, module, "   ")
        event.soft_delete()
        with pytest.raises(InvalidRequestError, match="deleted"):
            await add_objective(db_session, event, "Anything.")

    async def test_owner_must_match_level_in_database(
        self, db_session: AsyncSession, tree: tuple[CurriculumVersion, Module, LearningEvent]
    ) -> None:
        version, module, _ = tree

        await must_fail(
            db_session,
            Objective(
                version_id=version.id,
                level=ObjectiveLevel.PROGRAMME,
                module_id=module.id,
                text="Inconsistent owner.",
            ),
        )

    async def test_upward_links(
        self, db_session: AsyncSession, tree: tuple[CurriculumVersion, Module, LearningEvent]
    ) -> None:
        version, module, event = tree
        programme_outcome = await add_objective(db_session, version, "Communicate effectively.")
        module_outcome = await add_objective(db_session, module, "Take a patient history.")
        session_objective = await add_objective(db_session, event, "Use open questions.")

        await link_objectives(db_session, session_objective, module_outcome)
        await link_objectives(db_session, module_outcome, programme_outcome)
        await link_objectives(db_session, session_objective, programme_outcome)

        loaded = (
            await db_session.execute(
                select(Objective)
                .where(Objective.id == session_objective.id)
                .options(selectinload(Objective.parent_links))
            )
        ).scalar_one()
        assert {link.parent_id for link in loaded.parent_links} == {
            module_outcome.id,
            programme_outcome.id,
        }

    async def test_link_rules(
        self, db_session: AsyncSession, tree: tuple[CurriculumVersion, Module, LearningEvent]
    ) -> None:
        version, module, event = tree
        programme_outcome = await add_objective(db_session, version, "Programme outcome.")
        module_outcome = await add_objective(db_session, module, "Module outcome.")
        session_objective = await add_objective(db_session, event, "Session objective.")

        other_module = ModuleFactory(version=version)
        other_version = CurriculumVersionFactory(programme=version.programme)
        await save(db_session, other_module, other_version)
        other_module_outcome = await add_objective(db_session, other_module, "Other module.")
        other_version_outcome = await add_objective(db_session, other_version, "Other version.")

        cases = [
            (module_outcome, session_objective, "broader level"),  # downward
            (module_outcome, module_outcome, "broader level"),  # same level
            (session_objective, other_module_outcome, "own module"),
            (module_outcome, other_version_outcome, "same curriculum version"),
        ]
        for child, parent, message in cases:
            with pytest.raises(InvalidRequestError, match=message):
                await link_objectives(db_session, child, parent)

        await link_objectives(db_session, module_outcome, programme_outcome)
        with pytest.raises(ConflictError):
            await link_objectives(db_session, module_outcome, programme_outcome)

        programme_outcome.soft_delete()
        with pytest.raises(InvalidRequestError, match="deleted"):
            await link_objectives(db_session, session_objective, programme_outcome)


class TestCurriculumScopes:
    async def test_lineage_from_session_to_instance(self, db_session: AsyncSession) -> None:
        event = LearningEventFactory()
        await save(db_session, event)
        module = event.module
        programme = module.version.programme

        chain = await lineage(db_session, ScopeRef(ScopeType.LEARNING_EVENT, event.id))

        assert chain == [
            ScopeRef(ScopeType.LEARNING_EVENT, event.id),
            ScopeRef(ScopeType.MODULE, module.id),
            ScopeRef(ScopeType.PROGRAMME, programme.id),
            ScopeRef(ScopeType.FACULTY, programme.faculty_id),
            INSTANCE,
        ]

    async def test_deleted_items_are_not_scopes(self, db_session: AsyncSession) -> None:
        event = LearningEventFactory()
        await save(db_session, event)
        event.module.version.soft_delete()
        await db_session.flush()

        with pytest.raises(InvalidRequestError, match="No module"):
            await lineage(db_session, ScopeRef(ScopeType.LEARNING_EVENT, event.id))
        with pytest.raises(InvalidRequestError, match="No programme"):
            await lineage(db_session, ScopeRef(ScopeType.PROGRAMME, uuid.uuid4()))

    @pytest.mark.usefixtures("system_roles")
    async def test_programme_role_covers_every_version(self, db_session: AsyncSession) -> None:
        programme = ProgrammeFactory()
        this_year = CurriculumVersionFactory(programme=programme, academic_year=2027)
        next_year = CurriculumVersionFactory(programme=programme, academic_year=2028)
        modules = [ModuleFactory(version=this_year), ModuleFactory(version=next_year)]
        elsewhere = ModuleFactory()
        await save(db_session, programme, this_year, next_year, *modules, elsewhere)
        director = await new_user(db_session)
        await grant(
            db_session, director, "programme_director", ScopeRef(ScopeType.PROGRAMME, programme.id)
        )

        for module in modules:
            scope = ScopeRef(ScopeType.MODULE, module.id)
            assert await has_permission(db_session, director, Permission.CURRICULUM_EDIT, scope)
        other = ScopeRef(ScopeType.MODULE, elsewhere.id)
        assert not await has_permission(db_session, director, Permission.CURRICULUM_EDIT, other)

    @pytest.mark.usefixtures("system_roles")
    async def test_lecturer_limited_to_own_session(self, db_session: AsyncSession) -> None:
        mine = LearningEventFactory()
        other = LearningEventFactory(module=mine.module)
        await save(db_session, mine, other)
        lecturer = await new_user(db_session)
        await grant(db_session, lecturer, "lecturer", ScopeRef(ScopeType.LEARNING_EVENT, mine.id))

        def at(event: LearningEvent) -> ScopeRef:
            return ScopeRef(ScopeType.LEARNING_EVENT, event.id)

        assert await has_permission(db_session, lecturer, Permission.OBJECTIVES_EDIT, at(mine))
        assert not await has_permission(db_session, lecturer, Permission.OBJECTIVES_EDIT, at(other))
        assert not await has_permission(
            db_session,
            lecturer,
            Permission.OBJECTIVES_EDIT,
            ScopeRef(ScopeType.MODULE, mine.module_id),
        )
