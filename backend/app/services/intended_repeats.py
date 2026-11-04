"""Intentional repeats (Slice 1.24a, ADR 053): framework items a programme teaches in many
sessions on purpose (a spiral curriculum). Marked by someone who may edit the programme's
curriculum; audited; removing a mark is a soft delete."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, ScopeType
from app.models import FrameworkItem, IntendedRepeat, User
from app.services.authorization import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    ScopeRef,
    has_permission,
)

MAX_REASON = 500


async def may_mark(db: AsyncSession, actor: User, programme_id: uuid.UUID) -> bool:
    """Marking needs ``curriculum.edit`` at the programme (a programme coordinator)."""
    return await has_permission(
        db, actor, Permission.CURRICULUM_EDIT, ScopeRef(ScopeType.PROGRAMME, programme_id)
    )


async def marked_items(
    db: AsyncSession, programme_id: uuid.UUID
) -> dict[uuid.UUID, IntendedRepeat]:
    """The programme's live marks by framework item."""
    rows = await db.scalars(
        select(IntendedRepeat).where(
            IntendedRepeat.programme_id == programme_id, IntendedRepeat.deleted_at.is_(None)
        )
    )
    return {row.framework_item_id: row for row in rows}


async def mark(
    db: AsyncSession,
    actor: User,
    programme_id: uuid.UUID,
    framework_id: uuid.UUID,
    code: str,
    reason: str,
) -> IntendedRepeat:
    """Mark the framework item with ``code`` as an intentional repeat.

    Raises:
        AuthorizationError: If the actor may not edit the programme's curriculum.
        InvalidRequestError: If the item is not in the framework or the reason is too long.
        ConflictError: If it is already marked.
    """
    if not await may_mark(db, actor, programme_id):
        raise AuthorizationError("You may not mark intentional repeats in this programme.")
    reason = reason.strip()
    if len(reason) > MAX_REASON:
        raise InvalidRequestError(f"The reason may be at most {MAX_REASON} characters.")
    item = await db.scalar(
        select(FrameworkItem).where(
            FrameworkItem.framework_id == framework_id, FrameworkItem.code == code.strip()
        )
    )
    if item is None:
        raise InvalidRequestError("That framework item does not exist.")
    if item.id in await marked_items(db, programme_id):
        raise ConflictError("That item is already marked as an intentional repeat.")
    row = IntendedRepeat(
        programme_id=programme_id,
        framework_item_id=item.id,
        reason=reason,
        created_by_id=actor.id,
    )
    db.add(row)
    await db.flush()
    return row


async def unmark(
    db: AsyncSession, actor: User, programme_id: uuid.UUID, mark_id: uuid.UUID
) -> None:
    """Remove a mark.

    Raises:
        AuthorizationError: If the actor may not edit the programme's curriculum.
        InvalidRequestError: If there is no such mark in the programme.
    """
    if not await may_mark(db, actor, programme_id):
        raise AuthorizationError("You may not mark intentional repeats in this programme.")
    row = await db.scalar(
        select(IntendedRepeat).where(
            IntendedRepeat.id == mark_id,
            IntendedRepeat.programme_id == programme_id,
            IntendedRepeat.deleted_at.is_(None),
        )
    )
    if row is None:
        raise InvalidRequestError("That mark does not exist.")
    row.soft_delete()
    await db.flush()
