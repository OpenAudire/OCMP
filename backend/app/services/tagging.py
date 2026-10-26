"""Tag lists, tag values and taggings.

Inheritance (ADR 034): a tag set directly on a module flows to its sessions, and a tag
set directly on an objective flows to the objectives linked beneath it (programme
outcome to module outcomes and session objectives, module outcome to session
objectives). The person sees a preview of every item it would reach before saving.
Every inherited tagging points to the direct tagging it came from, so the source is
always known and removing the direct tag removes what it passed on.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Programme,
    Tagging,
    TagList,
    TagValue,
)
from app.models.curriculum import ObjectiveLevel
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
    # Through the ORM (not only the database cascade) so the audit log records each one.
    passed_on = await db.scalars(select(Tagging).where(Tagging.inherited_from_id == tagging.id))
    for inherited in passed_on:
        await db.delete(inherited)
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


async def teaching_formats(db: AsyncSession) -> list[tuple[TagValue, TagList]]:
    """Values that can be chosen as a session's teaching format, by list and position."""
    result = await db.execute(
        select(TagValue, TagList)
        .join(TagList, TagList.id == TagValue.tag_list_id)
        .where(
            TagList.kind == TagListKind.TEACHING_METHOD,
            TagList.deleted_at.is_(None),
            TagList.is_active.is_(True),
            TagValue.deleted_at.is_(None),
            TagValue.is_active.is_(True),
        )
        .order_by(TagList.name, TagValue.position, TagValue.label)
    )
    return [(value, tag_list) for value, tag_list in result.all()]


# --- Managing lists and values (curriculum office) -----------------------------------


async def create_tag_list(
    db: AsyncSession,
    *,
    key: str,
    name: str,
    kind: TagListKind,
    description: str = "",
    entity_types: Sequence[TaggableType],
    created_by_id: uuid.UUID | None = None,
) -> TagList:
    """Add a tag list.

    Raises:
        ConflictError: If a live list already has this key.
    """
    if await db.scalar(select(TagList.id).where(TagList.key == key, TagList.deleted_at.is_(None))):
        raise ConflictError(f"A list with the key '{key}' already exists.")
    tag_list = TagList(
        key=key,
        name=name,
        kind=kind,
        description=description,
        entity_types=[t.value for t in entity_types],
        created_by_id=created_by_id,
    )
    db.add(tag_list)
    await db.flush()
    return tag_list


async def update_tag_list(
    db: AsyncSession,
    tag_list: TagList,
    *,
    name: str | None = None,
    description: str | None = None,
    entity_types: Sequence[TaggableType] | None = None,
    is_active: bool | None = None,
) -> TagList:
    """Change a list. Its key and kind stay fixed (imports and formats rely on them).

    Narrowing the item types leaves existing tags in place; only new tags are checked.
    """
    if tag_list.is_deleted:
        raise InvalidRequestError("This tag list has been deleted.")
    if name is not None:
        tag_list.name = name
    if description is not None:
        tag_list.description = description
    if entity_types is not None:
        tag_list.entity_types = [t.value for t in entity_types]
    if is_active is not None:
        tag_list.is_active = is_active
    await db.flush()
    return tag_list


