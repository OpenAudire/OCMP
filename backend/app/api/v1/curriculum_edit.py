"""Editing the curriculum structure: phases, modules and learning events.

Each endpoint checks ``curriculum.edit`` at the narrowest scope that owns the
change (ADR 028):

- phases, adding modules, deleting modules and moving a module to another phase:
  the programme (through the curriculum version);
- changing a module and adding or deleting its sessions: the module;
- changing a session: the session.

Reordering and copying follow the same rules (ADR 029): phases and modules are the
programme's structure, sessions belong to their module.

A target the user cannot see is a 404, as in the read API (ADR 027); one they can
see but not change is a 403. Archived versions are read-only (409).
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, ScopeFromRequest, require_permission
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.models import CurriculumVersion, LearningEvent, Module, Objective, Phase, User
from app.schemas.curriculum import (
    LearningEventCopy,
    LearningEventCreate,
    LearningEventSaved,
    LearningEventUpdate,
    ModuleCopy,
    ModuleCreate,
    ModuleSaved,
    ModuleUpdate,
    MoveRequest,
    PhaseCopy,
    PhaseCreate,
    PhaseSaved,
    PhaseUpdate,
    TeachingFormat,
)
from app.services import curriculum_copy, curriculum_edit
from app.services.audit import audit_operation
from app.services.authorization import AuthorizationError, ScopeRef, has_permission
from app.services.curriculum_read import VisibleVersion, curriculum_access, visible_version
from app.services.tagging import teaching_formats, visible_faculty_ids

router = APIRouter(tags=["curriculum"])


@dataclass
class Target:
    """What a request edits, found (and checked visible) while resolving its scope."""

    visible: VisibleVersion
    phase: Phase | None = None
    module: Module | None = None
    event: LearningEvent | None = None
    objective: Objective | None = None

    @property
    def version(self) -> CurriculumVersion:
        return self.visible.version

    @property
    def programme_scope(self) -> ScopeRef:
        return ScopeRef(ScopeType.PROGRAMME, self.visible.programme.id)


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found.")


def path_id(request: Request, name: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(request.path_params[name]))
    except (KeyError, ValueError):
        raise not_found(what) from None


async def visible_or_404(
    db: AsyncSession, user: User, version_id: uuid.UUID, what: str
) -> VisibleVersion:
    visible = await visible_version(db, await curriculum_access(db, user), version_id)
    if visible is None:
        raise not_found(what)
    return visible


def store_target(request: Request, target: Target) -> None:
    request.state.curriculum_target = target


def target_of(request: Request) -> Target:
    target: Target = request.state.curriculum_target
    return target


async def _version_target(request: Request, db: AsyncSession, user: User) -> Target:
    what = "Curriculum version"
    version_id = path_id(request, "version_id", what)
    target = Target(await visible_or_404(db, user, version_id, what))
    store_target(request, target)
    return target


async def _phase_target(request: Request, db: AsyncSession, user: User) -> Target:
    phase_id = path_id(request, "phase_id", "Phase")
    phase = await db.scalar(select(Phase).where(Phase.id == phase_id, Phase.deleted_at.is_(None)))
    if phase is None:
        raise not_found("Phase")
    target = Target(await visible_or_404(db, user, phase.version_id, "Phase"), phase=phase)
    store_target(request, target)
    return target


async def _module_target(request: Request, db: AsyncSession, user: User) -> Target:
    return await module_target_for(request, db, user, path_id(request, "module_id", "Module"))


async def module_target_for(
    request: Request, db: AsyncSession, user: User, module_id: uuid.UUID
) -> Target:
    """The module with this id, if the user sees it (also stored on the request)."""
    module = await db.scalar(
        select(Module).where(Module.id == module_id, Module.deleted_at.is_(None))
    )
    if module is None:
        raise not_found("Module")
    visible = await visible_or_404(db, user, module.version_id, "Module")
    if not visible.view.shows_module(module.id):
        raise not_found("Module")
    target = Target(visible, module=module)
    store_target(request, target)
    return target


async def _event_target(request: Request, db: AsyncSession, user: User) -> Target:
    return await event_target_for(request, db, user, path_id(request, "event_id", "Learning event"))


async def event_target_for(
    request: Request, db: AsyncSession, user: User, event_id: uuid.UUID
) -> Target:
    """The session with this id, if the user sees it (also stored on the request)."""
    row = (
        await db.execute(
            select(LearningEvent, Module)
            .join(Module, Module.id == LearningEvent.module_id)
            .where(
                LearningEvent.id == event_id,
                LearningEvent.deleted_at.is_(None),
                Module.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("Learning event")
    event, module = row
    visible = await visible_or_404(db, user, module.version_id, "Learning event")
    if not visible.view.shows_event(module.id, event.id):
        raise not_found("Learning event")
    target = Target(visible, module=module, event=event)
    store_target(request, target)
    return target


async def version_programme(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    return (await _version_target(request, db, user)).programme_scope


async def phase_programme(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    return (await _phase_target(request, db, user)).programme_scope


async def module_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    target = await _module_target(request, db, user)
    assert target.module is not None
    return ScopeRef(ScopeType.MODULE, target.module.id)


async def module_programme(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    return (await _module_target(request, db, user)).programme_scope


async def event_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    target = await _event_target(request, db, user)
    assert target.event is not None
    return ScopeRef(ScopeType.LEARNING_EVENT, target.event.id)


async def event_module(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    target = await _event_target(request, db, user)
    assert target.module is not None
    return ScopeRef(ScopeType.MODULE, target.module.id)


def _editor(scope: ScopeFromRequest) -> Any:
    return Depends(require_permission(Permission.CURRICULUM_EDIT, scope=scope))


VersionEditor = Annotated[User, _editor(version_programme)]
PhaseEditor = Annotated[User, _editor(phase_programme)]
ModuleEditor = Annotated[User, _editor(module_scope)]
ModuleStructureEditor = Annotated[User, _editor(module_programme)]
EventEditor = Annotated[User, _editor(event_scope)]
# Removing, moving and copying a session change its module.
EventRemover = Annotated[User, _editor(event_module)]


# --- Phases -------------------------------------------------------------------------


@router.post(
    "/curriculum-versions/{version_id}/phases",
    response_model=PhaseSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_phase(
    version_id: uuid.UUID, body: PhaseCreate, request: Request, actor: VersionEditor, db: DbSession
) -> Phase:
    """Add a phase (year, block...) at the end of a version."""
    target = target_of(request)
    with audit_operation("curriculum.phase_create", actor_id=actor.id):
        return await curriculum_edit.create_phase(
            db, target.version, name=body.name, kind=body.kind, created_by_id=actor.id
        )


@router.patch("/phases/{phase_id}", response_model=PhaseSaved)
async def update_phase(
    phase_id: uuid.UUID, body: PhaseUpdate, request: Request, actor: PhaseEditor, db: DbSession
) -> Phase:
    """Rename a phase or change its kind."""
    target = target_of(request)
    assert target.phase is not None
    with audit_operation("curriculum.phase_update", actor_id=actor.id):
        return await curriculum_edit.update_phase(
            db, target.phase, target.version, body.model_dump(exclude_unset=True)
        )


@router.delete("/phases/{phase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phase(
    phase_id: uuid.UUID, request: Request, actor: PhaseEditor, db: DbSession
) -> Response:
    """Delete an empty phase (409 while it holds modules)."""
    target = target_of(request)
    assert target.phase is not None
    with audit_operation("curriculum.phase_delete", actor_id=actor.id):
        await curriculum_edit.delete_phase(db, target.phase, target.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/phases/{phase_id}/move", response_model=PhaseSaved)
async def move_phase(
    phase_id: uuid.UUID, body: MoveRequest, request: Request, actor: PhaseEditor, db: DbSession
) -> Phase:
    """Move a phase to another place in the version (0 is first)."""
    target = target_of(request)
    assert target.phase is not None
    with audit_operation("curriculum.phase_move", actor_id=actor.id):
        return await curriculum_edit.move_phase(db, target.phase, target.version, body.position)


@router.post(
    "/phases/{phase_id}/copy", response_model=PhaseSaved, status_code=status.HTTP_201_CREATED
)
async def copy_phase(
    phase_id: uuid.UUID, body: PhaseCopy, request: Request, actor: PhaseEditor, db: DbSession
) -> Phase:
    """Copy a phase with its modules, their sessions and objectives (one new code per
    module), right after it."""
    target = target_of(request)
    assert target.phase is not None
    with audit_operation("curriculum.phase_copy", actor_id=actor.id, source_id=phase_id):
        return await curriculum_copy.copy_phase(
            db,
            target.phase,
            target.version,
            name=body.name,
            module_codes=body.module_codes,
            created_by_id=actor.id,
        )


# --- Modules ------------------------------------------------------------------------


@router.post(
    "/curriculum-versions/{version_id}/modules",
    response_model=ModuleSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_module(
    version_id: uuid.UUID,
    body: ModuleCreate,
    request: Request,
    actor: VersionEditor,
    db: DbSession,
) -> Module:
    """Add a module to a phase of the version, or as a longitudinal module."""
    target = target_of(request)
    fields = curriculum_edit.ModuleFields(
        **body.model_dump(exclude={"external_lms_ref"}),
        external_lms_ref=body.external_lms_ref or None,
    )
    with audit_operation("curriculum.module_create", actor_id=actor.id):
        return await curriculum_edit.create_module(
            db, target.version, fields, created_by_id=actor.id
        )


@router.patch("/modules/{module_id}", response_model=ModuleSaved)
async def update_module(
    module_id: uuid.UUID,
    body: ModuleUpdate,
    request: Request,
    actor: ModuleEditor,
    db: DbSession,
) -> Module:
    """Change a module. Moving it to another phase needs edit rights for the programme."""
    target = target_of(request)
    module = target.module
    assert module is not None
    changes = body.model_dump(exclude_unset=True)
    if "external_lms_ref" in changes:
        changes["external_lms_ref"] = changes["external_lms_ref"] or None
    moves = "phase_id" in changes and changes["phase_id"] != module.phase_id
    if moves and not await has_permission(
        db, actor, Permission.CURRICULUM_EDIT, target.programme_scope
    ):
        raise AuthorizationError("Moving a module to another phase is a programme change.")
    with audit_operation("curriculum.module_update", actor_id=actor.id):
        return await curriculum_edit.update_module(db, module, target.version, changes)


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: uuid.UUID, request: Request, actor: ModuleStructureEditor, db: DbSession
) -> Response:
    """Delete a module with its sessions and their objectives (soft delete)."""
    target = target_of(request)
    assert target.module is not None
    with audit_operation("curriculum.module_delete", actor_id=actor.id):
        await curriculum_edit.delete_module(db, target.module, target.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/modules/{module_id}/move", response_model=ModuleSaved)
async def move_module(
    module_id: uuid.UUID,
    body: MoveRequest,
    request: Request,
    actor: ModuleStructureEditor,
    db: DbSession,
) -> Module:
    """Move a module to another place in its phase, or among the modules across phases."""
    target = target_of(request)
    assert target.module is not None
    with audit_operation("curriculum.module_move", actor_id=actor.id):
        return await curriculum_edit.move_module(db, target.module, target.version, body.position)


@router.post(
    "/modules/{module_id}/copy", response_model=ModuleSaved, status_code=status.HTTP_201_CREATED
)
async def copy_module(
    module_id: uuid.UUID,
    body: ModuleCopy,
    request: Request,
    actor: ModuleStructureEditor,
    db: DbSession,
) -> Module:
    """Copy a module with its sessions and objectives under a new code: right after it,
    or at the end of the phase given."""
    target = target_of(request)
    assert target.module is not None
    with audit_operation("curriculum.module_copy", actor_id=actor.id, source_id=module_id):
        return await curriculum_copy.copy_module(
            db,
            target.module,
            target.version,
            code=body.code,
            name=body.name,
            to_other_phase="phase_id" in body.model_fields_set,
            phase_id=body.phase_id,
            created_by_id=actor.id,
        )


# --- Learning events ----------------------------------------------------------------


@router.post(
    "/modules/{module_id}/learning-events",
    response_model=LearningEventSaved,
    status_code=status.HTTP_201_CREATED,
)
async def create_learning_event(
    module_id: uuid.UUID,
    body: LearningEventCreate,
    request: Request,
    actor: ModuleEditor,
    db: DbSession,
) -> LearningEvent:
    """Add a session at the end of a module."""
    target = target_of(request)
    assert target.module is not None
    fields = curriculum_edit.EventFields(
        **body.model_dump(exclude={"external_lms_ref"}),
        external_lms_ref=body.external_lms_ref or None,
    )
    with audit_operation("curriculum.learning_event_create", actor_id=actor.id):
        return await curriculum_edit.create_event(
            db, target.module, target.version, fields, created_by_id=actor.id
        )


@router.patch("/learning-events/{event_id}", response_model=LearningEventSaved)
async def update_learning_event(
    event_id: uuid.UUID,
    body: LearningEventUpdate,
    request: Request,
    actor: EventEditor,
    db: DbSession,
) -> LearningEvent:
    """Change a session."""
    target = target_of(request)
    assert target.event is not None
    changes = body.model_dump(exclude_unset=True)
    if "external_lms_ref" in changes:
        changes["external_lms_ref"] = changes["external_lms_ref"] or None
    with audit_operation("curriculum.learning_event_update", actor_id=actor.id):
        return await curriculum_edit.update_event(db, target.event, target.version, changes)


@router.delete("/learning-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning_event(
    event_id: uuid.UUID, request: Request, actor: EventRemover, db: DbSession
) -> Response:
    """Delete a session and its objectives (soft delete)."""
    target = target_of(request)
    assert target.event is not None
    with audit_operation("curriculum.learning_event_delete", actor_id=actor.id):
        await curriculum_edit.delete_event(db, target.event, target.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/learning-events/{event_id}/move", response_model=LearningEventSaved)
async def move_learning_event(
    event_id: uuid.UUID, body: MoveRequest, request: Request, actor: EventRemover, db: DbSession
) -> LearningEvent:
    """Move a session to another place in its module."""
    target = target_of(request)
    assert target.event is not None
    with audit_operation("curriculum.learning_event_move", actor_id=actor.id):
        return await curriculum_edit.move_event(db, target.event, target.version, body.position)


@router.post(
    "/learning-events/{event_id}/copy",
    response_model=LearningEventSaved,
    status_code=status.HTTP_201_CREATED,
)
async def copy_learning_event(
    event_id: uuid.UUID,
    body: LearningEventCopy,
    request: Request,
    actor: EventRemover,
    db: DbSession,
) -> LearningEvent:
    """Copy a session with its objectives, right after it."""
    target = target_of(request)
    assert target.event is not None
    with audit_operation("curriculum.learning_event_copy", actor_id=actor.id, source_id=event_id):
        return await curriculum_copy.copy_event(
            db, target.event, target.version, title=body.title, created_by_id=actor.id
        )


# --- Choices ------------------------------------------------------------------------


@router.get("/teaching-formats", response_model=list[TeachingFormat])
async def list_teaching_formats(user: CurrentUser, db: DbSession) -> list[TeachingFormat]:
    """Values that can be chosen as a session's format (active teaching-method lists)."""
    return [
        TeachingFormat(id=value.id, label=value.label, list_name=tag_list.name)
        for value, tag_list in await teaching_formats(db, await visible_faculty_ids(db, user))
    ]
