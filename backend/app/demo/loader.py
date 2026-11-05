"""Load the fictional demo dataset (``python -m app.cli load-demo``).

Data: ``data/bsc-health-sciences-demo.json`` (curriculum, tag lists, mappings)
and ``data/demo-graduate-competencies.json`` (framework pack, identical to
``packs/demo``). Everything is created through the normal services, so the
usual rules apply and the audit log records it as the ``demo.load`` operation.
Existing pieces are reused: the institution (from the setup wizard), the demo
framework if already imported, and tag lists with the same keys.

The programme gets a published version for the current academic year and a draft
for the next year, made by copy forward with the changes in ``next_year`` (so the
version diff has something to show). Loading again on an install that has only the
published version (loaded before the draft existed) adds the draft; otherwise a
second load is refused.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.permissions import ScopeType
from app.core.profiles import Profile
from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    CurriculumVersion,
    Department,
    Faculty,
    Framework,
    FrameworkItem,
    Institution,
    LearningEvent,
    Module,
    Objective,
    Phase,
    Programme,
    QualificationType,
    TagList,
    TagValue,
    TaxonomyLevel,
    TaxonomyScale,
)
from app.models.curriculum import (
    ObjectiveDomain,
    ObjectiveStatus,
    PhaseKind,
    ProgrammeStatus,
    VersionStatus,
)
from app.models.framework import FrameworkStatus
from app.models.mapping import DepthMatch, MappingSource
from app.models.tagging import TagListKind
from app.services import dashboard_metrics
from app.services.audit import audit_operation
from app.services.authorization import (
    ConflictError,
    InvalidRequestError,
    ScopeRef,
    assign_role,
    get_role,
)
from app.services.curriculum import add_objective, link_objectives
from app.services.curriculum_edit import EventFields, create_event, delete_event, update_event
from app.services.curriculum_versions import copy_forward
from app.services.frameworks import activate_framework
from app.services.institution_settings import get_institution
from app.services.mapping import create_link
from app.services.packs import import_pack, load_pack_file
from app.services.tagging import (
    add_tag_value,
    set_assessment_method,
    set_teaching_format,
    tag_item,
)
from app.services.users import create_local_user, get_user_by_email

DATA_DIR = Path(__file__).parent / "data"
CURRICULUM_FILE = DATA_DIR / "bsc-health-sciences-demo.json"

Domain = Literal["knowledge", "skill", "attitude"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DemoMapping(_Model):
    item: str
    coverage: int
    depth: DepthMatch


class DemoObjective(_Model):
    text: str
    domain: Domain
    level: str
    links: list[str] = []


class DemoOutcome(DemoObjective):
    ref: str
    maps: list[DemoMapping] = []


class DemoEvent(_Model):
    title: str
    format: str
    contact_minutes: int
    self_study_minutes: int
    week: int | None = None
    themes: list[str] = []
    objectives: list[DemoObjective]


class DemoAssessmentItem(_Model):
    label: str
    marks: Decimal
    # Refs of the module's outcomes the item assesses.
    objectives: list[str] = []


class DemoAssessment(_Model):
    name: str
    method: str
    weight: Decimal
    timing: str
    time_minutes: int
    items: list[DemoAssessmentItem]


class DemoModule(_Model):
    code: str
    name: str
    phase: str | None
    credits: Decimal
    nqf_level: int
    description: str
    assessment_methods: list[str] = []
    assessments: list[DemoAssessment] = []
    outcomes: list[DemoOutcome]
    events: list[DemoEvent]


class DemoTagValue(_Model):
    code: str
    label: str


class DemoTagList(_Model):
    key: str
    name: str
    kind: TagListKind
    entity_types: list[str]
    values: list[DemoTagValue]
    # True: kept for the demo faculty only (a faculty-scoped list, ADR 015).
    faculty: bool = False


class DemoOfficeUser(_Model):
    email: str
    display_name: str


class DemoProgramme(_Model):
    code: str
    name: str
    qualification_type: str
    nqf_exit_level: int
    total_credits: int
    minimum_duration_years: Decimal
    saqa_id: str
    outcomes: list[DemoOutcome]


class DemoPhase(_Model):
    ref: str
    name: str
    kind: PhaseKind


class DemoInstitution(_Model):
    name: str
    short_code: str
    country: str


class DemoDepartment(_Model):
    code: str
    name: str


class DemoFaculty(_Model):
    code: str
    name: str
    department: DemoDepartment


class DemoSessionChange(_Model):
    module: str
    title: str
    new_title: str | None = None
    contact_minutes: int | None = None


class DemoSessionAdd(_Model):
    module: str
    event: DemoEvent


class DemoSessionRef(_Model):
    module: str
    title: str


class DemoReword(_Model):
    module: str
    session: str
    text: str
    new_text: str


class DemoNextYear(BaseModel):
    """Changes made to the next year's draft after copying it forward."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    change_sessions: list[DemoSessionChange] = []
    add_sessions: list[DemoSessionAdd] = []
    remove_sessions: list[DemoSessionRef] = []
    reword_objectives: list[DemoReword] = []


