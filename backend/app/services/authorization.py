"""Scoped, role-based authorization.

A user holds roles at scopes. A role held at a scope applies to that scope and
everything inside it (instance > faculty > programme > module > learning
event), never to anything above it.

Each scope type registers how to find its parent. Instance and faculty are
registered here; curriculum scopes register themselves when their models exist.
"""

import re
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import SYSTEM_ROLE_KEYS, SYSTEM_ROLES, Permission, ScopeType, expand
from app.models import Faculty, Role, RoleAssignment, User


class AuthorizationError(PermissionError):
    """The acting user may not do this."""


class InvalidRequestError(ValueError):
    """The request is not valid (unknown scope, wrong scope type, missing expiry...)."""


class ConflictError(ValueError):
    """The change conflicts with existing data."""


@dataclass(frozen=True)
class ScopeRef:
    """A place a role can apply: the whole instance, or one faculty, programme, ..."""

    type: ScopeType
    id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if (self.type == ScopeType.INSTANCE) != (self.id is None):
            raise InvalidRequestError("Only the instance scope has no id.")


INSTANCE = ScopeRef(ScopeType.INSTANCE)

# Returns the parent scope, or None if no live row with that id exists.
ParentResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[ScopeRef | None]]
_parents: dict[ScopeType, ParentResolver] = {}


def register_scope(scope_type: ScopeType, parent: ParentResolver) -> None:
    """Declare how to find the parent of a scope type."""
    _parents[scope_type] = parent


async def _faculty_parent(db: AsyncSession, faculty_id: uuid.UUID) -> ScopeRef | None:
    found = await db.scalar(
        select(Faculty.id).where(Faculty.id == faculty_id, Faculty.deleted_at.is_(None))
    )
    return INSTANCE if found else None


register_scope(ScopeType.FACULTY, _faculty_parent)


async def lineage(db: AsyncSession, scope: ScopeRef) -> list[ScopeRef]:
    """The scope and all scopes containing it, ending with the instance.

    Raises:
        InvalidRequestError: If the scope type is not available or the scope does not exist.
    """
    chain = [scope]
    current = scope
    while current.type != ScopeType.INSTANCE:
        resolver = _parents.get(current.type)
        if resolver is None:
            raise InvalidRequestError(f"Scope type '{current.type}' is not available yet.")
        assert current.id is not None
        parent = await resolver(db, current.id)
        if parent is None:
            raise InvalidRequestError(f"No {current.type} with id {current.id}.")
        chain.append(parent)
        current = parent
    return chain


def _is_live(assignment: RoleAssignment, now: datetime) -> bool:
    return assignment.expires_at is None or assignment.expires_at > now


async def user_assignments(db: AsyncSession, user_id: uuid.UUID) -> list[RoleAssignment]:
    """A user's current (unexpired) role assignments, with their roles loaded."""
    result = await db.execute(
        select(RoleAssignment)
        .where(
            RoleAssignment.user_id == user_id,
            or_(RoleAssignment.expires_at.is_(None), RoleAssignment.expires_at > func.now()),
        )
        .options(selectinload(RoleAssignment.role))
        .order_by(RoleAssignment.created_at)
    )
    return list(result.scalars())


def role_permissions(role: Role) -> frozenset[Permission]:
    """A role's permissions (known ones only) plus everything they imply."""
    known = {p.value for p in Permission}
    return expand({Permission(p) for p in role.permissions if p in known})


async def permissions_at(db: AsyncSession, user: User, scope: ScopeRef) -> frozenset[Permission]:
    """Everything the user may do at a scope."""
    if not user.is_active or user.is_deleted:
        return frozenset()
    assignments = await user_assignments(db, user.id)
    if not assignments:
        return frozenset()
    scopes = set(await lineage(db, scope))
    granted: set[Permission] = set()
    for assignment in assignments:
        held_at = ScopeRef(ScopeType(assignment.scope_type), assignment.scope_id)
        if held_at in scopes:
            granted |= role_permissions(assignment.role)
    return frozenset(granted)


