"""Curriculum versions: publishing, copying a year forward, deleting drafts, and diffs.

Permissions (ADR 030), all at the version's programme:

- changing the status (publish, unpublish, archive, unarchive): ``curriculum.publish``;
  returning a published version to draft also needs ``curriculum.unpublish`` and a written
  reason, recorded in the audit log (ADR 032);
- copying forward and deleting a draft: ``curriculum.edit``; copying role assignments
  also needs ``roles.assign`` and every permission of each role copied;
- comparing two versions: seeing both versions whole.

A version the user cannot see is a 404 (ADR 027); one they can see but not change is
a 403. Changes that the version's status does not allow are a 409.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import ScopeFromRequest, SettingsDep, require_permission
from app.api.v1.curriculum import Access
from app.api.v1.curriculum_edit import version_programme
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.jobs.embeddings import enqueue_pending
from app.models import CurriculumVersion, User
from app.models.embedding import EmbeddedType
from app.schemas.curriculum import (
    ChangeCounts,
    CopyForwardPreview,
    CopyForwardRequest,
    FieldChangeRead,
    ItemChangeRead,
    ProgrammeRef,
    RoleAssignmentCopy,
    VersionDiffRead,
    VersionRead,
    VersionStatusChange,
)
from app.services import curriculum_versions
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    InvalidRequestError,
    ScopeRef,
    has_permission,
)
from app.services.curriculum_diff import Change, ItemKind, diff_versions
from app.services.curriculum_read import VisibleVersion, visible_version

router = APIRouter(tags=["curriculum"])


def _permission(permission: Permission, scope: ScopeFromRequest) -> Any:
    return Depends(require_permission(permission, scope=scope))


VersionPublisher = Annotated[User, _permission(Permission.CURRICULUM_PUBLISH, version_programme)]
VersionEditor = Annotated[User, _permission(Permission.CURRICULUM_EDIT, version_programme)]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Curriculum version not found."
    )


def _whole(request: Request) -> VisibleVersion:
    """The version resolved for the permission check; it must be visible whole."""
    visible: VisibleVersion = request.state.curriculum_target.visible
    if not visible.view.full:
        raise _not_found()
    return visible


@router.post("/curriculum-versions/{version_id}/status", response_model=VersionRead)
async def change_version_status(
    version_id: uuid.UUID,
    body: VersionStatusChange,
    request: Request,
    actor: VersionPublisher,
    db: DbSession,
) -> CurriculumVersion:
    """Publish a draft, return a published version to draft, archive a published version
    or publish an archived one again."""
    visible = _whole(request)
    version = visible.version
    name = curriculum_versions.transition(version, body.status)
    details: dict[str, str] = {}
    if name == "unpublish":
        scope = ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
        if not await has_permission(db, actor, Permission.CURRICULUM_UNPUBLISH, scope):
            raise AuthorizationError("Only a programme director can return a published year.")
        if not body.reason:
            raise InvalidRequestError("Give a reason for returning a published version to draft.")
        details["reason"] = body.reason
    with audit_operation(f"curriculum.version_{name}", actor_id=actor.id, **details):
        return await curriculum_versions.change_status(db, version, body.status)


@router.delete("/curriculum-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    version_id: uuid.UUID, request: Request, actor: VersionEditor, db: DbSession
) -> Response:
    """Delete a draft version with everything in it (soft delete)."""
    version = _whole(request).version
    with audit_operation("curriculum.version_delete", actor_id=actor.id):
        await curriculum_versions.delete_draft(db, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/curriculum-versions/{version_id}/copy-forward", response_model=CopyForwardPreview)
async def preview_copy_forward(
    version_id: uuid.UUID, request: Request, actor: VersionEditor, db: DbSession
) -> CopyForwardPreview:
    """What copying the version forward would make, a suggested academic year, and the
    role assignments at its modules and sessions (for people who may assign roles)."""
    preview = await curriculum_versions.forward_preview(db, actor, _whole(request).version)
    return CopyForwardPreview(
        academic_year=preview.academic_year,
        taken_years=preview.taken_years,
        phases=preview.phases,
        modules=preview.modules,
        learning_events=preview.learning_events,
        objectives=preview.objectives,
        mappings=preview.mappings,
        can_copy_roles=preview.can_copy_roles,
        role_assignments=[
            RoleAssignmentCopy(
                id=copy.assignment.id,
                user_name=copy.assignment.user.display_name,
                role_name=copy.assignment.role.name,
                scope_type="module" if copy.assignment.scope_type == "module" else "learning_event",
                item=copy.item,
                expires_at=copy.assignment.expires_at,
                skip_reason=copy.skip_reason,
            )
            for copy in preview.role_assignments
        ],
    )


@router.post(
    "/curriculum-versions/{version_id}/copy-forward",
    response_model=VersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def copy_forward(
    version_id: uuid.UUID,
    body: CopyForwardRequest,
    request: Request,
    actor: VersionEditor,
    db: DbSession,
    settings: SettingsDep,
) -> CurriculumVersion:
    """Copy the version, with everything in it, to a new draft for another academic year."""
    version = _whole(request).version
    with audit_operation(
        "curriculum.version_copy_forward", actor_id=actor.id, source_id=version_id
    ):
        copy = await curriculum_versions.copy_forward(
            db,
            actor,
            version,
            academic_year=body.academic_year,
            role_assignment_ids=body.role_assignment_ids,
        )
    enqueue_pending(settings, EmbeddedType.OBJECTIVE)
    return copy


@router.get("/curriculum-versions/{version_id}/diff", response_model=VersionDiffRead)
async def get_version_diff(
    version_id: uuid.UUID,
    access: Access,
    db: DbSession,
    base: Annotated[uuid.UUID, Query(description="The version to compare against.")],
) -> VersionDiffRead:
    """What changed from the ``base`` version to this one (same programme)."""
    visible = await visible_version(db, access, version_id)
    other = await visible_version(db, access, base)
    if visible is None or other is None or not visible.view.full or not other.view.full:
        raise _not_found()
    if base == version_id or other.programme.id != visible.programme.id:
        raise InvalidRequestError("Compare two different versions of the same programme.")
    diff = await diff_versions(db, other.version, visible.version)
    programme = visible.programme
    return VersionDiffRead(
        programme=ProgrammeRef(id=programme.id, code=programme.code, name=programme.name),
        base=VersionRead.model_validate(diff.base),
        version=VersionRead.model_validate(diff.version),
        summary={
            kind: ChangeCounts(
                added=diff.count(kind, Change.ADDED),
                removed=diff.count(kind, Change.REMOVED),
                changed=diff.count(kind, Change.CHANGED),
            )
            for kind in ItemKind
        },
        changes=[
            ItemChangeRead(
                kind=change.kind,
                change=change.change,
                id=change.id,
                base_id=change.base_id,
                label=change.label,
                context=change.context,
                level=change.level,
                fields=[
                    FieldChangeRead(field=f.field, before=f.before, after=f.after)
                    for f in change.fields
                ],
            )
            for change in diff.changes
        ],
    )