async def value_usage(db: AsyncSession, value_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """How many taggings and sessions (as teaching format) use each value."""
    if not value_ids:
        return {}
    usage: dict[uuid.UUID, int] = {}
    tagged = select(Tagging.tag_value_id, func.count()).where(Tagging.tag_value_id.in_(value_ids))
    formats = select(LearningEvent.format_value_id, func.count()).where(
        LearningEvent.format_value_id.in_(value_ids), LearningEvent.deleted_at.is_(None)
    )
    for query in (
        tagged.group_by(Tagging.tag_value_id),
        formats.group_by(LearningEvent.format_value_id),
    ):
        for value_id, count in await db.execute(query):
            if value_id is not None:
                usage[value_id] = usage.get(value_id, 0) + count
    return usage


async def delete_tag_value(db: AsyncSession, value: TagValue) -> None:
    """Delete a value that nothing uses.

    Raises:
        InvalidRequestError: If it is already deleted.
        ConflictError: If it is on an item or is a session's format (deactivate it).
    """
    if value.is_deleted:
        raise InvalidRequestError("This tag has been deleted.")
    if (await value_usage(db, [value.id])).get(value.id):
        raise ConflictError("This tag is in use. Make it inactive instead.")
    value.soft_delete()
    await db.flush()


async def delete_tag_list(db: AsyncSession, tag_list: TagList) -> None:
    """Delete a list whose values nothing uses (the values go with it).

    Raises:
        InvalidRequestError: If it is already deleted.
        ConflictError: If any of its values is in use (deactivate the list instead).
    """
    if tag_list.is_deleted:
        raise InvalidRequestError("This tag list has been deleted.")
    values = list(
        await db.scalars(
            select(TagValue).where(
                TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
            )
        )
    )
    if any((await value_usage(db, [v.id for v in values])).values()):
        raise ConflictError("This list is in use. Make it inactive instead.")
    for value in values:
        value.soft_delete()
    tag_list.soft_delete()
    await db.flush()


async def update_tag_value(
    db: AsyncSession,
    value: TagValue,
    *,
    label: str | None = None,
    code: str | None = None,
    clear_code: bool = False,
    description: str | None = None,
    is_active: bool | None = None,
) -> TagValue:
    """Change a value; the label and code stay unique within the list.

    Raises:
        InvalidRequestError: If the label is blank or the value is deleted.
        ConflictError: If the label or code is used by another value of the list.
    """
    if value.is_deleted:
        raise InvalidRequestError("This tag has been deleted.")
    others = select(TagValue.id).where(
        TagValue.tag_list_id == value.tag_list_id,
        TagValue.deleted_at.is_(None),
        TagValue.id != value.id,
    )
    if label is not None:
        label = label.strip()
        if not label:
            raise InvalidRequestError("A tag needs a label.")
        if await db.scalar(others.where(TagValue.label == label)):
            raise ConflictError(f"'{label}' is already in this list.")
        value.label = label
    if clear_code:
        value.code = None
    elif code is not None:
        if await db.scalar(others.where(TagValue.code == code)):
            raise ConflictError(f"Code '{code}' is already used in this list.")
        value.code = code
    if description is not None:
        value.description = description
    if is_active is not None:
        value.is_active = is_active
    await db.flush()
    return value


async def next_value_position(db: AsyncSession, tag_list: TagList) -> int:
    """The position after the list's last live value."""
    last = await db.scalar(
        select(func.max(TagValue.position)).where(
            TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
        )
    )
    return 0 if last is None else last + 1


# --- Inheritance ---------------------------------------------------------------------

_LEVEL_ORDER = {
    ObjectiveLevel.PROGRAMME: 0,
    ObjectiveLevel.MODULE: 1,
    ObjectiveLevel.LEARNING_EVENT: 2,
}


async def inheriting_items(db: AsyncSession, item: Taggable) -> list[Taggable]:
    """The items a tag set on ``item`` would flow to (live ones only).

    A module passes tags to its sessions; an objective to the objectives linked
    beneath it, at any level below, in the same version.
    """
    if isinstance(item, Module):
        sessions = await db.scalars(
            select(LearningEvent)
            .where(LearningEvent.module_id == item.id, LearningEvent.deleted_at.is_(None))
            .order_by(LearningEvent.position, LearningEvent.title)
        )
        return list(sessions)
    if isinstance(item, Objective):
        found: dict[uuid.UUID, Objective] = {}
        frontier = [item.id]
        while frontier:
            rows = await db.scalars(
                select(Objective)
                .join(ObjectiveLink, ObjectiveLink.child_id == Objective.id)
                .where(
                    ObjectiveLink.parent_id.in_(frontier),
                    Objective.deleted_at.is_(None),
                    Objective.version_id == item.version_id,
                )
            )
            frontier = []
            for below in rows:
                if below.id != item.id and below.id not in found:
                    found[below.id] = below
                    frontier.append(below.id)
        below_items = sorted(found.values(), key=lambda o: (_LEVEL_ORDER[o.level], o.position))
        return [*below_items]
    return []


@dataclass
class InheritanceEntry:
    """One item a tag would flow to, and what would happen to it."""

    item_type: TaggableType
    item: Taggable
    # new: gets the tag; has_tag: already carries it directly; not_applicable: the
    # list is not used on this kind of item.
    status: str


@dataclass
class InheritancePreview:
    tag_list: TagList
    item_has_tag: bool
    entries: list[InheritanceEntry] = field(default_factory=list)


async def _has_direct_tag(db: AsyncSession, value: TagValue, item: Taggable) -> bool:
    column = getattr(Tagging, TAGGING_COLUMNS[taggable_type(item)])
    found = await db.scalar(
        select(Tagging.id).where(
            Tagging.tag_value_id == value.id,
            column == item.id,
            Tagging.inherited_from_id.is_(None),
        )
    )
    return found is not None


async def inheritance_preview(
    db: AsyncSession, value: TagValue, item: Taggable
) -> InheritancePreview:
    """Every item that tagging ``item`` with ``value`` would reach, before saving.

    Raises:
        InvalidRequestError: If the tag or its list is unavailable.
    """
    tag_list = await _usable_value(db, value)
    preview = InheritancePreview(
        tag_list=tag_list, item_has_tag=await _has_direct_tag(db, value, item)
    )
    for below in await inheriting_items(db, item):
        kind = taggable_type(below)
        if kind.value not in tag_list.entity_types:
            status = "not_applicable"
        elif await _has_direct_tag(db, value, below):
            status = "has_tag"
        else:
            status = "new"
        preview.entries.append(InheritanceEntry(kind, below, status))
    return preview


async def apply_tag(
    db: AsyncSession,
    value: TagValue,
    item: Taggable,
    *,
    inherit: bool,
    created_by_id: uuid.UUID | None = None,
) -> tuple[Tagging, list[Tagging]]:
    """Tag an item directly and, when asked, pass the tag to what the preview lists as new.

    Returns the direct tagging and the inherited ones.

    Raises:
        InvalidRequestError, ConflictError: As ``tag_item``.
    """
    preview = await inheritance_preview(db, value, item) if inherit else None
    tagging = await tag_item(db, value, item, created_by_id=created_by_id)
    inherited = []
    if preview is not None:
        for entry in preview.entries:
            if entry.status == "new":
                inherited.append(
                    await tag_item(
                        db, value, entry.item, inherited_from=tagging, created_by_id=created_by_id
                    )
                )
    return tagging, inherited


# --- Reading the tags of items -------------------------------------------------------


@dataclass
class TagSource:
    """The item an inherited tag came from."""

    item_type: TaggableType
    item_id: uuid.UUID
    name: str


@dataclass
class ItemTag:
    """One tag on one item: set directly, inherited from one or more sources, or both."""

    value: TagValue
    tag_list: TagList
    direct_tagging_id: uuid.UUID | None = None
    sources: list[TagSource] = field(default_factory=list)


def tagging_item(tagging: Tagging) -> tuple[TaggableType, uuid.UUID]:
    """Which item a tagging is on."""
    for item_type, column in TAGGING_COLUMNS.items():
        item_id = getattr(tagging, column)
        if item_id is not None:
            return item_type, item_id
    raise ValueError("A tagging belongs to one item.")  # pragma: no cover - CHECK constraint


def excerpt(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


async def _source_names(
    db: AsyncSession, wanted: dict[TaggableType, set[uuid.UUID]]
) -> dict[tuple[TaggableType, uuid.UUID], str]:
    """Names of live source items: a module's code and name, a session's title, an
    objective's wording."""
    names: dict[tuple[TaggableType, uuid.UUID], str] = {}
    if modules := wanted.get(TaggableType.MODULE):
        for module in await db.scalars(
            select(Module).where(Module.id.in_(modules), Module.deleted_at.is_(None))
        ):
            names[(TaggableType.MODULE, module.id)] = f"{module.code} {module.name}"
    if events := wanted.get(TaggableType.LEARNING_EVENT):
        for event in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.id.in_(events), LearningEvent.deleted_at.is_(None)
            )
        ):
            names[(TaggableType.LEARNING_EVENT, event.id)] = event.title
    if objectives := wanted.get(TaggableType.OBJECTIVE):
        for objective in await db.scalars(
            select(Objective).where(Objective.id.in_(objectives), Objective.deleted_at.is_(None))
        ):
            names[(TaggableType.OBJECTIVE, objective.id)] = excerpt(objective.text)
    return names


