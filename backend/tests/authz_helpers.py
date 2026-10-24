"""Helpers for authorization tests."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ScopeType
from app.models import Faculty, RoleAssignment, User
from app.services import authorization
from app.services.authorization import INSTANCE, ScopeRef, assign_role, get_role
from tests.factories import FacultyFactory, UserFactory


@dataclass
class ScopeTree:
    """Stand-in programme > module > learning event hierarchy (real tables come in 0.9)."""

    parents: dict[ScopeRef, ScopeRef] = field(default_factory=dict)

    def add(self, scope_type: ScopeType, parent: ScopeRef) -> ScopeRef:
        scope = ScopeRef(scope_type, uuid.uuid4())
        self.parents[scope] = parent
        return scope

    def programme(self, faculty: ScopeRef) -> ScopeRef:
        return self.add(ScopeType.PROGRAMME, faculty)

    def module(self, programme: ScopeRef) -> ScopeRef:
        return self.add(ScopeType.MODULE, programme)

    def learning_event(self, module: ScopeRef) -> ScopeRef:
        return self.add(ScopeType.LEARNING_EVENT, module)


@contextmanager
def curriculum_scopes() -> Iterator[ScopeTree]:
    """Register the stand-in curriculum scope types for the duration of a test."""
    tree = ScopeTree()
    saved = dict(authorization._parents)

    def resolver(scope_type: ScopeType):  # type: ignore[no-untyped-def]
        async def parent(_db: AsyncSession, scope_id: uuid.UUID) -> ScopeRef | None:
            return tree.parents.get(ScopeRef(scope_type, scope_id))

        return parent

    for scope_type in (ScopeType.PROGRAMME, ScopeType.MODULE, ScopeType.LEARNING_EVENT):
        authorization.register_scope(scope_type, resolver(scope_type))
    try:
        yield tree
    finally:
        authorization._parents.clear()
        authorization._parents.update(saved)


async def new_faculty(db: AsyncSession) -> tuple[Faculty, ScopeRef]:
    faculty = FacultyFactory()
    db.add(faculty)
    await db.flush()
    return faculty, ScopeRef(ScopeType.FACULTY, faculty.id)


async def new_user(db: AsyncSession, **kwargs: object) -> User:
    user = UserFactory(**kwargs)
    db.add(user)
    await db.flush()
    return user


async def grant(
    db: AsyncSession,
    user: User,
    role_key: str,
    scope: ScopeRef = INSTANCE,
    expires_at: datetime | None = None,
) -> RoleAssignment:
    """Assign a role as a system action (no permission check)."""
    role = await get_role(db, key=role_key)
    assert role is not None, role_key
    return await assign_role(db, None, user=user, role=role, scope=scope, expires_at=expires_at)
