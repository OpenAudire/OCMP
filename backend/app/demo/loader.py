"""Load the fictional demo dataset (``python -m app.cli load-demo``).

Data: ``data/bsc-health-sciences-demo.json`` (curriculum, tag lists, mappings)
and ``data/demo-graduate-competencies.json`` (framework pack, identical to
``packs/demo``). Everything is created through the normal services, so the
usual rules apply and the audit log records it as the ``demo.load`` operation.
Existing pieces are reused: the institution (from the setup wizard), the demo
framework if already imported, and tag lists with the same keys.
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

from app.core.profiles import Profile
from app.models import (
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
from app.services.audit import audit_operation
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum import add_objective, link_objectives
from app.services.frameworks import activate_framework
from app.services.institution_settings import get_institution
from app.services.mapping import create_link
from app.services.packs import import_pack, load_pack_file
from app.services.tagging import add_tag_value, set_teaching_format, tag_item

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


class DemoModule(_Model):
    code: str
    name: str
    phase: str | None
    credits: Decimal
    nqf_level: int
    description: str
    assessment_methods: list[str] = []
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


class DemoData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    institution: DemoInstitution
    faculty: DemoFaculty
    framework_pack: str
    taxonomy_scale: str
    tag_lists: list[DemoTagList]
    programme: DemoProgramme
    phases: list[DemoPhase]
    modules: list[DemoModule]

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

    async def tag_lists(self) -> None:
        for raw in self.data.tag_lists:
            tag_list = (
                await self.db.execute(
                    select(TagList).where(TagList.key == raw.key, TagList.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            if tag_list is None:
                tag_list = TagList(
                    key=raw.key, name=raw.name, kind=raw.kind, entity_types=raw.entity_types
                )
                self.db.add(tag_list)
                await self.db.flush()
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

    async def curriculum(self, faculty: Faculty) -> tuple[Programme, int, int]:
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
        return programme, len(self.data.modules), events_total

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


async def load_demo(db: AsyncSession, data: DemoData | None = None) -> DemoSummary:
    """Load the demo dataset in one transaction.

    Raises:
        ConflictError: If the demo programme is already loaded.
    """
    data = data or load_data()
    already = await db.scalar(
        select(Programme.id).where(
            Programme.code == data.programme.code, Programme.deleted_at.is_(None)
        )
    )
    if already:
        raise ConflictError(f"The demo programme {data.programme.code} is already loaded.")

    loader = _Loader(db, data)
    with audit_operation("demo.load"):
        institution = await loader.institution()
        faculty = await loader.faculty(institution)
        await loader.framework()
        await loader.tag_lists()
        programme, modules, events = await loader.curriculum(faculty)
    return DemoSummary(
        programme=programme,
        modules=modules,
        learning_events=events,
        objectives=loader.objectives,
        objective_links=loader.links,
        framework_items=len(loader.items),
        mappings=loader.mappings,
        tag_lists=len(loader.tags),
    )