class DemoData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    institution: DemoInstitution
    faculty: DemoFaculty
    framework_pack: str
    taxonomy_scale: str
    tag_lists: list[DemoTagList]
    # Curriculum office account for the demo faculty (made only when a password is given).
    office_user: DemoOfficeUser | None = None
    programme: DemoProgramme
    phases: list[DemoPhase]
    modules: list[DemoModule]
    next_year: DemoNextYear = DemoNextYear()

    @model_validator(mode="after")
    def references_resolve(self) -> "DemoData":
        programme_refs = {o.ref for o in self.programme.outcomes}
        phase_refs = {p.ref for p in self.phases}
        for module in self.modules:
            if module.phase is not None and module.phase not in phase_refs:
                raise ValueError(f"{module.code}: unknown phase {module.phase}")
            module_refs = {o.ref for o in module.outcomes}
            for outcome in module.outcomes:
                if unknown := set(outcome.links) - programme_refs:
                    raise ValueError(f"{outcome.ref}: unknown programme outcomes {unknown}")
            for event in module.events:
                for objective in event.objectives:
                    if unknown := set(objective.links) - module_refs:
                        raise ValueError(f"{module.code}: unknown module outcomes {unknown}")
        return self


def load_data(path: Path = CURRICULUM_FILE) -> DemoData:
    return DemoData.model_validate(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class DemoSummary:
    programme: Programme
    modules: int
    learning_events: int
    objectives: int
    objective_links: int
    framework_items: int
    mappings: int
    tag_lists: int
    # The next year's draft (None if it was not added).
    draft_year: int | None = None
    # True when only the draft was added to a demo loaded earlier.
    draft_only: bool = False
    assessments: int = 0
    # True when this load made the faculty curriculum-office account.
    office_user_added: bool = False


class _Loader:
    def __init__(self, db: AsyncSession, data: DemoData) -> None:
        self.db = db
        self.data = data
        self.levels: dict[str, TaxonomyLevel] = {}
        self.items: dict[str, FrameworkItem] = {}
        self.tags: dict[str, dict[str, TagValue]] = {}
        self.objectives = 0
        self.links = 0
        self.mappings = 0
        self.assessments = 0
        self.new_lists = 0

    async def institution(self) -> Institution:
        existing = await get_institution(self.db)
        if existing is not None:
            return existing
        raw = self.data.institution
        institution = Institution(
            name=raw.name,
            short_code=raw.short_code,
            country=raw.country,
            settings={"profiles": [Profile.CORE.value, Profile.HEALTH.value]},
        )
        self.db.add(institution)
        await self.db.flush()
        return institution

    async def faculty(self, institution: Institution) -> Faculty:
        raw = self.data.faculty
        faculty = (
            await self.db.execute(
                select(Faculty).where(
                    Faculty.institution_id == institution.id,
                    Faculty.code == raw.code,
                    Faculty.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if faculty is None:
            faculty = Faculty(institution_id=institution.id, code=raw.code, name=raw.name)
            self.db.add(faculty)
            await self.db.flush()
            self.db.add(
                Department(
                    faculty_id=faculty.id, code=raw.department.code, name=raw.department.name
                )
            )
            await self.db.flush()
        return faculty

    async def framework(self) -> None:
        pack = load_pack_file(DATA_DIR / self.data.framework_pack)
        framework = (
            await self.db.execute(
                select(Framework).where(
                    Framework.key == pack.metadata.key,
                    Framework.version_label == pack.metadata.version,
                    Framework.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if framework is None:
            imported = await import_pack(self.db, pack)
            framework = imported.framework
        if framework.status != FrameworkStatus.ACTIVE:
            await activate_framework(self.db, framework)
        result = await self.db.execute(
            select(FrameworkItem).where(FrameworkItem.framework_id == framework.id)
        )
        self.items = {item.code: item for item in result.scalars()}

        scale_id = await self.db.scalar(
            select(TaxonomyScale.id).where(TaxonomyScale.key == self.data.taxonomy_scale)
        )
        if scale_id is None:
            raise InvalidRequestError(f"Taxonomy scale '{self.data.taxonomy_scale}' is missing.")
        levels = await self.db.execute(
            select(TaxonomyLevel).where(TaxonomyLevel.scale_id == scale_id)
        )
        self.levels = {level.name: level for level in levels.scalars()}

    async def tag_lists(self, faculty: Faculty) -> None:
        for raw in self.data.tag_lists:
            tag_list = (
                await self.db.execute(
                    select(TagList).where(TagList.key == raw.key, TagList.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            if tag_list is None:
                tag_list = TagList(
                    key=raw.key,
                    name=raw.name,
                    kind=raw.kind,
                    entity_types=raw.entity_types,
                    faculty_id=faculty.id if raw.faculty else None,
                )
                self.db.add(tag_list)
                await self.db.flush()
                self.new_lists += 1
            existing = await self.db.execute(
                select(TagValue).where(
                    TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
                )
            )
            values = {v.code: v for v in existing.scalars() if v.code}
            for position, value in enumerate(raw.values):
                if value.code not in values:
                    values[value.code] = await add_tag_value(
                        self.db, tag_list, value.label, code=value.code, position=position
                    )
            self.tags[raw.key] = values

    async def office_user(self, settings: Settings, faculty: Faculty, password: str) -> bool:
        """Make the demo curriculum-office account (role at the demo faculty only).

        Returns False if the data names no account or it already exists.
        """
        raw = self.data.office_user
        if raw is None or await get_user_by_email(self.db, raw.email) is not None:
            return False
        user = await create_local_user(
            self.db, settings, email=raw.email, display_name=raw.display_name, password=password
        )
        role = await get_role(self.db, key="curriculum_office")
        if role is None:
            raise InvalidRequestError("The system roles are missing; run sync-roles first.")
        await assign_role(
            self.db, None, user=user, role=role, scope=ScopeRef(ScopeType.FACULTY, faculty.id)
        )
        return True

    async def objective(
        self,
        owner: CurriculumVersion | Module | LearningEvent,
        raw: DemoObjective,
        position: int,
    ) -> Objective:
        level = self.levels.get(raw.level)
        if level is None:
            raise InvalidRequestError(f"Unknown taxonomy level '{raw.level}'.")
        objective = await add_objective(
            self.db, owner, raw.text, domain=ObjectiveDomain(raw.domain), position=position
        )
        objective.taxonomy_level_id = level.id
        objective.status = ObjectiveStatus.APPROVED
        self.objectives += 1
        return objective

    async def link(self, child: Objective, parents: list[Objective]) -> None:
        for parent in parents:
            await link_objectives(self.db, child, parent)
            self.links += 1

    async def curriculum(self, faculty: Faculty) -> tuple[Programme, CurriculumVersion, int, int]:
        raw = self.data.programme
        qualification = await self.db.scalar(
            select(QualificationType).where(QualificationType.key == raw.qualification_type)
        )
        programme = Programme(
            faculty_id=faculty.id,
            qualification_type_id=qualification.id if qualification else None,
            code=raw.code,
            name=raw.name,
            nqf_exit_level=raw.nqf_exit_level,
            total_credits=raw.total_credits,
            minimum_duration_years=raw.minimum_duration_years,
            saqa_id=raw.saqa_id,
            status=ProgrammeStatus.ACTIVE,
        )
        self.db.add(programme)
        await self.db.flush()
        version = CurriculumVersion(
            programme_id=programme.id,
            academic_year=date.today().year,
            status=VersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        self.db.add(version)
        await self.db.flush()

        outcomes: dict[str, Objective] = {}
        for position, outcome in enumerate(raw.outcomes):
            outcomes[outcome.ref] = await self.objective(version, outcome, position)

        phases: dict[str, Phase] = {}
        for position, raw_phase in enumerate(self.data.phases):
            phase = Phase(
                version_id=version.id, name=raw_phase.name, kind=raw_phase.kind, position=position
            )
            self.db.add(phase)
            phases[raw_phase.ref] = phase
        await self.db.flush()

        events_total = 0
        for position, raw_module in enumerate(self.data.modules):
            events_total += await self.module(version, phases, outcomes, raw_module, position)
        return programme, version, len(self.data.modules), events_total

    async def module(
        self,
        version: CurriculumVersion,
        phases: dict[str, Phase],
        programme_outcomes: dict[str, Objective],
        raw: DemoModule,
        position: int,
    ) -> int:
        module = Module(
            version_id=version.id,
            phase_id=phases[raw.phase].id if raw.phase else None,
            code=raw.code,
            name=raw.name,
            credits=raw.credits,
            nqf_level=raw.nqf_level,
            description=raw.description,
            position=position,
        )
        self.db.add(module)
        await self.db.flush()
        for code in raw.assessment_methods:
            await tag_item(self.db, self.tags["assessment-methods"][code], module)

        outcomes: dict[str, Objective] = {}
        for index, raw_outcome in enumerate(raw.outcomes):
            outcome = await self.objective(module, raw_outcome, index)
            outcomes[raw_outcome.ref] = outcome
            await self.link(outcome, [programme_outcomes[ref] for ref in raw_outcome.links])
            for mapping in raw_outcome.maps:
                await create_link(
                    self.db,
                    outcome,
                    self.items[mapping.item],
                    source=MappingSource.IMPORT,
                    coverage=mapping.coverage,
                    depth_match=mapping.depth,
                    rationale="Demo mapping (fictional).",
                )
                self.mappings += 1

        for index, raw_assessment in enumerate(raw.assessments):
            await self.assessment(module, raw_assessment, index, outcomes)

        for index, raw_event in enumerate(raw.events):
            event = LearningEvent(
                module_id=module.id,
                title=raw_event.title,
                contact_minutes=raw_event.contact_minutes,
                self_study_minutes=raw_event.self_study_minutes,
                week=raw_event.week,
                position=index,
            )
            self.db.add(event)
            await self.db.flush()
            await set_teaching_format(
                self.db, event, self.tags["teaching-methods"][raw_event.format]
            )
            for theme in raw_event.themes:
                await tag_item(self.db, self.tags["themes"][theme], event)
            for objective_position, raw_objective in enumerate(raw_event.objectives):
                objective = await self.objective(event, raw_objective, objective_position)
                await self.link(objective, [outcomes[ref] for ref in raw_objective.links])
        return len(raw.events)

    async def assessment(
        self,
        module: Module,
        raw: DemoAssessment,
        position: int,
        outcomes: dict[str, Objective],
    ) -> None:
        # Added directly: the demo version is already published, so the editing service
        # (draft versions only) would refuse.
        assessment = Assessment(
            module_id=module.id,
            name=raw.name,
            weight=raw.weight,
            timing=raw.timing,
            time_minutes=raw.time_minutes,
            position=position,
        )
        self.db.add(assessment)
        await self.db.flush()
        await set_assessment_method(
            self.db, assessment, self.tags["assessment-methods"][raw.method]
        )
        for index, raw_item in enumerate(raw.items):
            item = AssessmentItem(
                assessment_id=assessment.id,
                label=raw_item.label,
                marks=raw_item.marks,
                position=index,
            )
            self.db.add(item)
            await self.db.flush()
            for ref in raw_item.objectives:
                self.db.add(AssessmentItemObjective(item_id=item.id, objective_id=outcomes[ref].id))
        await self.db.flush()
        self.assessments += 1

    async def _event(self, module: Module, title: str) -> LearningEvent:
        event = await self.db.scalar(
            select(LearningEvent).where(
                LearningEvent.module_id == module.id,
                LearningEvent.title == title,
                LearningEvent.deleted_at.is_(None),
            )
        )
        if event is None:
            raise InvalidRequestError(f"{module.code} has no session '{title}'.")
        return event

    async def next_year(self, published: CurriculumVersion) -> CurriculumVersion:
        """Copy the published version forward to a draft and make the demo changes."""
        changes = self.data.next_year
        draft = await copy_forward(
            self.db, None, published, academic_year=published.academic_year + 1
        )
        modules = {
            module.code: module
            for module in await self.db.scalars(
                select(Module).where(Module.version_id == draft.id, Module.deleted_at.is_(None))
            )
        }
        raw_modules = {module.code: module for module in self.data.modules}

        for change in changes.change_sessions:
            event = await self._event(modules[change.module], change.title)
            fields: dict[str, object] = {}
            if change.new_title is not None:
                fields["title"] = change.new_title
            if change.contact_minutes is not None:
                fields["contact_minutes"] = change.contact_minutes
            await update_event(self.db, event, draft, fields)

        for added in changes.add_sessions:
            module, raw = modules[added.module], added.event
            event = await create_event(
                self.db,
                module,
                draft,
                EventFields(
                    title=raw.title,
                    format_value_id=self.tags["teaching-methods"][raw.format].id,
                    contact_minutes=raw.contact_minutes,
                    self_study_minutes=raw.self_study_minutes,
                    week=raw.week,
                ),
            )
            for theme in raw.themes:
                await tag_item(self.db, self.tags["themes"][theme], event)
            outcome_texts = {o.ref: o.text for o in raw_modules[added.module].outcomes}
            for position, raw_objective in enumerate(raw.objectives):
                objective = await add_objective(
                    self.db,
                    event,
                    raw_objective.text,
                    domain=ObjectiveDomain(raw_objective.domain),
                    position=position,
                )
                objective.taxonomy_level_id = self.levels[raw_objective.level].id
                objective.status = ObjectiveStatus.APPROVED
                for ref in raw_objective.links:
                    parent = await self.db.scalar(
                        select(Objective).where(
                            Objective.module_id == module.id,
                            Objective.text == outcome_texts[ref],
                            Objective.deleted_at.is_(None),
                        )
                    )
                    if parent is None:
                        raise InvalidRequestError(f"{module.code}: outcome {ref} is missing.")
                    await link_objectives(self.db, objective, parent)

        for removed in changes.remove_sessions:
            event = await self._event(modules[removed.module], removed.title)
            await delete_event(self.db, event, draft)

        for reword in changes.reword_objectives:
            event = await self._event(modules[reword.module], reword.session)
            found = await self.db.scalar(
                select(Objective).where(
                    Objective.learning_event_id == event.id,
                    Objective.text == reword.text,
                    Objective.deleted_at.is_(None),
                )
            )
            if found is None:
                raise InvalidRequestError(f"{reword.session}: objective not found.")
            found.text = reword.new_text
        await self.db.flush()
        return draft


async def load_demo(
    db: AsyncSession,
    data: DemoData | None = None,
    *,
    settings: Settings | None = None,
    office_password: str | None = None,
) -> DemoSummary:
    """Load the demo dataset in one transaction (or add the draft to an earlier load).

    The faculty curriculum-office account is made only when ``office_password`` and
    ``settings`` (for the password policy) are given; the data holds no secret. An install
    loaded earlier gets the faculty tag list and the account added the same way.

    Raises:
        ConflictError: If the demo programme is already loaded with its draft.
    """
    data = data or load_data()
    existing = await db.scalar(
        select(Programme).where(
            Programme.code == data.programme.code, Programme.deleted_at.is_(None)
        )
    )
    loader = _Loader(db, data)
    if existing is not None:
        versions = list(
            await db.scalars(
                select(CurriculumVersion).where(
                    CurriculumVersion.programme_id == existing.id,
                    CurriculumVersion.deleted_at.is_(None),
                )
            )
        )
        needs_draft = len(versions) == 1 and versions[0].status == VersionStatus.PUBLISHED
        faculty = await db.get(Faculty, existing.faculty_id)
        assert faculty is not None
        with audit_operation("demo.load"):
            await loader.framework()
            await loader.tag_lists(faculty)
            draft = await loader.next_year(versions[0]) if needs_draft else None
            if draft is not None:
                await dashboard_metrics.seed_history(db, draft, existing)
            added = await _add_office(loader, settings, faculty, office_password)
        if not needs_draft and not added and not loader.new_lists:
            raise ConflictError(f"The demo programme {data.programme.code} is already loaded.")
        return DemoSummary(
            programme=existing,
            modules=0,
            learning_events=0,
            objectives=0,
            objective_links=0,
            framework_items=len(loader.items),
            mappings=0,
            tag_lists=len(loader.tags),
            draft_year=draft.academic_year if draft else None,
            draft_only=True,
            office_user_added=added,
        )

    with audit_operation("demo.load"):
        institution = await loader.institution()
        faculty = await loader.faculty(institution)
        await loader.framework()
        await loader.tag_lists(faculty)
        programme, published, modules, events = await loader.curriculum(faculty)
        draft = await loader.next_year(published)
        await dashboard_metrics.seed_history(db, published, programme)
        await dashboard_metrics.seed_history(db, draft, programme)
        added = await _add_office(loader, settings, faculty, office_password)
    return DemoSummary(
        programme=programme,
        modules=modules,
        learning_events=events,
        objectives=loader.objectives,
        objective_links=loader.links,
        framework_items=len(loader.items),
        mappings=loader.mappings,
        tag_lists=len(loader.tags),
        draft_year=draft.academic_year,
        assessments=loader.assessments,
        office_user_added=added,
    )


async def _add_office(
    loader: _Loader, settings: Settings | None, faculty: Faculty, password: str | None
) -> bool:
    if not password or settings is None:
        return False
    return await loader.office_user(settings, faculty, password)
