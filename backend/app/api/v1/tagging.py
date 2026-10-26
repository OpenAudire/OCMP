"""Tag lists (managed by the curriculum office) and tagging curriculum items (ADR 034).

Managing a list needs ``taglists.manage`` at the list's scope: its faculty, or the whole
instance for an institution-wide list (a faculty manager cannot change those). Tagging a
module, session or objective needs ``tagging.edit`` at the scope that owns the item (the
module, the session, or the programme for a programme outcome); an item the user cannot
see is a 404 (ADR 027), and only draft versions can be changed (409). Inherited tags
are removed where they were set, never one by one (422).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.v1.curriculum_edit import (
    Target,
    event_target_for,
    module_target_for,
    not_found,
    path_id,
    target_of,
)
from app.api.v1.curriculum_objectives import objective_scope_for
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.models import (
    Faculty,
    LearningEvent,
    Module,
    Objective,
    Tagging,
    TagList,
    TagValue,
    User,
)
from app.models.tagging import TaggableType
from app.schemas.tagging import (
    FacultyRef,
    InheritancePreviewRead,
    PreviewItem,
    TagApplied,
    TaggableKind,
    TagListCreate,
    TagListPlaces,
    TagListRead,
    TagListUpdate,
    TagRequest,
    TagValueCreate,
    TagValueRead,
    TagValueUpdate,
    item_tag_reads,
)
from app.services import tagging as tagging_service
from app.services.audit import audit_operation
from app.services.authorization import INSTANCE, InvalidRequestError, ScopeRef, has_permission
from app.services.curriculum_edit import ensure_editable
from app.services.tagging import Taggable

router = APIRouter(tags=["tagging"])


# --- Tag lists and values -----------------------------------------------------------


async def _list_or_404(db: AsyncSession, list_id: uuid.UUID) -> TagList:
    tag_list = await db.scalar(
        select(TagList).where(TagList.id == list_id, TagList.deleted_at.is_(None))
    )
    if tag_list is None:
        raise not_found("Tag list")
    return tag_list


async def _value_or_404(db: AsyncSession, value_id: uuid.UUID) -> TagValue:
    value = await db.scalar(
        select(TagValue)
        .join(TagList, TagList.id == TagValue.tag_list_id)
        .where(
            TagValue.id == value_id,
            TagValue.deleted_at.is_(None),
            TagList.deleted_at.is_(None),
        )
    )
    if value is None:
        raise not_found("Tag")
    return value


async def list_manage_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    """The scope that manages the list in the path: its faculty, else the instance."""
    tag_list = await _list_or_404(db, path_id(request, "list_id", "Tag list"))
    return tagging_service.list_scope(tag_list)


async def value_manage_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    """The scope that manages the list of the tag in the path."""
    value = await _value_or_404(db, path_id(request, "value_id", "Tag"))
    tag_list = await db.get(TagList, value.tag_list_id)
    assert tag_list is not None
    return tagging_service.list_scope(tag_list)


def _manager(scope: Any) -> Any:
    return Depends(require_permission(Permission.TAGLISTS_MANAGE, scope=scope))


ListManager = Annotated[User, _manager(list_manage_scope)]
ValueManager = Annotated[User, _manager(value_manage_scope)]


def _value_read(value: TagValue, usage: int = 0) -> TagValueRead:
    return TagValueRead(
        id=value.id,
        label=value.label,
        code=value.code,
        description=value.description,
        position=value.position,
        is_active=value.is_active,
        usage_count=usage,
    )


async def _list_read(
    db: AsyncSession, tag_list: TagList, *, manager: bool, faculty_name: str | None = None
) -> TagListRead:
    values = list(
        await db.scalars(
            select(TagValue)
            .where(TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None))
            .order_by(TagValue.position, TagValue.label)
        )
    )
    usage = await tagging_service.value_usage(db, [v.id for v in values]) if manager else {}
    if tag_list.faculty_id is not None and faculty_name is None:
        faculty_name = await db.scalar(
            select(Faculty.name).where(Faculty.id == tag_list.faculty_id)
        )
    return TagListRead(
        id=tag_list.id,
        key=tag_list.key,
        name=tag_list.name,
        kind=tag_list.kind,
        description=tag_list.description,
        entity_types=list(tag_list.entity_types),
        is_active=tag_list.is_active,
        faculty_id=tag_list.faculty_id,
        faculty_name=faculty_name,
        can_manage=manager,
        values=[_value_read(v, usage.get(v.id, 0)) for v in values if manager or v.is_active],
    )


@router.get("/tag-lists", response_model=list[TagListRead])
async def list_tag_lists(user: CurrentUser, db: DbSession) -> list[TagListRead]:
    """Tag lists with their values. Everyone signed in gets the active institution-wide
    lists and those of their faculties (to tag with). People who manage a list also get
    its inactive tags and how often each tag is used, and see it when it is inactive."""
    management = await tagging_service.list_management(db, user)
    visible = await tagging_service.visible_faculty_ids(db, user)
    lists = await db.scalars(
        select(TagList)
        .where(TagList.deleted_at.is_(None), tagging_service.list_visibility(visible))
        .order_by(TagList.name)
    )
    names = dict((await db.execute(select(Faculty.id, Faculty.name))).all())
    reads = []
    for tag_list in lists:
        manager = management.covers(tag_list.faculty_id)
        if not tag_list.is_active and not manager:
            continue
        reads.append(
            await _list_read(
                db,
                tag_list,
                manager=manager,
                faculty_name=names.get(tag_list.faculty_id) if tag_list.faculty_id else None,
            )
        )
    return reads


@router.get("/tag-lists/places", response_model=TagListPlaces)
async def tag_list_places(user: CurrentUser, db: DbSession) -> TagListPlaces:
    """Where this user may create tag lists: the whole institution and/or some faculties."""
    management = await tagging_service.list_management(db, user)
    query = select(Faculty.id, Faculty.name).where(Faculty.deleted_at.is_(None))
    if not management.instance:
        query = query.where(Faculty.id.in_(management.faculties))
    faculties = (await db.execute(query.order_by(Faculty.name))).all()
    return TagListPlaces(
        institution=management.instance,
        faculties=[FacultyRef(id=i, name=n) for i, n in faculties],
    )


@router.post("/tag-lists", response_model=TagListRead, status_code=status.HTTP_201_CREATED)
async def create_tag_list(body: TagListCreate, actor: CurrentUser, db: DbSession) -> TagListRead:
    """Add a tag list: institution-wide, or for one faculty with ``faculty_id``. Needs
    ``taglists.manage`` for that faculty (a faculty manager cannot add institution-wide lists)."""
    scope = INSTANCE if body.faculty_id is None else ScopeRef(ScopeType.FACULTY, body.faculty_id)
    if not await has_permission(db, actor, Permission.TAGLISTS_MANAGE, scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to do this.",
        )
    with audit_operation("taglist.create", actor_id=actor.id):
        tag_list = await tagging_service.create_tag_list(
            db,
            key=body.key,
            name=body.name,
            kind=body.kind,
            description=body.description,
            entity_types=[TaggableType(t) for t in body.entity_types],
            faculty_id=body.faculty_id,
            created_by_id=actor.id,
        )
    return await _list_read(db, tag_list, manager=True)


@router.patch("/tag-lists/{list_id}", response_model=TagListRead)
async def update_tag_list(
    list_id: uuid.UUID, body: TagListUpdate, actor: ListManager, db: DbSession
) -> TagListRead:
    """Change a list's name, description, item types or active flag."""
    tag_list = await _list_or_404(db, list_id)
    with audit_operation("taglist.update", actor_id=actor.id):
        await tagging_service.update_tag_list(
            db,
            tag_list,
            name=body.name,
            description=body.description,
            entity_types=[TaggableType(t) for t in body.entity_types]
            if body.entity_types is not None
            else None,
            is_active=body.is_active,
        )
    return await _list_read(db, tag_list, manager=True)


