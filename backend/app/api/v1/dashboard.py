"""The committee dashboard (Slice 1.28, ADR 058).

Needs ``reports.view`` at the programme (or at a module of it, for a narrower view: then the figures
cover only what that person sees and there are no trend lines). A version the user cannot see is a
404.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.models import Framework
from app.models.curriculum import VersionStatus
from app.services import committee_dashboard
from app.services.authorization import AuthorizationError
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.policies import coverage_policy_for_version
from app.services.report_access import may_report

router = APIRouter(tags=["dashboard"])


class FrameworkRef(BaseModel):
    id: uuid.UUID
    name: str
    version_label: str


class VersionRef(BaseModel):
    id: uuid.UUID
    academic_year: int
    status: VersionStatus
    programme_code: str
    programme_name: str


class PointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    value: float


class KpiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    # "percent" (value from 0 to 1) or "count".
    unit: str
    value: float | None
    numerator: int | None
    denominator: int | None
    series: list[PointRead]


class ProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_id: uuid.UUID
    code: str
    name: str
    objectives: int
    mapped: int
    waiting: int


class GroupCompareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    now: float
    before: float | None


class ComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: uuid.UUID
    academic_year: int
    status: VersionStatus
    groups: list[GroupCompareRead]


class CreditRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_id: uuid.UUID
    code: str
    name: str
    credits: float | None
    expected_hours: float | None
    planned_hours: float
    difference_percent: float | None
    status: str


class CreditYearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    credits: float
    expected_credits: int | None
    status: str


class CreditTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hours_per_credit: int
    tolerance_percent: int
    credits_per_year: int
    years: list[CreditYearRead]
    modules: list[CreditRowRead]


class DashboardRead(BaseModel):
    version: VersionRef
    # The person sees only part of the version: the figures cover only that part, with no trends.
    partial: bool
    framework: FrameworkRef | None
    frameworks: list[FrameworkRef]
    kpis: list[KpiRead]
    # The date of the latest snapshot behind the trend lines.
    snapshot_on: date | None
    progress: list[ProgressRead]
    # Coverage under this share (percent) counts as low.
    low_percent: int
    comparison: ComparisonRead | None
    credits: CreditTableRead
    generated_at: datetime


class TraceModuleOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    module_code: str | None


class TraceGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_outcome_id: uuid.UUID | None
    objectives: int
    sessions: int


class TraceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    coverage: int
    objectives: int


class OutcomeRef(BaseModel):
    id: uuid.UUID
    text: str


class ReachRead(BaseModel):
    # The index of the session-objective group, and the framework item it reaches.
    group: int
    item_id: uuid.UUID


class TraceRead(BaseModel):
    version: VersionRef
    framework: FrameworkRef | None
    partial: bool
    outcomes: list[OutcomeRef]
    outcome: OutcomeRef | None
    module_outcomes: list[TraceModuleOutcomeRead]
    groups: list[TraceGroupRead]
    items: list[TraceItemRead]
    items_total: int
    reaches: list[ReachRead]
    module_count: int
    session_objectives: int
    sessions: int


def _framework(framework: Framework) -> FrameworkRef:
    return FrameworkRef(id=framework.id, name=framework.name, version_label=framework.version_label)


def _version(visible: VisibleVersion) -> VersionRef:
    return VersionRef(
        id=visible.version.id,
        academic_year=visible.version.academic_year,
        status=visible.version.status,
        programme_code=visible.programme.code,
        programme_name=visible.programme.name,
    )


async def _allowed(
    db: DbSession, access: Access, actor: CurrentUser, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    if not await may_report(db, actor, visible):
        raise AuthorizationError("You do not have permission to see reports for this programme.")
    return visible


@router.get("/curriculum-versions/{version_id}/dashboard", response_model=DashboardRead)
async def dashboard(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    framework_id: Annotated[uuid.UUID | None, Query()] = None,
) -> DashboardRead:
    """Key indicators with trends, mapping progress by module, coverage against the last published
    version and the credits table."""
    visible = await _allowed(db, access, actor, version_id)
    policy = await coverage_policy_for_version(db, version_id)
    result = await committee_dashboard.build_dashboard(db, visible, policy, framework_id)
    return DashboardRead(
        version=_version(visible),
        partial=result.partial,
        framework=_framework(result.framework) if result.framework else None,
        frameworks=[_framework(f) for f in result.frameworks],
        kpis=[KpiRead.model_validate(k) for k in result.kpis],
        snapshot_on=result.snapshot_on,
        progress=[ProgressRead.model_validate(p) for p in result.progress],
        low_percent=result.low_percent,
        comparison=ComparisonRead.model_validate(result.comparison) if result.comparison else None,
        credits=CreditTableRead.model_validate(result.credits),
        generated_at=datetime.now().astimezone(),
    )


@router.get("/curriculum-versions/{version_id}/dashboard/traceability", response_model=TraceRead)
async def traceability(
    version_id: uuid.UUID,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    framework_id: Annotated[uuid.UUID | None, Query()] = None,
    outcome_id: Annotated[uuid.UUID | None, Query()] = None,
) -> TraceRead:
    """From one programme outcome down to the framework items its objectives reach."""
    visible = await _allowed(db, access, actor, version_id)
    framework = await db.get(Framework, framework_id) if framework_id else None
    if framework is not None and (framework.is_deleted or framework.status.value == "draft"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found.")
    trace = await committee_dashboard.build_trace(db, visible, framework, outcome_id)
    return TraceRead(
        version=_version(visible),
        framework=_framework(framework) if framework else None,
        partial=not visible.view.full,
        outcomes=[OutcomeRef(id=i, text=t) for i, t in trace.outcomes],
        outcome=OutcomeRef(id=trace.outcome[0], text=trace.outcome[1]) if trace.outcome else None,
        module_outcomes=[TraceModuleOutcomeRead.model_validate(m) for m in trace.module_outcomes],
        groups=[TraceGroupRead.model_validate(g) for g in trace.groups],
        items=[TraceItemRead.model_validate(i) for i in trace.items],
        items_total=trace.items_total,
        reaches=[ReachRead(group=g, item_id=i) for g, i in trace.reaches],
        module_count=trace.module_count,
        session_objectives=trace.session_objectives,
        sessions=trace.sessions,
    )
