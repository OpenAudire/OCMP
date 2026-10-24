"""Framework rules that the database alone does not enforce."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Crosswalk, CrosswalkEntry, Framework, FrameworkCrossRef, FrameworkItem
from app.models.framework import CrossRefType, CrosswalkEntryType, FrameworkStatus
from app.services.authorization import ConflictError, InvalidRequestError


async def add_item(
    db: AsyncSession,
    framework: Framework,
    *,
    code: str,
    title: str,
    parent: FrameworkItem | None = None,
    description: str = "",
    position: int = 0,
    metadata: dict[str, Any] | None = None,
    created_by_id: uuid.UUID | None = None,
) -> FrameworkItem:
    """Add an item to a framework, under ``parent`` or at the top level.

    Raises:
        InvalidRequestError: If the parent is in another framework or the code is blank.
        ConflictError: If the code is already used in this framework.
    """
    code = code.strip()
    if not code or not title.strip():
        raise InvalidRequestError("Items need a code and a title.")
    if parent is not None and parent.framework_id != framework.id:
        raise InvalidRequestError("The parent item belongs to another framework.")
    taken = await db.scalar(
        select(FrameworkItem.id).where(
            FrameworkItem.framework_id == framework.id, FrameworkItem.code == code
        )
    )
    if taken:
        raise ConflictError(f"Code '{code}' is already used in this framework.")

    item = FrameworkItem(
        framework_id=framework.id,
        parent_id=parent.id if parent else None,
        depth=parent.depth + 1 if parent else 0,
        code=code,
        title=title.strip(),
        description=description,
        position=position,
        item_metadata=metadata or {},
        created_by_id=created_by_id,
    )
    db.add(item)
    await db.flush()
    return item


async def add_cross_ref(
    db: AsyncSession,
    from_item: FrameworkItem,
    to_item: FrameworkItem,
    ref_type: CrossRefType,
    *,
    created_by_id: uuid.UUID | None = None,
) -> FrameworkCrossRef:
    """Link two items, in the same framework or across frameworks.

    Raises:
        InvalidRequestError: For a link from an item to itself.
        ConflictError: If the same link already exists.
    """
    if from_item.id == to_item.id:
        raise InvalidRequestError("An item cannot reference itself.")
    exists = await db.scalar(
        select(FrameworkCrossRef.id).where(
            FrameworkCrossRef.from_item_id == from_item.id,
            FrameworkCrossRef.to_item_id == to_item.id,
            FrameworkCrossRef.type == ref_type,
        )
    )
    if exists:
        raise ConflictError("This cross-reference already exists.")
    ref = FrameworkCrossRef(
        from_item_id=from_item.id,
        to_item_id=to_item.id,
        type=ref_type,
        created_by_id=created_by_id,
    )
    db.add(ref)
    await db.flush()
    return ref


_NEEDS = {
    CrosswalkEntryType.EQUIVALENT: (True, True),
    CrosswalkEntryType.SPLIT: (True, True),
    CrosswalkEntryType.MERGED: (True, True),
    CrosswalkEntryType.REMOVED: (True, False),
    CrosswalkEntryType.NEW: (False, True),
}


async def add_crosswalk_entry(
    db: AsyncSession,
    crosswalk: Crosswalk,
    entry_type: CrosswalkEntryType,
    *,
    from_item: FrameworkItem | None = None,
    to_item: FrameworkItem | None = None,
    notes: str = "",
    created_by_id: uuid.UUID | None = None,
) -> CrosswalkEntry:
    """Record how an item moves from the old framework version to the new one.

    Raises:
        InvalidRequestError: If the items do not fit the entry type or belong to
            the wrong framework.
    """
    needs_from, needs_to = _NEEDS[entry_type]
    if (from_item is not None) != needs_from or (to_item is not None) != needs_to:
        raise InvalidRequestError(
            f"A '{entry_type.value}' entry needs "
            f"{'an old item' if needs_from else 'no old item'} and "
            f"{'a new item' if needs_to else 'no new item'}."
        )
    if from_item is not None and from_item.framework_id != crosswalk.from_framework_id:
        raise InvalidRequestError("The old item is not in the crosswalk's source framework.")
    if to_item is not None and to_item.framework_id != crosswalk.to_framework_id:
        raise InvalidRequestError("The new item is not in the crosswalk's target framework.")

    entry = CrosswalkEntry(
        crosswalk_id=crosswalk.id,
        type=entry_type,
        from_item_id=from_item.id if from_item else None,
        to_item_id=to_item.id if to_item else None,
        notes=notes,
        created_by_id=created_by_id,
    )
    db.add(entry)
    await db.flush()
    return entry


async def activate_framework(db: AsyncSession, framework: Framework) -> list[uuid.UUID]:
    """Make a framework version the active one; earlier active versions become superseded.

    Returns:
        The ids of the versions that were superseded.
    """
    if framework.is_deleted:
        raise InvalidRequestError("A deleted framework cannot be activated.")
    # ORM updates (not a bulk UPDATE) so each status change reaches the audit log.
    result = await db.execute(
        select(Framework).where(
            Framework.key == framework.key,
            Framework.id != framework.id,
            Framework.status == FrameworkStatus.ACTIVE,
            Framework.deleted_at.is_(None),
        )
    )
    superseded = []
    for older in result.scalars():
        older.status = FrameworkStatus.SUPERSEDED
        superseded.append(older.id)
    framework.status = FrameworkStatus.ACTIVE
    await db.flush()
    return superseded
