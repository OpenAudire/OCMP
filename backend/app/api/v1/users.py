"""User administration."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, RedisDep, SettingsDep, require_permission
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.permissions import Permission
from app.core.security import PasswordPolicyError
from app.models import RoleAssignment, User
from app.schemas.roles import AssignmentRead
from app.schemas.users import UserAdminRead, UserCreate, UserList, UserUpdate
from app.services import sessions
from app.services.authorization import (
    ConflictError,
    InvalidRequestError,
    has_permission,
    is_last_platform_admin,
    user_assignments,
)
from app.services.users import (
    InvalidEmailError,
    UserAlreadyExistsError,
    create_local_user,
    list_users,
)

router = APIRouter(prefix="/users", tags=["users"])
logger = get_logger(__name__)

UserManager = Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))]


async def _user_or_404(db: DbSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("", response_model=UserList)
async def get_users(
    _actor: UserManager,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UserList:
    """Users, newest first."""
    users, total = await list_users(db, search=search, offset=offset, limit=limit)
    return UserList(items=[UserAdminRead.model_validate(u) for u in users], total=total)


@router.post("", response_model=UserAdminRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, actor: UserManager, db: DbSession, settings: SettingsDep
) -> User:
    """Create a local account. Give it roles with a role assignment."""
    try:
        user = await create_local_user(
            db,
            settings,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
            created_by_id=actor.id,
        )
    except (InvalidEmailError, PasswordPolicyError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    except UserAlreadyExistsError as exc:
        raise ConflictError(str(exc)) from exc
    logger.info("user_created", user_id=str(user.id), actor_id=str(actor.id))
    return user


@router.get("/{user_id}", response_model=UserAdminRead)
async def get_user(user_id: uuid.UUID, _actor: UserManager, db: DbSession) -> User:
    return await _user_or_404(db, user_id)


@router.patch("/{user_id}", response_model=UserAdminRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    actor: UserManager,
    db: DbSession,
    redis: RedisDep,
) -> User:
    """Rename, deactivate or reactivate a user. Deactivation ends their sessions."""
    user = await _user_or_404(db, user_id)
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.is_active is False and user.is_active:
        if user.id == actor.id:
            raise ConflictError("You cannot deactivate your own account.")
        if await is_last_platform_admin(db, user):
            raise ConflictError("This is the last platform admin; assign another one first.")
        user.is_active = False
        await sessions.revoke_user_sessions(redis, user.id)
        logger.info("user_deactivated", user_id=str(user.id), actor_id=str(actor.id))
    elif body.is_active is True and not user.is_active:
        user.is_active = True
        logger.info("user_reactivated", user_id=str(user.id), actor_id=str(actor.id))
    await db.flush()
    return user


@router.get("/{user_id}/role-assignments", response_model=list[AssignmentRead])
async def get_user_assignments(
    user_id: uuid.UUID, actor: CurrentUser, db: DbSession
) -> list[RoleAssignment]:
    """A user's current roles. Users may see their own; otherwise needs users.manage."""
    if actor.id != user_id and not await has_permission(db, actor, Permission.USERS_MANAGE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed.")
    await _user_or_404(db, user_id)
    return await user_assignments(db, user_id)
