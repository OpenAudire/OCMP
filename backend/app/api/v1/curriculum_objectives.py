"""Editing objectives: programme outcomes, module outcomes and session objectives.

Each endpoint checks ``objectives.edit`` at the scope that owns the objective (ADR 031):
the programme for programme outcomes, the module for module outcomes, the session for
session objectives (roles held higher up count). A target the user cannot see is a 404
(ADR 027); one they can see but not change is a 403; non-draft versions are read-only
(409). Setting an objective to approved or retired needs ``objectives.approve`` at the
same scope (ADR 032); the services refuse it otherwise (403).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, ScopeFromRequest, SettingsDep, require_permission
from app.api.v1.curriculum_edit import (
    Target,
    event_scope,
    module_scope,
    not_found,
    path_id,
    store_target,
    target_of,
    version_programme,
    visible_or_404,
)
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.jobs.embeddings import enqueue_objective
from app.models import Module, Objective, ObjectiveLink, TaxonomyScale, User
from app.models.curriculum import ObjectiveLevel
from app.schemas.curriculum import (
    ObjectiveCreate,
    ObjectiveOption,
    ObjectiveSaved,
    ObjectiveUpdate,
    TaxonomyLevelRead,
    TaxonomyScaleRead,
)
from app.services import curriculum_objectives
from app.services.audit import audit_operation
from app.services.authorization import ScopeRef, has_permission
from app.services.curriculum_scopes import objective_scope

router = APIRouter(tags=["curriculum"])


async def objective_edit_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    """The scope of the objective in the path, if the user sees the item that owns it."""
    return await objective_scope_for(
        request, db, user, path_id(request, "objective_id", "Objective")
    )


async def objective_scope_for(
    request: Request, db: AsyncSession, user: User, objective_id: uuid.UUID
) -> ScopeRef:
    """The scope of this objective, if the user sees the item that owns it."""
    objective = await db.scalar(
        select(Objective).where(Objective.id == objective_id, Objective.deleted_at.is_(None))
    )
    if objective is None:
        raise not_found("Objective")
    visible = await visible_or_404(db, user, objective.version_id, "Objective")
    module_id = await curriculum_objectives.owner_module_id(db, objective)
    if objective.level == ObjectiveLevel.PROGRAMME:
        shown = visible.view.full
    elif objective.level == ObjectiveLevel.MODULE:
        shown = module_id is not None and visible.view.shows_module(module_id)
    else:
        assert objective.learning_event_id is not None and module_id is not None
        shown = visible.view.shows_event(module_id, objective.learning_event_id)
    if not shown:
        raise not_found("Objective")
    store_target(request, Target(visible, objective=objective))
    return await objective_scope(db, objective)


def _editor(scope: ScopeFromRequest) -> Any:
    return Depends(require_permission(Permission.OBJECTIVES_EDIT, scope=scope))


OutcomeEditor = Annotated[User, _editor(version_programme)]
ModuleObjectiveEditor = Annotated[User, _editor(module_scope)]
EventObjectiveEditor = Annotated[User, _editor(event_scope)]
ObjectiveEditor = Annotated[User, _editor(objective_edit_scope)]


async def _can_approve(db: AsyncSession, actor: User, scope: ScopeRef) -> bool:
    return await has_permission(db, actor, Permission.OBJECTIVES_APPROVE, scope)


async def _parent_ids(db: AsyncSession, objective: Objective) -> list[uuid.UUID]:
    parent = Objective.__table__.alias("parent")
    rows = await db.execute(
        select(ObjectiveLink.parent_id)
        .join(parent, parent.c.id == ObjectiveLink.parent_id)
        .where(ObjectiveLink.child_id == objective.id, parent.c.deleted_at.is_(None))
        .order_by(parent.c.position)
    )
    return list(rows.scalars())


async def _saved(db: AsyncSession, objective: Objective) -> ObjectiveSaved:
    return ObjectiveSaved(
        id=objective.id,
        level=objective.level,
        text=objective.text,
        domain=objective.domain,
        taxonomy_level_id=objective.taxonomy_level_id,
        status=objective.status,
        position=objective.position,
        parent_ids=await _parent_ids(db, objective),
    )


async def _options(
    db: AsyncSession, target: Target, level: ObjectiveLevel, module_id: uuid.UUID | None
) -> list[Objective]:
    return await curriculum_objectives.parent_options(
        db, target.visible.view, level, target.version.id, module_id
    )


async def _option_reads(db: AsyncSession, options: list[Objective]) -> list[ObjectiveOption]:
    module_ids = [o.module_id for o in options if o.module_id]
    codes: dict[uuid.UUID, str] = {}
    if module_ids:
        rows = await db.execute(select(Module.id, Module.code).where(Module.id.in_(module_ids)))
        codes = dict(rows.all())
    return [
        ObjectiveOption(
            id=o.id,
            level=o.level,
            text=o.text,
            module_code=codes.get(o.module_id) if o.module_id else None,
        )
        for o in options
    ]


@router.post(
    "/curriculum-versions/{version_id}/outcomes",
    response_model=ObjectiveSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_programme_outcome(
    version_id: uuid.UUID,
    body: ObjectiveCreate,
    request: Request,
    actor: OutcomeEditor,
    db: DbSession,
    settings: SettingsDep,
) -> ObjectiveSaved:
    """Add a programme outcome at the end of the version's outcomes."""
    target = target_of(request)
    with audit_operation("curriculum.objective_create", actor_id=actor.id):
        objective = await curriculum_objectives.create_objective(
            db,
            target.version,
            target.version,
            body.model_dump(),
            options=[],
            can_approve=await _can_approve(
                db, actor, ScopeRef(ScopeType.PROGRAMME, target.visible.programme.id)
            ),
            created_by_id=actor.id,
        )
    enqueue_objective(settings, objective.id)
    return await _saved(db, objective)


