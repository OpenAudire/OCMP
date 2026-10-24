"""Permissions, roles and role assignments."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, require_permission
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.permissions import IMPLIED, Permission, ScopeType
from app.models import Role, RoleAssignment, User
from app.schemas.roles import (
    AssignmentCreate,
    AssignmentRead,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from app.services.authorization import (
    ScopeRef,
    assign_role,
    create_custom_role,
    delete_custom_role,
    get_role,
    has_permission,
    revoke_assignment,
    update_custom_role,
)

router = APIRouter(tags=["roles"])
logger = get_logger(__name__)

RoleManager = Annotated[User, Depends(require_permission(Permission.ROLES_MANAGE))]


async def _role_or_404(db: DbSession, key: str) -> Role:
    role = await get_role(db, key=key)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
    return role


@router.get("/permissions", response_model=list[PermissionRead])
async def list_permissions(_user: CurrentUser) -> list[PermissionRead]:
    """Every permission a role can contain."""
    return [
        PermissionRead(key=p.value, implies=sorted(i.value for i in IMPLIED.get(p, ())))
        for p in Permission
    ]


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(_user: CurrentUser, db: DbSession) -> list[Role]:
    """System and custom roles."""
    result = await db.execute(select(Role).order_by(Role.is_system.desc(), Role.name))
    return list(result.scalars())


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(body: RoleCreate, actor: RoleManager, db: DbSession) -> Role:
    """Define a custom role."""
    role = await create_custom_role(
        db,
        actor,
        key=body.key,
        name=body.name,
        description=body.description,
        permissions=body.permissions,
        scope_types=[s.value for s in body.scope_types],
        requires_expiry=body.requires_expiry,
    )
    logger.info("role_created", role=role.key, actor_id=str(actor.id))
    return role


@router.patch("/roles/{key}", response_model=RoleRead)
async def update_role(key: str, body: RoleUpdate, actor: RoleManager, db: DbSession) -> Role:
    """Change a custom role."""
    role = await update_custom_role(
        db,
        await _role_or_404(db, key),
        name=body.name,
        description=body.description,
        permissions=body.permissions,
        scope_types=[s.value for s in body.scope_types] if body.scope_types else None,
        requires_expiry=body.requires_expiry,
    )
    logger.info("role_updated", role=role.key, actor_id=str(actor.id))
    return role


@router.delete("/roles/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(key: str, actor: RoleManager, db: DbSession) -> None:
    """Delete a custom role that nobody holds."""
    await delete_custom_role(db, await _role_or_404(db, key))
    logger.info("role_deleted", role=key, actor_id=str(actor.id))


@router.get("/role-assignments", response_model=list[AssignmentRead])
async def list_assignments_at_scope(
    actor: CurrentUser,
    db: DbSession,
    scope_type: ScopeType,
    scope_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RoleAssignment]:
    """Who holds roles at exactly this scope. Needs roles.assign there."""
    scope = ScopeRef(scope_type, scope_id)
    if not await has_permission(db, actor, Permission.ROLES_ASSIGN, scope):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed here.")
    result = await db.execute(
        select(RoleAssignment)
        .where(
            RoleAssignment.scope_type == scope.type,
            RoleAssignment.scope_id.is_(None)
            if scope.id is None
            else RoleAssignment.scope_id == scope.id,
        )
        .options(selectinload(RoleAssignment.role))
        .order_by(RoleAssignment.created_at)
    )
    return list(result.scalars())


@router.post(
    "/role-assignments", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED
)
async def create_assignment(
    body: AssignmentCreate, actor: CurrentUser, db: DbSession
) -> RoleAssignment:
    """Give a user a role at a scope.

    Needs roles.assign at the scope and every permission of the role there.
    """
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    assignment = await assign_role(
        db,
        actor,
        user=user,
        role=await _role_or_404(db, body.role_key),
        scope=ScopeRef(body.scope_type, body.scope_id),
        expires_at=body.expires_at,
    )
    logger.info(
        "role_assigned",
        assignment_id=str(assignment.id),
        role=body.role_key,
        user_id=str(user.id),
        actor_id=str(actor.id),
    )
    return assignment


@router.delete("/role-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(assignment_id: uuid.UUID, actor: CurrentUser, db: DbSession) -> None:
    """Remove a role assignment."""
    result = await db.execute(
        select(RoleAssignment)
        .where(RoleAssignment.id == assignment_id)
        .options(selectinload(RoleAssignment.role))
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    await revoke_assignment(db, actor, assignment)
    logger.info("role_revoked", assignment_id=str(assignment_id), actor_id=str(actor.id))
