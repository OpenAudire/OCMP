"""The curriculum explorer for students and staff (Slice 1.29, ADR 059).

Reads of **published** versions only, for anyone who may view published curriculum. They show what
the person's roles show of the version and never framework mappings. A version or module that is not
published, or that the person cannot see, is a 404.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.services import explorer, explorer_competencies
from app.services.explorer import ExplorerAssessment, ExplorerModule, ExplorerSession

router = APIRouter(tags=["explorer"])


class ObjectiveRead(BaseModel):
    id: uuid.UUID
    text: str


class SessionRead(BaseModel):
    id: uuid.UUID
    title: str
    week: int | None
    format: str | None
    contact_minutes: int
    self_study_minutes: int
    description: str
    objectives: list[ObjectiveRead]
    module_id: uuid.UUID
    module_code: str
    module_name: str


class ItemRead(BaseModel):
    id: uuid.UUID
    label: str
    marks: int | None
    objectives: list[ObjectiveRead]


class AssessmentRead(BaseModel):
    id: uuid.UUID
    name: str
    method: str | None
    weight: float | None
    timing: str
    time_minutes: int
    items: list[ItemRead]
    covered: list[ObjectiveRead]


class TagRead(BaseModel):
    list_name: str
    label: str


class ExplorerModuleRead(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    code: str
    name: str
    credits: float | None
    nqf_level: int | None
    description: str
    contact_minutes: int
    self_study_minutes: int
    outcomes: list[ObjectiveRead]
    sessions: list[SessionRead]
    assessments: list[AssessmentRead]
    tags: list[TagRead]


class ExplorerWeekRead(BaseModel):
    version_id: uuid.UUID
    programme_code: str
    academic_year: int
    week: int
    # The weeks that have sessions, in order.
    weeks: list[int]
    sessions: list[SessionRead]


def _session(s: ExplorerSession) -> SessionRead:
    return SessionRead(
        id=s.id,
        title=s.title,
        week=s.week,
        format=s.format,
        contact_minutes=s.contact_minutes,
        self_study_minutes=s.self_study_minutes,
        description=s.description,
        objectives=[ObjectiveRead(id=o.id, text=o.text) for o in s.objectives],
        module_id=s.module_id,
        module_code=s.module_code,
        module_name=s.module_name,
    )


def _assessment(a: ExplorerAssessment) -> AssessmentRead:
    return AssessmentRead(
        id=a.id,
        name=a.name,
        method=a.method,
        weight=a.weight,
        timing=a.timing,
        time_minutes=a.time_minutes,
        items=[
            ItemRead(
                id=i.id,
                label=i.label,
                marks=i.marks,
                objectives=[ObjectiveRead(id=o.id, text=o.text) for o in i.objectives],
            )
            for i in a.items
        ],
        covered=[ObjectiveRead(id=o.id, text=o.text) for o in a.covered],
    )


def _module(found: ExplorerModule) -> ExplorerModuleRead:
    m = found.module
    return ExplorerModuleRead(
        id=m.id,
        version_id=m.version_id,
        code=m.code,
        name=m.name,
        credits=float(m.credits) if m.credits is not None else None,
        nqf_level=m.nqf_level,
        description=m.description,
        contact_minutes=found.contact_minutes,
        self_study_minutes=found.self_study_minutes,
        outcomes=[ObjectiveRead(id=o.id, text=o.text) for o in found.outcomes],
        sessions=[_session(s) for s in found.sessions],
        assessments=[_assessment(a) for a in found.assessments],
        tags=[TagRead(list_name=t.list_name, label=t.label) for t in found.tags],
    )


class BuiltSessionRead(BaseModel):
    id: uuid.UUID
    title: str
    week: int | None


class BuiltModuleRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    sessions: list[BuiltSessionRead]


class CompetencyGroupRead(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    modules: list[BuiltModuleRead]


class FrameworkGroupsRead(BaseModel):
    name: str
    version_label: str
    groups: list[CompetencyGroupRead]


class CompetenciesRead(BaseModel):
    version_id: uuid.UUID
    programme_code: str
    academic_year: int
    frameworks: list[FrameworkGroupsRead]


@router.get(
    "/curriculum-versions/{version_id}/explorer/competencies", response_model=CompetenciesRead
)
async def explore_competencies(
    version_id: uuid.UUID, access: Access, db: DbSession
) -> CompetenciesRead:
    """Where a published year builds each competency group (ADR 061). A 404 while the
    institution has the view switched off, as for a version the person cannot see."""
    found = await explorer_competencies.competency_view(db, access, version_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    return CompetenciesRead(
        version_id=found.version.version.id,
        programme_code=found.version.programme.code,
        academic_year=found.version.version.academic_year,
        frameworks=[
            FrameworkGroupsRead(
                name=f.name,
                version_label=f.version_label,
                groups=[
                    CompetencyGroupRead(
                        id=g.id,
                        code=g.code,
                        title=g.title,
                        modules=[
                            BuiltModuleRead(
                                id=m.id,
                                code=m.code,
                                name=m.name,
                                sessions=[
                                    BuiltSessionRead(id=s.id, title=s.title, week=s.week)
                                    for s in m.sessions
                                ],
                            )
                            for m in g.modules
                        ],
                    )
                    for g in f.groups
                ],
            )
            for f in found.frameworks
        ],
    )


@router.get("/modules/{module_id}/explorer", response_model=ExplorerModuleRead)
async def explore_module(module_id: uuid.UUID, access: Access, db: DbSession) -> ExplorerModuleRead:
    """A module of a published version: its outcomes, its sessions by week with their objectives
    and its assessments with what each item assesses."""
    found = await explorer.module_view(db, access, module_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Module not found.")
    return _module(found)


@router.get("/curriculum-versions/{version_id}/explorer/week", response_model=ExplorerWeekRead)
async def explore_week(
    version_id: uuid.UUID,
    access: Access,
    db: DbSession,
    week: Annotated[int, Query(ge=0, le=200)] = 1,
) -> ExplorerWeekRead:
    """The sessions of one teaching week across the modules of a published version."""
    found = await explorer.week_view(db, access, version_id, week)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    return ExplorerWeekRead(
        version_id=found.version.version.id,
        programme_code=found.version.programme.code,
        academic_year=found.version.version.academic_year,
        week=found.week,
        weeks=found.weeks,
        sessions=[_session(s) for s in found.sessions],
    )
