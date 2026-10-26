"""Assessment and credit check schemas."""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.curriculum import ObjectiveLevel, PhaseKind
from app.services.credit_check import HoursStatus, YearStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Timing = Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)]
Weight = Annotated[Decimal, Field(ge=0, le=100, max_digits=4, decimal_places=1)]
Marks = Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=1)]
Minutes = Annotated[int, Field(ge=0, le=100_000)]


class AssessmentItemRead(BaseModel):
    id: uuid.UUID
    label: str
    marks: Decimal | None
    position: int
    # Objectives this item assesses (live ones, in order).
    objective_ids: list[uuid.UUID]


class AssessmentRead(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    name: str
    method_value_id: uuid.UUID | None
    method: str | None
    weight: Decimal | None
    timing: str
    time_minutes: int
    position: int
    items: list[AssessmentItemRead]


class AssessmentCreate(BaseModel):
    name: Name
    method_value_id: uuid.UUID | None = None
    weight: Weight | None = None
    timing: Timing = ""
    time_minutes: Minutes = 0


class AssessmentUpdate(BaseModel):
    """Only the fields sent are changed; send null to clear the method or the weight."""

    name: Name | None = None
    method_value_id: uuid.UUID | None = None
    weight: Weight | None = None
    timing: Timing | None = None
    time_minutes: Minutes | None = None


class AssessmentItemCreate(BaseModel):
    label: Name
    marks: Marks | None = None
    objective_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class AssessmentItemUpdate(BaseModel):
    """Only the fields sent are changed; ``objective_ids`` replaces the whole list."""

    label: Name | None = None
    marks: Marks | None = None
    objective_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


class AssessmentMethod(BaseModel):
    id: uuid.UUID
    label: str
    list_name: str


class AssessableObjective(BaseModel):
    """An objective an item of the module may assess."""

    id: uuid.UUID
    level: ObjectiveLevel
    text: str
    # The session that owns it (null for module outcomes).
    event_title: str | None


# --- Credits and hours --------------------------------------------------------------


class ModuleHoursRead(BaseModel):
    module_id: uuid.UUID
    code: str
    name: str
    phase_id: uuid.UUID | None
    credits: Decimal | None
    nqf_level: int | None
    contact_hours: Decimal
    self_study_hours: Decimal
    assessment_hours: Decimal
    planned_hours: Decimal
    expected_hours: Decimal | None
    difference_percent: Decimal | None
    status: HoursStatus


class CreditPolicyRead(BaseModel):
    hours_per_credit: int
    tolerance_percent: int
    credits_per_year: int
    min_exit_level_credits: int | None


class YearCreditsRead(BaseModel):
    phase_id: uuid.UUID
    name: str
    kind: PhaseKind
    credits: Decimal
    modules: int
    modules_without_credits: int
    expected_credits: int | None
    status: YearStatus


class LevelCreditsRead(BaseModel):
    level: int | None
    credits: Decimal
    modules: int


class CreditFindingRead(BaseModel):
    code: str
    params: dict[str, str | int]


class VersionCreditCheckRead(BaseModel):
    policy: CreditPolicyRead
    modules: list[ModuleHoursRead]
    years: list[YearCreditsRead]
    unphased_credits: Decimal
    unphased_modules: int
    levels: list[LevelCreditsRead]
    total_credits: Decimal
    programme_total_credits: int | None
    qualification_name: str | None
    qualification_min_credits: int | None
    exit_level: int | None
    findings: list[CreditFindingRead]