@router.delete("/tag-lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag_list(list_id: uuid.UUID, actor: ListManager, db: DbSession) -> Response:
    """Delete a list nothing uses (409 if any of its tags is in use: make it inactive)."""
    tag_list = await _list_or_404(db, list_id)
    with audit_operation("taglist.delete", actor_id=actor.id):
        await tagging_service.delete_tag_list(db, tag_list)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tag-lists/{list_id}/values",
    response_model=TagValueRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tag_value(
    list_id: uuid.UUID, body: TagValueCreate, actor: ListManager, db: DbSession
) -> TagValueRead:
    """Add a tag at the end of a list."""
    tag_list = await _list_or_404(db, list_id)
    with audit_operation("tagvalue.create", actor_id=actor.id):
        value = await tagging_service.add_tag_value(
            db,
            tag_list,
            body.label,
            code=body.code,
            description=body.description,
            position=await tagging_service.next_value_position(db, tag_list),
            created_by_id=actor.id,
        )
    return _value_read(value)


@router.patch("/tag-values/{value_id}", response_model=TagValueRead)
async def update_tag_value(
    value_id: uuid.UUID, body: TagValueUpdate, actor: ValueManager, db: DbSession
) -> TagValueRead:
    """Change a tag's label, code, description or active flag."""
    value = await _value_or_404(db, value_id)
    with audit_operation("tagvalue.update", actor_id=actor.id):
        await tagging_service.update_tag_value(
            db,
            value,
            label=body.label,
            code=body.code,
            clear_code="code" in body.model_fields_set and body.code is None,
            description=body.description,
            is_active=body.is_active,
        )
    usage = await tagging_service.value_usage(db, [value.id])
    return _value_read(value, usage.get(value.id, 0))


@router.delete("/tag-values/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag_value(value_id: uuid.UUID, actor: ValueManager, db: DbSession) -> Response:
    """Delete a tag nothing uses (409 if it is in use: make it inactive)."""
    value = await _value_or_404(db, value_id)
    with audit_operation("tagvalue.delete", actor_id=actor.id):
        await tagging_service.delete_tag_value(db, value)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Tagging items ------------------------------------------------------------------


async def _scope_of(
    request: Request, db: AsyncSession, user: User, kind: str, item_id: uuid.UUID
) -> ScopeRef:
    """The scope that owns the item; a 404 unless the user sees it."""
    if kind == "module":
        await module_target_for(request, db, user, item_id)
        return ScopeRef(ScopeType.MODULE, item_id)
    if kind == "learning_event":
        await event_target_for(request, db, user, item_id)
        return ScopeRef(ScopeType.LEARNING_EVENT, item_id)
    if kind == "objective":
        return await objective_scope_for(request, db, user, item_id)
    raise not_found("Item")


async def item_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    kind = str(request.path_params.get("item_type", ""))
    return await _scope_of(request, db, user, kind, path_id(request, "item_id", "Item"))


async def tagging_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    tagging = await db.get(Tagging, path_id(request, "tagging_id", "Tag"))
    if tagging is None:
        raise not_found("Tag")
    item_type, item_id = tagging_service.tagging_item(tagging)
    if item_type == TaggableType.PROGRAMME:
        raise not_found("Tag")
    return await _scope_of(request, db, user, item_type.value, item_id)


def _tagger(scope: Any) -> Any:
    return Depends(require_permission(Permission.TAGGING_EDIT, scope=scope))


ItemTagger = Annotated[User, _tagger(item_scope)]
TaggingTagger = Annotated[User, _tagger(tagging_scope)]


def _item(target: Target, kind: str) -> Taggable:
    item: Taggable | None
    if kind == "module":
        item = target.module
    elif kind == "learning_event":
        item = target.event
    else:
        item = target.objective
    assert item is not None
    return item


async def _tags_of(db: AsyncSession, item: Taggable) -> TagApplied:
    item_type = tagging_service.taggable_type(item)
    found = await tagging_service.item_tags(db, {item_type: [item.id]})
    return TagApplied(tags=item_tag_reads(found.get((item_type, item.id), [])), inherited_count=0)


async def _preview_items(
    db: AsyncSession, entries: list[tagging_service.InheritanceEntry]
) -> list[PreviewItem]:
    """Names for the preview, with the code of the module each item sits in."""
    event_ids = {e.item.id for e in entries if isinstance(e.item, LearningEvent)} | {
        e.item.learning_event_id
        for e in entries
        if isinstance(e.item, Objective) and e.item.learning_event_id
    }
    event_module = dict(
        (
            await db.execute(
                select(LearningEvent.id, LearningEvent.module_id).where(
                    LearningEvent.id.in_(event_ids)
                )
            )
        ).all()
    )
    module_ids = {
        e.item.module_id for e in entries if isinstance(e.item, Objective) and e.item.module_id
    } | set(event_module.values())
    codes = dict(
        (await db.execute(select(Module.id, Module.code).where(Module.id.in_(module_ids)))).all()
    )
    items: list[PreviewItem] = []
    for entry in entries:
        item = entry.item
        level = None
        module_id: uuid.UUID | None
        if isinstance(item, LearningEvent):
            name, module_id = item.title, item.module_id
        elif isinstance(item, Objective):
            name, level = tagging_service.excerpt(item.text), item.level
            module_id = item.module_id
            if module_id is None and item.learning_event_id is not None:
                module_id = event_module.get(item.learning_event_id)
        else:  # pragma: no cover - modules and programmes receive nothing
            continue
        items.append(
            PreviewItem(
                item_type=entry.item_type,
                item_id=item.id,
                name=name,
                level=level,
                module_code=codes.get(module_id) if module_id else None,
                status=entry.status,
            )
        )
    return items


@router.get(
    "/curriculum-items/{item_type}/{item_id}/tag-preview", response_model=InheritancePreviewRead
)
async def preview_tag(
    item_type: TaggableKind,
    item_id: uuid.UUID,
    tag_value_id: uuid.UUID,
    request: Request,
    actor: ItemTagger,
    db: DbSession,
) -> InheritancePreviewRead:
    """Every item that tagging this one with the tag would reach, before saving."""
    value = await db.get(TagValue, tag_value_id)
    if value is None or value.is_deleted:
        raise InvalidRequestError("This tag is not available.")
    item = _item(target_of(request), item_type)
    preview = await tagging_service.inheritance_preview(db, value, item)
    return InheritancePreviewRead(
        tag_value_id=value.id,
        label=value.label,
        list_name=preview.tag_list.name,
        item_has_tag=preview.item_has_tag,
        items=await _preview_items(db, preview.entries),
    )


@router.post(
    "/curriculum-items/{item_type}/{item_id}/tags",
    response_model=TagApplied,
    status_code=status.HTTP_201_CREATED,
)
async def tag_curriculum_item(
    item_type: TaggableKind,
    item_id: uuid.UUID,
    body: TagRequest,
    request: Request,
    actor: ItemTagger,
    db: DbSession,
) -> TagApplied:
    """Tag a module, session or objective, and with ``inherit`` pass the tag to the items
    in the preview that do not have it yet. Draft versions only."""
    target = target_of(request)
    ensure_editable(target.version)
    value = await db.get(TagValue, body.tag_value_id)
    if value is None or value.is_deleted:
        raise InvalidRequestError("This tag is not available.")
    item = _item(target, item_type)
    with audit_operation(
        "tagging.add", actor_id=actor.id, tag_value_id=value.id, inherit=body.inherit
    ):
        _, inherited = await tagging_service.apply_tag(
            db, value, item, inherit=body.inherit, created_by_id=actor.id
        )
    applied = await _tags_of(db, item)
    applied.inherited_count = len(inherited)
    return applied


async def _tagging_and_item(
    request: Request, tagging_id: uuid.UUID, db: AsyncSession
) -> tuple[Tagging, Taggable]:
    """The tagging in the path and the (module or objective) item it is on."""
    tagging = await db.get(Tagging, tagging_id)
    if tagging is None:  # pragma: no cover - the scope resolver found it
        raise not_found("Tag")
    item_type, _ = tagging_service.tagging_item(tagging)
    return tagging, _item(target_of(request), item_type.value)


@router.get("/taggings/{tagging_id}/pass-on-preview", response_model=InheritancePreviewRead)
async def preview_pass_on(
    tagging_id: uuid.UUID, request: Request, actor: TaggingTagger, db: DbSession
) -> InheritancePreviewRead:
    """The items below a directly tagged item that the tag has not reached yet (linked or
    added after it was set), before passing it on. Items marked ``new`` would get it."""
    tagging, item = await _tagging_and_item(request, tagging_id, db)
    value, preview, _ = await tagging_service.pass_on_preview(db, tagging, item)
    return InheritancePreviewRead(
        tag_value_id=value.id,
        label=value.label,
        list_name=preview.tag_list.name,
        item_has_tag=True,
        items=await _preview_items(db, preview.entries),
    )


@router.post(
    "/taggings/{tagging_id}/pass-on",
    response_model=TagApplied,
    status_code=status.HTTP_201_CREATED,
)
async def pass_tag_on(
    tagging_id: uuid.UUID, request: Request, actor: TaggingTagger, db: DbSession
) -> TagApplied:
    """Give a directly set tag to the items below that it has not reached yet (what the
    preview lists as new). Draft versions only; "apply once" still holds, this is a
    new, explicit application."""
    target = target_of(request)
    ensure_editable(target.version)
    tagging, item = await _tagging_and_item(request, tagging_id, db)
    with audit_operation("tagging.pass_on", actor_id=actor.id, tag_value_id=tagging.tag_value_id):
        passed = await tagging_service.pass_on(db, tagging, item, created_by_id=actor.id)
    applied = await _tags_of(db, item)
    applied.inherited_count = len(passed)
    return applied


@router.delete("/taggings/{tagging_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tagging(
    tagging_id: uuid.UUID, request: Request, actor: TaggingTagger, db: DbSession
) -> Response:
    """Remove a tag that was set directly; what it passed on goes with it. An inherited
    tag is removed where it was set (422)."""
    target = target_of(request)
    ensure_editable(target.version)
    tagging = await db.get(Tagging, tagging_id)
    if tagging is None:  # pragma: no cover - the scope resolver found it
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found.")
    with audit_operation("tagging.remove", actor_id=actor.id, tag_value_id=tagging.tag_value_id):
        await tagging_service.remove_tagging(db, tagging)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
