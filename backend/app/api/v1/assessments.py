"""Minimal assessments of a module, and the credits and notional hours check (ADR 035).

Changing assessments and their items needs ``curriculum.edit`` at the module (as for
sessions); roles held higher up count. A module the user cannot see is a 404 (ADR 027),
one they can see but not change is a 403; non-draft versions are read-only (409).

The credits check is advice and is open to everyone who sees the whole version.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, ScopeFromRequest, require_permission
from app.api.v1.curriculum_edit import (
    Target,
    module_scope,
    module_target_for,
    not_found,
    path_id,
    target_of,
    visible_or_404,
)
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.models import Assessment, AssessmentItem, User
from app.schemas.assessments import (
    AssessableObjective,
    AssessmentCreate,
    AssessmentItemCreate,
    AssessmentItemRead,
    AssessmentItemUpdate,
    AssessmentMethod,
    AssessmentRead,
    AssessmentUpdate,
    CreditFindingRead,
    CreditPolicyRead,
    LevelCreditsRead,
    ModuleHoursRead,
    VersionCreditCheckRead,
    YearCreditsRead,
)
from app.services import assessments, credit_check
from app.services.assessments import AssessmentWithItems
from app.services.audit import audit_operation
from app.services.authorization import ScopeRef
from app.services.tagging import assessment_methods, visible_faculty_ids

router = APIRouter(tags=["assessments"])


@dataclass
class AssessmentTarget:
    """The assessment (and item) a request changes, found while resolving its scope."""

    target: Target
    assessment: Assessment
    item: AssessmentItem | None = None


def _state(request: Request) -> AssessmentTarget:
    found: AssessmentTarget = request.state.assessment_target
    return found


async def _resolve(
    request: Request, db: AsyncSession, user: User, assessment: Assessment, what: str
) -> ScopeRef:
    try:
        target = await module_target_for(request, db, user, assessment.module_id)
    except HTTPException:
        raise not_found(what) from None
    assert target.module is not None
    request.state.assessment_target = AssessmentTarget(target, assessment)
    return ScopeRef(ScopeType.MODULE, target.module.id)


async def assessment_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    assessment_id = path_id(request, "assessment_id", "Assessment")
    assessment = await db.scalar(
        select(Assessment).where(Assessment.id == assessment_id, Assessment.deleted_at.is_(None))
    )
    if assessment is None:
        raise not_found("Assessment")
    return await _resolve(request, db, user, assessment, "Assessment")


async def item_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    item_id = path_id(request, "item_id", "Assessment item")
    row = (
        await db.execute(
            select(AssessmentItem, Assessment)
            .join(Assessment, Assessment.id == AssessmentItem.assessment_id)
            .where(
                AssessmentItem.id == item_id,
                AssessmentItem.deleted_at.is_(None),
                Assessment.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("Assessment item")
    item, assessment = row
    scope = await _resolve(request, db, user, assessment, "Assessment item")
    _state(request).item = item
    return scope


def _editor(scope: ScopeFromRequest) -> Any:
    return Depends(require_permission(Permission.CURRICULUM_EDIT, scope=scope))


ModuleEditor = Annotated[User, _editor(module_scope)]
AssessmentEditor = Annotated[User, _editor(assessment_scope)]
ItemEditor = Annotated[User, _editor(item_scope)]


def read_assessment(found: AssessmentWithItems) -> AssessmentRead:
    a = found.assessment
    return AssessmentRead(
        id=a.id,
        module_id=a.module_id,
        name=a.name,
        method_value_id=a.method_value_id,
        method=found.method_label,
        weight=a.weight,
        timing=a.timing,
        time_minutes=a.time_minutes,
        position=a.position,
        items=[
            AssessmentItemRead(
                id=i.item.id,
                label=i.item.label,
                marks=i.item.marks,
                position=i.item.position,
                objective_ids=i.objective_ids,
            )
            for i in found.items
        ],
    )


async def _saved(
    db: AsyncSession, module_id: uuid.UUID, assessment_id: uuid.UUID
) -> AssessmentRead:
    for found in await assessments.module_assessments(db, module_id):
        if found.assessment.id == assessment_id:
            return read_assessment(found)
    raise not_found("Assessment")  # pragma: no cover - the assessment was just saved


# --- Assessments --------------------------------------------------------------------


@router.post(
    "/modules/{module_id}/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    module_id: uuid.UUID,
    body: AssessmentCreate,
    request: Request,
    actor: ModuleEditor,
    db: DbSession,
) -> AssessmentRead:
    """Add an assessment at the end of a module."""
    target = target_of(request)
    assert target.module is not None
    with audit_operation("curriculum.assessment_create", actor_id=actor.id):
        assessment = await assessments.create_assessment(
            db,
            target.module,
            target.version,
            assessments.AssessmentFields(**body.model_dump()),
            created_by_id=actor.id,
        )
    return await _saved(db, target.module.id, assessment.id)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentRead)
async def update_assessment(
    assessment_id: uuid.UUID,
    body: AssessmentUpdate,
    request: Request,
    actor: AssessmentEditor,
    db: DbSession,
) -> AssessmentRead:
    """Change an assessment."""
    state = _state(request)
    with audit_operation("curriculum.assessment_update", actor_id=actor.id):
        await assessments.update_assessment(
            db,
            state.assessment,
            state.target.version,
            body.model_dump(exclude_unset=True),
        )
    return await _saved(db, state.assessment.module_id, state.assessment.id)


@router.delete("/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    assessment_id: uuid.UUID, request: Request, actor: AssessmentEditor, db: DbSession
) -> Response:
    """Delete an assessment with its items (soft delete)."""
    state = _state(request)
    with audit_operation("curriculum.assessment_delete", actor_id=actor.id):
        await assessments.delete_assessment(db, state.assessment, state.target.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Items --------------------------------------------------------------------------


@router.post(
    "/assessments/{assessment_id}/items",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_item(
    assessment_id: uuid.UUID,
    body: AssessmentItemCreate,
    request: Request,
    actor: AssessmentEditor,
    db: DbSession,
) -> AssessmentRead:
    """Add an item to an assessment; it returns the whole assessment."""
    state = _state(request)
    assert state.target.module is not None
    with audit_operation("curriculum.assessment_item_create", actor_id=actor.id):
        await assessments.create_item(
            db,
            state.assessment,
            state.target.module,
            state.target.version,
            label=body.label,
            marks=body.marks,
            objective_ids=body.objective_ids,
            created_by_id=actor.id,
        )
    return await _saved(db, state.assessment.module_id, state.assessment.id)


@router.patch("/assessment-items/{item_id}", response_model=AssessmentRead)
async def update_item(
    item_id: uuid.UUID,
    body: AssessmentItemUpdate,
    request: Request,
    actor: ItemEditor,
    db: DbSession,
) -> AssessmentRead:
    """Change an item or the objectives it assesses; it returns the whole assessment."""
    state = _state(request)
    assert state.item is not None and state.target.module is not None
    with audit_operation("curriculum.assessment_item_update", actor_id=actor.id):
        await assessments.update_item(
            db,
            state.item,
            state.target.module,
            state.target.version,
            body.model_dump(exclude_unset=True),
            updated_by_id=actor.id,
        )
    return await _saved(db, state.assessment.module_id, state.assessment.id)


@router.delete("/assessment-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID, request: Request, actor: ItemEditor, db: DbSession
) -> Response:
    """Delete an item (soft delete)."""
    state = _state(request)
    assert state.item is not None
    with audit_operation("curriculum.assessment_item_delete", actor_id=actor.id):
        await assessments.delete_item(db, state.item, state.target.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Choices ------------------------------------------------------------------------


@router.get("/assessment-methods", response_model=list[AssessmentMethod])
async def list_assessment_methods(user: CurrentUser, db: DbSession) -> list[AssessmentMethod]:
    """Values that can be chosen as an assessment's method (active assessment-method lists)."""
    return [
        AssessmentMethod(id=value.id, label=value.label, list_name=tag_list.name)
        for value, tag_list in await assessment_methods(db, await visible_faculty_ids(db, user))
    ]


