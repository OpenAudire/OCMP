"""Frameworks: the library, the item tree, search, where items are mapped (ADR 038) and
removing an unused framework version (ADR 037).

Reading needs ``curriculum.view`` or ``frameworks.manage`` at any scope (frameworks are shared
by the institution); the mappings shown are cut down to what the user may see of the
curriculum. Deleting needs ``frameworks.manage`` for the whole instance. Importing is in
``framework_packs``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, require_permission
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import Framework, FrameworkItem, User
from app.schemas.frameworks import (
    AncestorRead,
    DetailAncestor,
    FrameworkItemRead,
    FrameworkLibrary,
    FrameworkSummary,
    ItemDetail,
    ItemPage,
    MappedObjective,
    SearchHit,
    SearchPage,
    WhereMapped,
)
from app.services import framework_browse as browse
from app.services import frameworks as frameworks_service
from app.services.audit import audit_operation
from app.services.curriculum_read import CurriculumAccess, curriculum_access

router = APIRouter(prefix="/frameworks", tags=["frameworks"])

FrameworkManager = Annotated[User, Depends(require_permission(Permission.FRAMEWORKS_MANAGE))]


async def framework_reader(user: CurrentUser, db: DbSession) -> CurriculumAccess:
    """The user's access, when they may read frameworks at all (403 otherwise)."""
    access = await curriculum_access(db, user)
    if not browse.may_read_frameworks(access):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this.")
    return access


Reader = Annotated[CurriculumAccess, Depends(framework_reader)]


async def _framework_or_404(db: DbSession, framework_id: uuid.UUID) -> Framework:
    framework = await browse.live_framework(db, framework_id)
    if framework is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found.")
    return framework


async def _item_or_404(db: DbSession, framework: Framework, item_id: uuid.UUID) -> FrameworkItem:
    item = await browse.item_in_framework(db, framework, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    return item


def _ancestors(chain: list[browse.Ancestor]) -> list[AncestorRead]:
    return [AncestorRead(id=a.id, code=a.code, title=a.title) for a in chain]


@router.get("", response_model=FrameworkLibrary)
async def list_frameworks(access: Reader, db: DbSession) -> FrameworkLibrary:
    """Every framework version with its item counts, source and licence note."""
    entries = await browse.library(db)
    return FrameworkLibrary(
        frameworks=[
            FrameworkSummary(
                id=e.framework.id,
                key=e.framework.key,
                name=e.framework.name,
                version_label=e.framework.version_label,
                publisher=e.framework.publisher,
                licence_note=e.framework.licence_note,
                description=e.framework.description,
                url=e.framework.url,
                profile=e.framework.profile,
                status=e.framework.status,
                item_count=e.item_count,
                top_level_count=e.top_level_count,
                level_count=e.level_count,
            )
            for e in entries
        ],
        can_manage=Permission.FRAMEWORKS_MANAGE in access.instance,
    )


@router.get("/{framework_id}/items", response_model=ItemPage)
async def list_items(
    framework_id: uuid.UUID,
    access: Reader,
    db: DbSession,
    parent_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=browse.MAX_PAGE)] = 100,
) -> ItemPage:
    """A window of the children of one item (the top level without ``parent_id``)."""
    framework = await _framework_or_404(db, framework_id)
    if parent_id is not None:
        await _item_or_404(db, framework, parent_id)
    window = await browse.children_window(db, framework, parent_id, offset, limit)
    mapped = await browse.visible_mappings(db, access, [i.id for i in window.items])
    return ItemPage(
        parent_id=parent_id,
        offset=window.offset,
        total=window.total,
        items=[
            FrameworkItemRead(
                id=i.id,
                code=i.code,
                title=i.title,
                depth=i.depth,
                child_count=window.child_counts.get(i.id, 0),
                mapped_count=len(mapped.get(i.id, [])),
            )
            for i in window.items
        ],
    )