@router.post(
    "/modules/{module_id}/outcomes",
    response_model=ObjectiveSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_module_outcome(
    module_id: uuid.UUID,
    body: ObjectiveCreate,
    request: Request,
    actor: ModuleObjectiveEditor,
    db: DbSession,
    settings: SettingsDep,
) -> ObjectiveSaved:
    """Add an outcome to a module; its upward links go to programme outcomes."""
    target = target_of(request)
    assert target.module is not None
    options = await _options(db, target, ObjectiveLevel.MODULE, target.module.id)
    with audit_operation("curriculum.objective_create", actor_id=actor.id):
        objective = await curriculum_objectives.create_objective(
            db,
            target.module,
            target.version,
            body.model_dump(),
            options=options,
            can_approve=await _can_approve(db, actor, ScopeRef(ScopeType.MODULE, target.module.id)),
            created_by_id=actor.id,
        )
    enqueue_objective(settings, objective.id)
    return await _saved(db, objective)


@router.post(
    "/learning-events/{event_id}/objectives",
    response_model=ObjectiveSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_objective(
    event_id: uuid.UUID,
    body: ObjectiveCreate,
    request: Request,
    actor: EventObjectiveEditor,
    db: DbSession,
    settings: SettingsDep,
) -> ObjectiveSaved:
    """Add an objective to a session; its upward links go to its module's outcomes or
    to programme outcomes."""
    target = target_of(request)
    assert target.event is not None and target.module is not None
    options = await _options(db, target, ObjectiveLevel.LEARNING_EVENT, target.module.id)
    with audit_operation("curriculum.objective_create", actor_id=actor.id):
        objective = await curriculum_objectives.create_objective(
            db,
            target.event,
            target.version,
            body.model_dump(),
            options=options,
            can_approve=await _can_approve(
                db, actor, ScopeRef(ScopeType.LEARNING_EVENT, target.event.id)
            ),
            created_by_id=actor.id,
        )
    enqueue_objective(settings, objective.id)
    return await _saved(db, objective)


@router.patch("/objectives/{objective_id}", response_model=ObjectiveSaved)
async def update_objective(
    objective_id: uuid.UUID,
    body: ObjectiveUpdate,
    request: Request,
    actor: ObjectiveEditor,
    db: DbSession,
    settings: SettingsDep,
) -> ObjectiveSaved:
    """Change an objective's text, domain, taxonomy level, status or upward links.

    Approving or retiring needs ``objectives.approve``."""
    target = target_of(request)
    objective = target.objective
    assert objective is not None
    options = await _options(
        db, target, objective.level, await curriculum_objectives.owner_module_id(db, objective)
    )
    with audit_operation("curriculum.objective_update", actor_id=actor.id):
        await curriculum_objectives.update_objective(
            db,
            objective,
            target.version,
            body.model_dump(exclude_unset=True),
            options=options,
            can_approve=await _can_approve(db, actor, await objective_scope(db, objective)),
            created_by_id=actor.id,
        )
    enqueue_objective(settings, objective.id)
    return await _saved(db, objective)


@router.delete("/objectives/{objective_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_objective(
    objective_id: uuid.UUID,
    request: Request,
    actor: ObjectiveEditor,
    db: DbSession,
    settings: SettingsDep,
) -> Response:
    """Delete an objective (soft delete)."""
    target = target_of(request)
    assert target.objective is not None
    with audit_operation("curriculum.objective_delete", actor_id=actor.id):
        await curriculum_objectives.delete_objective(db, target.objective, target.version)
    enqueue_objective(settings, target.objective.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/modules/{module_id}/outcome-link-options", response_model=list[ObjectiveOption])
async def module_outcome_link_options(
    module_id: uuid.UUID, request: Request, actor: ModuleObjectiveEditor, db: DbSession
) -> list[ObjectiveOption]:
    """The programme outcomes a module outcome can link to (those the user sees)."""
    target = target_of(request)
    assert target.module is not None
    options = await _options(db, target, ObjectiveLevel.MODULE, target.module.id)
    return await _option_reads(db, options)


@router.get(
    "/learning-events/{event_id}/objective-link-options", response_model=list[ObjectiveOption]
)
async def event_objective_link_options(
    event_id: uuid.UUID, request: Request, actor: EventObjectiveEditor, db: DbSession
) -> list[ObjectiveOption]:
    """The outcomes a session objective can link to (those the user sees)."""
    target = target_of(request)
    assert target.module is not None
    options = await _options(db, target, ObjectiveLevel.LEARNING_EVENT, target.module.id)
    return await _option_reads(db, options)


@router.get("/taxonomy-scales", response_model=list[TaxonomyScaleRead])
async def list_taxonomy_scales(user: CurrentUser, db: DbSession) -> list[TaxonomyScaleRead]:
    """The taxonomy scales (Bloom, Miller...) with their levels, for an objective's level."""
    scales = await db.scalars(
        select(TaxonomyScale)
        .options(selectinload(TaxonomyScale.levels))
        .order_by(TaxonomyScale.name)
    )
    return [
        TaxonomyScaleRead(
            key=scale.key,
            name=scale.name,
            description=scale.description,
            levels=[TaxonomyLevelRead.model_validate(level) for level in scale.levels],
        )
        for scale in scales
    ]