async def item_tags(
    db: AsyncSession, items: dict[TaggableType, Sequence[uuid.UUID]]
) -> dict[tuple[TaggableType, uuid.UUID], list[ItemTag]]:
    """The tags of many items, one entry per item and tag, with the source of each
    inherited one. Deleted tags and lists, and tags whose source item was deleted, are
    left out."""
    conditions = [
        getattr(Tagging, TAGGING_COLUMNS[item_type]).in_(list(ids))
        for item_type, ids in items.items()
        if ids
    ]
    if not conditions:
        return {}
    rows = (
        await db.execute(
            select(Tagging, TagValue, TagList)
            .join(TagValue, TagValue.id == Tagging.tag_value_id)
            .join(TagList, TagList.id == TagValue.tag_list_id)
            .where(or_(*conditions), TagValue.deleted_at.is_(None), TagList.deleted_at.is_(None))
            .order_by(TagList.name, TagValue.position, TagValue.label, Tagging.created_at)
        )
    ).all()
    source_ids = {t.inherited_from_id for t, _, _ in rows if t.inherited_from_id}
    origins: dict[uuid.UUID, tuple[TaggableType, uuid.UUID]] = {}
    wanted: dict[TaggableType, set[uuid.UUID]] = {}
    if source_ids:
        for origin_tagging in await db.scalars(select(Tagging).where(Tagging.id.in_(source_ids))):
            item_type, item_id = tagging_item(origin_tagging)
            origins[origin_tagging.id] = (item_type, item_id)
            wanted.setdefault(item_type, set()).add(item_id)
    names = await _source_names(db, wanted)

    result: dict[tuple[TaggableType, uuid.UUID], list[ItemTag]] = {}
    by_key: dict[tuple[TaggableType, uuid.UUID, uuid.UUID], ItemTag] = {}
    for tagging, value, tag_list in rows:
        item_type, item_id = tagging_item(tagging)
        source: TagSource | None = None
        if tagging.inherited_from_id:
            origin = origins.get(tagging.inherited_from_id)
            name = names.get(origin) if origin else None
            if origin is None or name is None:
                continue  # the source item was deleted
            source = TagSource(origin[0], origin[1], name)
        key = (item_type, item_id, value.id)
        entry = by_key.get(key)
        if entry is None:
            entry = ItemTag(value=value, tag_list=tag_list)
            by_key[key] = entry
            result.setdefault((item_type, item_id), []).append(entry)
        if source is None:
            entry.direct_tagging_id = tagging.id
        elif all(s.item_id != source.item_id for s in entry.sources):
            entry.sources.append(source)
    return result
