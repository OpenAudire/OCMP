"""Tag lists, tag values and taggings.

Inheritance rules (which tags flow down to which items, with a preview before
saving) are built with the tagging UI in phase 1. This module stores inherited
taggings with their source, so removing a source tag removes what it passed on.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import LearningEvent, Module, Objective, Programme, Tagging, TagList, TagValue
from app.models.tagging import TAGGING_COLUMNS, TaggableType, TagListKind
from app.services.authorization import ConflictError, InvalidRequestError

Taggable = Programme | Module | LearningEvent | Objective

_TYPE_OF: dict[type, TaggableType] = {
    Programme: TaggableType.PROGRAMME,
    Module: TaggableType.MODULE,
    LearningEvent: TaggableType.LEARNING_EVENT,
    Objective: TaggableType.OBJECTIVE,
}


def taggable_type(item: Taggable) -> TaggableType:
    """The taggable type of a curriculum item."""
    return _TYPE_OF[type(item)]


async def add_tag_value(
    db: AsyncSession,
    tag_list: TagList,
    label: str,
    *,
    code: str | None = None,
    description: str = "",
    position: int = 0,
    created_by_id: uuid.UUID | None = None,
) -> TagValue:
    """Add a value to a list.

    Raises:
        InvalidRequestError: If the label is blank or the list is deleted.
        ConflictError: If the label or code is already used in the list.
    """
    label = label.strip()
    if not label:
        raise InvalidRequestError("A tag needs a label.")
    if tag_list.is_deleted:
        raise InvalidRequestError("This tag list has been deleted.")
    live = select(TagValue.id).where(
        TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
    )
    if await db.scalar(live.where(TagValue.label == label)):
        raise ConflictError(f"'{label}' is already in this list.")
    if code and await db.scalar(live.where(TagValue.code == code)):
        raise ConflictError(f"Code '{code}' is already used in this list.")

    value = TagValue(
        tag_list_id=tag_list.id,
        label=label,
        code=code or None,
        description=description,
        position=position,
        created_by_id=created_by_id,
    )
    db.add(value)
    await db.flush()
    return value


async def _usable_value(db: AsyncSession, value: TagValue) -> TagList:
    """The value's list, if both can be used for new tags."""
    tag_list = await db.get(TagList, value.tag_list_id)
    if tag_list is None or tag_list.is_deleted or not tag_list.is_active:
        raise InvalidRequestError("This tag list is not available.")
    if value.is_deleted or not value.is_active:
        raise InvalidRequestError("This tag is not available.")
    return tag_list


async def tag_item(
    db: AsyncSession,
    value: TagValue,
    item: Taggable,
    *,
    inherited_from: Tagging | None = None,
    created_by_id: uuid.UUID | None = None,
) -> Tagging:
    """Apply a tag to a curriculum item.

    Raises:
        InvalidRequestError: If the tag or list is unavailable, the list does not
            apply to this kind of item, or the item is deleted.
        ConflictError: If the item already has this tag from the same source.
    """
    tag_list = await _usable_value(db, value)
    item_type = taggable_type(item)
    if item_type.value not in tag_list.entity_types:
        raise InvalidRequestError(f"'{tag_list.name}' cannot be used on a {item_type.value}.")
    if item.is_deleted:
        raise InvalidRequestError("Cannot tag a deleted item.")
    if inherited_from is not None and inherited_from.tag_value_id != value.id:
        raise InvalidRequestError("An inherited tag must be the same tag as its source.")

    column = TAGGING_COLUMNS[item_type]
    source_id = inherited_from.id if inherited_from else None
    exists = await db.scalar(
        select(Tagging.id).where(
            Tagging.tag_value_id == value.id,
            getattr(Tagging, column) == item.id,
            Tagging.inherited_from_id.is_(None)
            if source_id is None
            else Tagging.inherited_from_id == source_id,
        )
    )
    if exists:
        raise ConflictError("The item already has this tag.")

    tagging = Tagging(
        tag_value_id=value.id,
        inherited_from_id=source_id,
        created_by_id=created_by_id,
        **{column: item.id},
    )
    db.add(tagging)
    await db.flush()
    return tagging


async def remove_tagging(db: AsyncSession, tagging: Tagging) -> None:
    """Remove a tag that was set directly; tags it passed on go with it.

    Raises:
        InvalidRequestError: For an inherited tag (remove it at its source).
    """
    if tagging.is_inherited:
        raise InvalidRequestError("This tag is inherited; remove it where it was set.")
    await db.delete(tagging)
    await db.flush()


async def item_taggings(db: AsyncSession, item: Taggable) -> Sequence[Tagging]:
    """All tags on an item (direct and inherited), with their values loaded."""
    column = TAGGING_COLUMNS[taggable_type(item)]
    result = await db.execute(
        select(Tagging)
        .where(getattr(Tagging, column) == item.id)
        .options(selectinload(Tagging.tag_value))
        .order_by(Tagging.created_at)
    )
    return result.scalars().all()


async def set_teaching_format(
    db: AsyncSession, event: LearningEvent, value: TagValue | None
) -> None:
    """Set (or clear) a learning event's teaching format.

    Raises:
        InvalidRequestError: If the value is not from a usable teaching-method list.
    """
    if value is not None:
        tag_list = await _usable_value(db, value)
        if tag_list.kind != TagListKind.TEACHING_METHOD:
            raise InvalidRequestError("The format must come from a teaching-method list.")
    event.format_value_id = value.id if value else None
    await db.flush()