async def has_permission(
    db: AsyncSession, user: User, permission: Permission, scope: ScopeRef = INSTANCE
) -> bool:
    """Whether the user may do ``permission`` at ``scope``."""
    return permission in await permissions_at(db, user, scope)


# --- Role assignments ---------------------------------------------------------------


async def get_role(
    db: AsyncSession, *, role_id: uuid.UUID | None = None, key: str | None = None
) -> Role | None:
    """Find a role by id or key."""
    query = select(Role)
    query = query.where(Role.id == role_id) if role_id else query.where(Role.key == key)
    return (await db.execute(query)).scalar_one_or_none()


async def _check_may_grant(db: AsyncSession, actor: User, role: Role, scope: ScopeRef) -> None:
    """The actor needs roles.assign at the scope and every permission of the role there."""
    held = await permissions_at(db, actor, scope)
    if Permission.ROLES_ASSIGN not in held:
        raise AuthorizationError("You may not assign roles here.")
    if not role_permissions(role) <= held:
        raise AuthorizationError("You may not grant permissions you do not hold here.")


async def _active_platform_admins(db: AsyncSession) -> int:
    count = await db.scalar(
        select(func.count(func.distinct(RoleAssignment.user_id)))
        .join(Role, Role.id == RoleAssignment.role_id)
        .join(User, User.id == RoleAssignment.user_id)
        .where(
            Role.key == "platform_admin",
            RoleAssignment.scope_type == ScopeType.INSTANCE,
            or_(RoleAssignment.expires_at.is_(None), RoleAssignment.expires_at > func.now()),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return int(count or 0)


async def is_last_platform_admin(db: AsyncSession, user: User) -> bool:
    """Whether removing this user's admin access would leave no platform admin."""
    if await _active_platform_admins(db) != 1:
        return False
    return any(
        a.role.key == "platform_admin" and a.scope_type == ScopeType.INSTANCE
        for a in await user_assignments(db, user.id)
    )


async def assign_role(
    db: AsyncSession,
    actor: User | None,
    *,
    user: User,
    role: Role,
    scope: ScopeRef,
    expires_at: datetime | None = None,
) -> RoleAssignment:
    """Give a user a role at a scope.

    ``actor`` None means a system action (bootstrap command, setup wizard),
    which skips the permission check.

    Raises:
        AuthorizationError: If the actor may not grant this role here.
        InvalidRequestError: If the scope or expiry is not valid for the role.
        ConflictError: If the user already holds the role at this scope.
    """
    if scope.type not in role.scope_types:
        allowed = ", ".join(sorted(role.scope_types))
        raise InvalidRequestError(f"'{role.name}' can only be assigned at: {allowed}.")
    if role.requires_expiry and expires_at is None:
        raise InvalidRequestError(f"'{role.name}' assignments need an end date.")
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise InvalidRequestError("The end date must be in the future.")
    if user.is_deleted:
        raise InvalidRequestError("This user has been deleted.")
    await lineage(db, scope)  # the scope must exist
    if actor is not None:
        await _check_may_grant(db, actor, role, scope)

    existing = await db.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role_id == role.id,
            RoleAssignment.scope_type == scope.type,
            RoleAssignment.scope_id.is_(None)
            if scope.id is None
            else RoleAssignment.scope_id == scope.id,
        )
    )
    if existing:
        raise ConflictError("The user already has this role here.")

    assignment = RoleAssignment(
        user_id=user.id,
        role_id=role.id,
        scope_type=scope.type,
        scope_id=scope.id,
        expires_at=expires_at,
        created_by_id=actor.id if actor else None,
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment, attribute_names=["role"])
    return assignment


async def revoke_assignment(db: AsyncSession, actor: User, assignment: RoleAssignment) -> None:
    """Remove a role assignment.

    Raises:
        AuthorizationError: If the actor may not manage this role here.
        ConflictError: If it would remove the last platform admin.
    """
    scope = ScopeRef(ScopeType(assignment.scope_type), assignment.scope_id)
    await _check_may_grant(db, actor, assignment.role, scope)
    if assignment.role.key == "platform_admin":
        target = await db.get(User, assignment.user_id)
        if target is not None and await is_last_platform_admin(db, target):
            raise ConflictError("This is the last platform admin; assign another one first.")
    await db.delete(assignment)
    await db.flush()


