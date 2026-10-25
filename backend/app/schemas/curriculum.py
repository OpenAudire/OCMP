"""Curriculum read schemas: programmes, versions, structure tree and details."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
    format_value_id: uuid.UUID | None
    contact_minutes: int
    self_study_minutes: int
    objective_count: int
    # Whether the user may edit this session.
    can_edit: bool


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
    # Whether the user may edit the module and add or remove its sessions.
    can_edit: bool
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
    # Whether the user may add, change and remove phases and modules.
    can_edit: bool


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
    format_value_id: uuid.UUID | None
    contact_minutes: int
    self_study_minutes: int
    week: int | None
    position: int
    description: str
    external_lms_ref: str | None
    objectives: list[ObjectiveRead]


# --- Editing (Slice 1.3) ---------------------------------------------------------------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]
LmsRef = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Credits = Annotated[Decimal, Field(ge=0, max_digits=5, decimal_places=1)]
NqfLevel = Annotated[int, Field(ge=1, le=10)]
Minutes = Annotated[int, Field(ge=0, le=100_000)]
Week = Annotated[int, Field(ge=0, le=520)]


class PhaseCreate(BaseModel):
    name: Name
    kind: PhaseKind = PhaseKind.YEAR


class PhaseUpdate(BaseModel):
    name: Name | None = None
    kind: PhaseKind | None = None


class PhaseSaved(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    name: str
    kind: PhaseKind
    position: int


class ModuleCreate(BaseModel):
    code: Code
    name: Name
    # None: a longitudinal module that spans phases.
    phase_id: uuid.UUID | None = None
    credits: Credits | None = None
    nqf_level: NqfLevel | None = None
    description: Description = ""
    external_lms_ref: LmsRef | None = None


class ModuleUpdate(BaseModel):
    """Only the fields sent are changed; send null to clear an optional field."""

    code: Code | None = None
    name: Name | None = None
    phase_id: uuid.UUID | None = None
    credits: Credits | None = None
    nqf_level: NqfLevel | None = None
    description: Description | None = None
    external_lms_ref: LmsRef | None = None


class ModuleSaved(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    phase_id: uuid.UUID | None
    code: str
    name: str
    credits: Decimal | None
    nqf_level: int | None
    description: str
    external_lms_ref: str | None
    position: int


class LearningEventCreate(BaseModel):
    title: Name
    format_value_id: uuid.UUID | None = None
    contact_minutes: Minutes = 0
    self_study_minutes: Minutes = 0
    week: Week | None = None
    description: Description = ""
    external_lms_ref: LmsRef | None = None


class LearningEventUpdate(BaseModel):
    """Only the fields sent are changed; send null to clear an optional field."""

    title: Name | None = None
    format_value_id: uuid.UUID | None = None
    contact_minutes: Minutes | None = None
    self_study_minutes: Minutes | None = None
    week: Week | None = None
    description: Description | None = None
    external_lms_ref: LmsRef | None = None


class LearningEventSaved(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    format_value_id: uuid.UUID | None
    contact_minutes: int
    self_study_minutes: int
    week: int | None
    position: int
    description: str
    external_lms_ref: str | None


class MoveRequest(BaseModel):
    """Where to put an item among its siblings: 0 is first."""

    position: Annotated[int, Field(ge=0, le=10_000)]


class PhaseCopy(BaseModel):
    name: Name
    # A new code for each module of the phase (module id to code); codes must be unused.
    module_codes: dict[uuid.UUID, Code] = Field(default_factory=dict)


class ModuleCopy(BaseModel):
    """Leave out ``phase_id`` to keep the copy in the module's phase; null puts it
    across phases."""

    code: Code
    name: Name
    phase_id: uuid.UUID | None = None


class LearningEventCopy(BaseModel):
    title: Name


class TeachingFormat(BaseModel):
    """A value that can be chosen as a session's teaching format."""

    id: uuid.UUID
    label: str
    list_name: str
