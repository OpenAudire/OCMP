"""The mapping workspace: link objectives to framework items by hand (ADR 039).

Reading a version's objectives and links shows what the user may see of the version
(ADR 027; not visible = 404). Making, changing and removing a link needs ``mapping.edit``
at the objective's scope (the programme for programme outcomes, the module, or the
session); confirming that a link still fits after the objective's wording changed needs
``mapping.review``. Only draft versions can be changed (409).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, ScopeFromRequest, require_permission
from app.api.v1.curriculum_edit import not_found, path_id, target_of, visible_or_404
from app.api.v1.curriculum_objectives import objective_scope_for
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import FrameworkItem, MappingLink, Objective, User
from app.models.mapping import MappingStatus
from app.schemas.mapping import (
    LinkCreate,
    LinkRemoved,
    LinkUpdate,
    MappingWorkspace,
    WorkspaceLink,
)
from app.services import mapping as mapping_service
from app.services import mapping_links
from app.services.audit import audit_operation
from app.services.authorization import InvalidRequestError, ScopeRef, has_permission
from app.services.curriculum_scopes import objective_scope
from app.services.mapping_workspace import link_read, mapping_workspace
from app.services.policies import mapping_policy_for

router = APIRouter(tags=["mapping"])


async def objective_link_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    """The scope of the objective in the path, if the user sees it."""
    return await objective_scope_for(
        request, db, user, path_id(request, "objective_id", "Objective")
    )


async def _live_link(db: AsyncSession, link_id: uuid.UUID) -> MappingLink:
    link = await db.get(MappingLink, link_id)
    # A rejected link is not a mapping: it is hidden like a missing one.
    if link is None or link.status == MappingStatus.REJECTED:
        raise not_found("Link")
    return link


async def link_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    """The scope of the objective that owns the link in the path, if the user sees it."""
    link = await _live_link(db, path_id(request, "link_id", "Link"))
    return await objective_scope_for(request, db, user, link.objective_id)


def _holding(permission: Permission, scope: ScopeFromRequest) -> Any:
    return Depends(require_permission(permission, scope=scope))


ObjectiveMapper = Annotated[User, _holding(Permission.MAPPING_EDIT, objective_link_scope)]
LinkMapper = Annotated[User, _holding(Permission.MAPPING_EDIT, link_scope)]
LinkReviewer = Annotated[User, _holding(Permission.MAPPING_REVIEW, link_scope)]


@router.get("/curriculum-versions/{version_id}/mapping", response_model=MappingWorkspace)
async def get_mapping_workspace(
    version_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MappingWorkspace:
    """The objectives of a version with their links, and what the user may do to each."""
    visible = await visible_or_404(db, user, version_id, "Curriculum version")
    return await mapping_workspace(db, visible)


async def _can_review(db: AsyncSession, actor: User, objective: Objective) -> bool:
    return await has_permission(
        db, actor, Permission.MAPPING_REVIEW, await objective_scope(db, objective)
    )


@router.post(
    "/objectives/{objective_id}/mapping-links",
    response_model=WorkspaceLink,
    status_code=status.HTTP_201_CREATED,
)
async def add_mapping_link(
    objective_id: uuid.UUID,
    body: LinkCreate,
    request: Request,
    actor: ObjectiveMapper,
    db: DbSession,
) -> WorkspaceLink:
    """Link the objective to a framework item with coverage and depth.

    A reviewer's link is accepted (or waits for a second reviewer in four-eyes mode);
    anyone else makes a suggestion. A rejected link for the same pair is reopened."""
    objective = target_of(request).objective
    assert objective is not None
    item = await db.get(FrameworkItem, body.framework_item_id)
    if item is None:
        raise InvalidRequestError("That framework item does not exist.")
    policy = await mapping_policy_for(db, objective)
    with audit_operation("mapping.link_add", actor_id=actor.id):
        link = await mapping_links.add_link(
            db,
            objective,
            item,
            actor,
            can_review=await _can_review(db, actor, objective),
            policy=policy,
            coverage=body.coverage,
            depth_match=body.depth_match,
            rationale=body.rationale,
        )
    return await link_read(db, link)


@router.patch("/mapping-links/{link_id}", response_model=WorkspaceLink)
async def update_mapping_link(
    link_id: uuid.UUID,
    body: LinkUpdate,
    request: Request,
    actor: LinkMapper,
    db: DbSession,
) -> WorkspaceLink:
    """Change a link's coverage, depth or reason. It is decided again (see ADR 039)."""
    objective = target_of(request).objective
    assert objective is not None
    link = await _live_link(db, link_id)
    policy = await mapping_policy_for(db, objective)
    with audit_operation("mapping.link_update", actor_id=actor.id):
        await mapping_links.update_link(
            db,
            link,
            actor,
            mapping_links.LinkChange(body.coverage, body.depth_match, body.rationale),
            can_review=await _can_review(db, actor, objective),
            policy=policy,
        )
    return await link_read(db, link)


@router.delete("/mapping-links/{link_id}", response_model=LinkRemoved)
async def remove_mapping_link(
    link_id: uuid.UUID, request: Request, actor: LinkMapper, db: DbSession
) -> LinkRemoved:
    """Remove a link. A link the AI suggested is rejected instead of deleted."""
    objective = target_of(request).objective
    assert objective is not None
    link = await _live_link(db, link_id)
    with audit_operation("mapping.link_remove", actor_id=actor.id):
        deleted = await mapping_links.remove_link(
            db, link, can_review=await _can_review(db, actor, objective)
        )
    return LinkRemoved(deleted=deleted)


@router.post("/mapping-links/{link_id}/recheck", response_model=WorkspaceLink)
async def confirm_mapping_recheck(
    link_id: uuid.UUID, request: Request, actor: LinkReviewer, db: DbSession
) -> WorkspaceLink:
    """Confirm that an accepted link still fits after its objective's wording changed."""
    objective = target_of(request).objective
    assert objective is not None
    link = await _live_link(db, link_id)
    await mapping_links.ensure_objective_open(db, objective)
    await mapping_service.confirm_recheck(db, actor, link)
    return await link_read(db, link)