# --- Roles --------------------------------------------------------------------------

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _validate_role_fields(permissions: Iterable[str], scope_types: Iterable[str]) -> None:
    known_permissions = {p.value for p in Permission}
    unknown = sorted(set(permissions) - known_permissions)
    if unknown:
        raise InvalidRequestError(f"Unknown permissions: {', '.join(unknown)}.")
    known_scopes = {s.value for s in ScopeType}
    scopes = set(scope_types)
    if not scopes:
        raise InvalidRequestError("A role needs at least one scope type.")
    if scopes - known_scopes:
        raise InvalidRequestError(
            f"Unknown scope types: {', '.join(sorted(scopes - known_scopes))}."
        )


async def create_custom_role(
    db: AsyncSession,
    actor: User,
    *,
    key: str,
    name: str,
    description: str,
    permissions: list[str],
    scope_types: list[str],
    requires_expiry: bool,
) -> Role:
    """Define a new role.

    Raises:
        InvalidRequestError: For an invalid key, permission or scope type.
        ConflictError: If the key is taken.
    """
    if not _KEY_PATTERN.match(key):
        raise InvalidRequestError("Key must be lowercase letters, digits and underscores.")
    _validate_role_fields(permissions, scope_types)
    if key in SYSTEM_ROLE_KEYS or await get_role(db, key=key) is not None:
        raise ConflictError("A role with this key already exists.")
    role = Role(
        key=key,
        name=name,
        description=description,
        is_system=False,
        permissions=sorted(set(permissions)),
        scope_types=sorted(set(scope_types)),
        requires_expiry=requires_expiry,
        created_by_id=actor.id,
    )
    db.add(role)
    await db.flush()
    return role


async def update_custom_role(
    db: AsyncSession,
    role: Role,
    *,
    name: str | None = None,
    description: str | None = None,
    permissions: list[str] | None = None,
    scope_types: list[str] | None = None,
    requires_expiry: bool | None = None,
) -> Role:
    """Change a custom role. System roles are defined in code and cannot be changed."""
    if role.is_system:
        raise ConflictError("System roles cannot be changed.")
    _validate_role_fields(
        permissions if permissions is not None else role.permissions,
        scope_types if scope_types is not None else role.scope_types,
    )
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if permissions is not None:
        role.permissions = sorted(set(permissions))
    if scope_types is not None:
        role.scope_types = sorted(set(scope_types))
    if requires_expiry is not None:
        role.requires_expiry = requires_expiry
    await db.flush()
    return role


async def delete_custom_role(db: AsyncSession, role: Role) -> None:
    """Delete a custom role that nobody holds."""
    if role.is_system:
        raise ConflictError("System roles cannot be deleted.")
    in_use = await db.scalar(select(RoleAssignment.id).where(RoleAssignment.role_id == role.id))
    if in_use:
        raise ConflictError("The role is still assigned; remove its assignments first.")
    await db.delete(role)
    await db.flush()


async def sync_system_roles(db: AsyncSession) -> list[Role]:
    """Create or update the system roles from their definitions in code."""
    synced = []
    for definition in SYSTEM_ROLES:
        role = await get_role(db, key=definition.key)
        if role is None:
            role = Role(key=definition.key)
            db.add(role)
        role.name = definition.name
        role.description = definition.description
        role.is_system = True
        role.permissions = sorted(p.value for p in definition.permissions)
        role.scope_types = sorted(s.value for s in definition.scope_types)
        role.requires_expiry = definition.requires_expiry
        synced.append(role)
    await db.flush()
    return synced


# Curriculum scope types (programme, module, learning event) live with the
# curriculum models. Registered here, after register_scope exists, so that any
# use of this module has every scope type available.
from app.services import curriculum_scopes  # noqa: E402

curriculum_scopes.register()