@router.get("/{framework_id}/search", response_model=SearchPage)
async def search_framework(
    framework_id: uuid.UUID,
    access: Reader,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SearchPage:
    """Items whose code or title contains the text, with the path above each."""
    framework = await _framework_or_404(db, framework_id)
    text = q.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter some text to search for.")
    found = await browse.search_items(db, framework, text, offset, limit)
    chains = await browse.paths(db, found.items)
    mapped = await browse.visible_mappings(db, access, [i.id for i in found.items])
    return SearchPage(
        query=text,
        offset=offset,
        total=found.total,
        hits=[
            SearchHit(
                id=i.id,
                code=i.code,
                title=i.title,
                depth=i.depth,
                path=_ancestors(chains[i.id]),
                mapped_count=len(mapped.get(i.id, [])),
            )
            for i in found.items
        ],
    )


@router.get("/{framework_id}/items/{item_id}", response_model=ItemDetail)
async def get_item(
    framework_id: uuid.UUID, item_id: uuid.UUID, access: Reader, db: DbSession
) -> ItemDetail:
    """One item with the path above it and where it stands among its siblings."""
    framework = await _framework_or_404(db, framework_id)
    item = await _item_or_404(db, framework, item_id)
    chain = (await browse.paths(db, [item]))[item.id]
    above = []
    for ancestor in chain:
        parent = await browse.item_in_framework(db, framework, ancestor.id)
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
        above.append(
            DetailAncestor(
                id=ancestor.id,
                code=ancestor.code,
                title=ancestor.title,
                sibling_index=await browse.sibling_index(db, parent),
            )
        )
    mapped = await browse.visible_mappings(db, access, [item.id])
    return ItemDetail(
        id=item.id,
        framework_id=framework.id,
        code=item.code,
        title=item.title,
        description=item.description,
        depth=item.depth,
        child_count=await browse.child_count(db, item),
        mapped_count=len(mapped.get(item.id, [])),
        path=above,
        sibling_index=await browse.sibling_index(db, item),
    )


@router.get("/{framework_id}/items/{item_id}/mappings", response_model=WhereMapped)
async def where_mapped(
    framework_id: uuid.UUID, item_id: uuid.UUID, access: Reader, db: DbSession
) -> WhereMapped:
    """The objectives linked to the item that the user may see (read only)."""
    framework = await _framework_or_404(db, framework_id)
    item = await _item_or_404(db, framework, item_id)
    rows = (await browse.visible_mappings(db, access, [item.id])).get(item.id, [])
    return WhereMapped(
        item_id=item.id,
        total=len(rows),
        limit=browse.MAX_MAPPINGS,
        mappings=[
            MappedObjective(
                link_id=r.link.id,
                status=r.link.status,
                source=r.link.source,
                coverage=r.link.coverage,
                depth_match=r.link.depth_match,
                needs_recheck=r.link.needs_recheck,
                needs_discussion=r.link.needs_discussion,
                objective_id=r.objective.id,
                objective_text=r.objective.text,
                level=r.objective.level,
                programme_id=r.programme.id,
                programme_name=r.programme.name,
                version_id=r.version.id,
                academic_year=r.version.academic_year,
                version_status=r.version.status,
                module_id=r.module.id if r.module else None,
                module_code=r.module.code if r.module else None,
                module_name=r.module.name if r.module else None,
                learning_event_id=r.event.id if r.event else None,
                learning_event_title=r.event.title if r.event else None,
            )
            for r in rows[: browse.MAX_MAPPINGS]
        ],
    )


@router.delete("/{framework_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_framework(
    framework_id: uuid.UUID, actor: FrameworkManager, db: DbSession
) -> Response:
    """Delete a framework version that no objective is mapped to (409 otherwise). The
    framework is hidden, not erased, and the audit log keeps the entry."""
    framework = await db.get(Framework, framework_id)
    if framework is None or framework.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found.")
    with audit_operation("framework.delete", actor_id=actor.id):
        await frameworks_service.delete_framework(db, framework)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