@router.get("/modules/{module_id}/assessable-objectives", response_model=list[AssessableObjective])
async def list_assessable_objectives(
    module_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession
) -> list[AssessableObjective]:
    """The objectives of a module and its sessions that its assessment items may assess."""
    target = await module_target_for(request, db, user, module_id)
    assert target.module is not None
    return [
        AssessableObjective(
            id=objective.id,
            level=objective.level,
            text=objective.text,
            event_title=event.title if event else None,
        )
        for objective, event in await assessments.linkable_objectives(db, target.module)
    ]


# --- Credits and hours --------------------------------------------------------------


def _read_check(check: credit_check.VersionCreditCheck) -> VersionCreditCheckRead:
    return VersionCreditCheckRead(
        policy=CreditPolicyRead(**check.policy.model_dump()),
        modules=[ModuleHoursRead(**vars(m)) for m in check.modules],
        years=[YearCreditsRead(**vars(y)) for y in check.years],
        unphased_credits=check.unphased_credits,
        unphased_modules=check.unphased_modules,
        levels=[LevelCreditsRead(**vars(row)) for row in check.levels],
        total_credits=check.total_credits,
        programme_total_credits=check.programme_total_credits,
        qualification_name=check.qualification_name,
        qualification_min_credits=check.qualification_min_credits,
        exit_level_minimum=check.exit_level_minimum,
        exit_level=check.exit_level,
        findings=[CreditFindingRead(code=f.code, params=f.params) for f in check.findings],
    )


@router.get("/curriculum-versions/{version_id}/credit-check", response_model=VersionCreditCheckRead)
async def get_credit_check(
    version_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> VersionCreditCheckRead:
    """Planned hours against credits for every module, credits per year and NQF level, and
    findings against the qualification. Advice only. Needs the whole version to be visible."""
    visible = await visible_or_404(db, user, version_id, "Curriculum version")
    if not visible.view.full:
        raise not_found("Curriculum version")
    return _read_check(
        await credit_check.version_credit_check(db, visible.version, visible.programme)
    )
