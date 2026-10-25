"""Curriculum read schemas: programmes, versions, structure tree and details."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.curriculum import (
    AccreditationStatus,
    ObjectiveDomain,
    ObjectiveStatus,
    PhaseKind,
    ProgrammeStatus,
    VersionStatus,
)


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    academic_year: int
    status: VersionStatus
    published_at: datetime | None
    based_on_id: uuid.UUID | None


class ProgrammeSummary(BaseModel):
    """A programme with the versions the user may see, newest academic year first."""

    id: uuid.UUID
    code: str
    name: str
    faculty_id: uuid.UUID
    faculty_name: str
    status: ProgrammeStatus
    versions: list[VersionRead]


class QualificationTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    nqf_exit_level: int
    min_total_credits: int


class ProgrammeRead(ProgrammeSummary):
    qualification_type: QualificationTypeRead | None
    nqf_exit_level: int | None
    saqa_id: str | None
    total_credits: int | None
    minimum_duration_years: Decimal | None
    che_accreditation_status: AccreditationStatus
    che_accredited_from: date | None
    che_accredited_until: date | None
    council_name: str | None
    council_accreditation_status: AccreditationStatus
    council_accredited_from: date | None
    council_accredited_until: date | None


class ProgrammeRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class StructureEvent(BaseModel):
    id: uuid.UUID
    title: str
    position: int
    week: int | None
    format: str | None
    contact_minutes: int
    self_study_minutes: int
    objective_count: int


class StructureModule(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    phase_id: uuid.UUID | None
    position: int
    credits: Decimal | None
    nqf_level: int | None
    # Shown only to place the user's sessions; its details are not available to them.
    context_only: bool
    objective_count: int
    events: list[StructureEvent]


class StructurePhase(BaseModel):
    id: uuid.UUID
    name: str
    kind: PhaseKind
    position: int
    modules: list[StructureModule]


class VersionStructure(BaseModel):
    """The tree of a version as far as the user may see it."""

    version: VersionRead
    programme: ProgrammeRef
    # True when the user sees only some modules or sessions (a narrower role).
    partial: bool
    # Programme outcomes; null when the user does not see the whole version.
    outcome_count: int | None
    phases: list[StructurePhase]
    # Longitudinal modules that span phases.
    modules_without_phase: list[StructureModule]


class ObjectiveRead(BaseModel):
    id: uuid.UUID
    text: str
    domain: ObjectiveDomain | None
    status: ObjectiveStatus
    position: int
    # Broader objectives this one contributes to.
    parent_ids: list[uuid.UUID]


class ModuleRead(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    phase_id: uuid.UUID | None
    code: str
    name: str
    credits: Decimal | None
    nqf_level: int | None
    description: str
    external_lms_ref: str | None
    event_count: int
    # Sums over the module's sessions.
    contact_minutes: int
    self_study_minutes: int
    outcomes: list[ObjectiveRead]


class LearningEventRead(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    format: str | None
    contact_minutes: int
    self_study_minutes: int
    week: int | None
    position: int
    description: str
    external_lms_ref: str | None
    objectives: list[ObjectiveRead]
