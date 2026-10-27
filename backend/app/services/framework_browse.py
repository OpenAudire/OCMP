"""Reading frameworks: the library, the item tree, search and where items are mapped (ADR 038).

Trees can hold tens of thousands of items, so the tree is read one parent at a time in
windows of siblings, and search returns a page of matches with the path above each.

Mapping links are shown only when the user may see the objective they belong to, by the
same rules as the curriculum itself (ADR 027, ``curriculum_read``): a version the roles
show (drafts only with ``curriculum.view``), and within it the programme outcomes only to
people who see the whole version, a module's outcomes to people who see the module, a
session's objectives to people who see the session. Rejected links are not shown.
Everything else is left out silently, so counts never reveal hidden curriculum.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Programme,
)
from app.models.curriculum import ObjectiveLevel
from app.models.mapping import MappingStatus
from app.services.curriculum_read import CurriculumAccess, VisibleVersion, visible_version
from app.services.mapping_live import live_link

MAX_PAGE = 200
MAX_MAPPINGS = 200


def may_read_frameworks(access: CurriculumAccess) -> bool:
    """Whether the user holds ``curriculum.view`` or ``frameworks.manage`` at any scope.

    The same rule as the Frameworks entry in the navigation. Frameworks are shared by the
    whole institution, so there is no narrower scope to check.
    """
    held = set(access.instance)
    for permissions in access.scoped.values():
        held |= permissions
    return Permission.CURRICULUM_VIEW in held or Permission.FRAMEWORKS_MANAGE in held


# --- Library ------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryEntry:
    framework: Framework
    item_count: int
    top_level_count: int
    level_count: int


async def library(db: AsyncSession) -> list[LibraryEntry]:
    """Every live framework version with its item counts, by name then newest first."""
    frameworks = list(
        await db.scalars(
            select(Framework)
            .where(Framework.deleted_at.is_(None))
            .order_by(Framework.name, Framework.created_at.desc())
        )
    )
    counts = {
        framework_id: (total, top, deepest)
        for framework_id, total, top, deepest in await db.execute(
            select(
                FrameworkItem.framework_id,
                func.count(),
                func.count().filter(FrameworkItem.depth == 0),
                func.max(FrameworkItem.depth),
            )
            .where(FrameworkItem.framework_id.in_([f.id for f in frameworks]))
            .group_by(FrameworkItem.framework_id)
        )
    }
    entries = []
    for framework in frameworks:
        total, top, deepest = counts.get(framework.id, (0, 0, None))
        entries.append(LibraryEntry(framework, total, top, 0 if deepest is None else deepest + 1))
    return entries


async def live_framework(db: AsyncSession, framework_id: uuid.UUID) -> Framework | None:
    framework = await db.get(Framework, framework_id)
    return None if framework is None or framework.is_deleted else framework


# --- Tree ---------------------------------------------------------------------------


async def _child_counts(db: AsyncSession, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not item_ids:
        return {}
    rows = await db.execute(
        select(FrameworkItem.parent_id, func.count())
        .where(FrameworkItem.parent_id.in_(item_ids))
        .group_by(FrameworkItem.parent_id)
    )
    return {parent_id: count for parent_id, count in rows if parent_id is not None}


@dataclass(frozen=True)
class ChildrenWindow:
    offset: int
    total: int
    items: list[FrameworkItem]
    child_counts: dict[uuid.UUID, int]


async def children_window(
    db: AsyncSession,
    framework: Framework,
    parent_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> ChildrenWindow:
    """Up to ``limit`` children of ``parent_id`` (the top level when None) from ``offset``."""
    where = [
        FrameworkItem.framework_id == framework.id,
        FrameworkItem.parent_id.is_(None)
        if parent_id is None
        else FrameworkItem.parent_id == parent_id,
    ]
    total = await db.scalar(select(func.count()).select_from(FrameworkItem).where(*where)) or 0
    items = list(
        await db.scalars(
            select(FrameworkItem)
            .where(*where)
            .order_by(FrameworkItem.position, FrameworkItem.code)
            .offset(offset)
            .limit(limit)
        )
    )
    return ChildrenWindow(offset, total, items, await _child_counts(db, [i.id for i in items]))


async def item_in_framework(
    db: AsyncSession, framework: Framework, item_id: uuid.UUID
) -> FrameworkItem | None:
    item = await db.get(FrameworkItem, item_id)
    return item if item is not None and item.framework_id == framework.id else None


@dataclass(frozen=True)
class Ancestor:
    id: uuid.UUID
    code: str
    title: str


async def paths(db: AsyncSession, items: list[FrameworkItem]) -> dict[uuid.UUID, list[Ancestor]]:
    """For each item the items above it, top level first (a query per level of depth)."""
    known: dict[uuid.UUID, FrameworkItem] = {}
    wanted = {i.parent_id for i in items if i.parent_id is not None}
    while wanted:
        fetched = list(await db.scalars(select(FrameworkItem).where(FrameworkItem.id.in_(wanted))))
        known.update({i.id: i for i in fetched})
        wanted = {i.parent_id for i in fetched if i.parent_id is not None} - known.keys()
    result: dict[uuid.UUID, list[Ancestor]] = {}
    for item in items:
        chain: list[Ancestor] = []
        parent_id = item.parent_id
        while parent_id is not None:
            parent = known[parent_id]
            chain.append(Ancestor(parent.id, parent.code, parent.title))
            parent_id = parent.parent_id
        result[item.id] = chain[::-1]
    return result


async def sibling_index(db: AsyncSession, item: FrameworkItem) -> int:
    """Where the item stands among its siblings, from 0."""
    same_parent = (
        FrameworkItem.parent_id.is_(None)
        if item.parent_id is None
        else FrameworkItem.parent_id == item.parent_id
    )
    return (
        await db.scalar(
            select(func.count())
            .select_from(FrameworkItem)
            .where(
                FrameworkItem.framework_id == item.framework_id,
                same_parent,
                or_(
                    FrameworkItem.position < item.position,
                    (FrameworkItem.position == item.position) & (FrameworkItem.code < item.code),
                ),
            )
        )
        or 0
    )


async def child_count(db: AsyncSession, item: FrameworkItem) -> int:
    return (await _child_counts(db, [item.id])).get(item.id, 0)


# --- Search -------------------------------------------------------------------------


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class SearchResult:
    total: int
    items: list[FrameworkItem]


async def search_items(
    db: AsyncSession, framework: Framework, query: str, offset: int, limit: int
) -> SearchResult:
    """Items whose code or title contains the text (case does not matter).

    Codes that equal the text come first, then codes that start with it, then the rest
    in tree order.
    """
    pattern = _like(query)
    matches = or_(
        FrameworkItem.code.ilike(pattern, escape="\\"),
        FrameworkItem.title.ilike(pattern, escape="\\"),
    )
    where = [FrameworkItem.framework_id == framework.id, matches]
    total = await db.scalar(select(func.count()).select_from(FrameworkItem).where(*where)) or 0
    rank = case(
        (func.lower(FrameworkItem.code) == query.lower(), 0),
        (FrameworkItem.code.ilike(pattern.removeprefix("%"), escape="\\"), 1),
        else_=2,
    )
    items = list(
        await db.scalars(
            select(FrameworkItem)
            .where(*where)
            .order_by(rank, FrameworkItem.depth, FrameworkItem.position, FrameworkItem.code)
            .offset(offset)
            .limit(limit)
        )
    )
    return SearchResult(total, items)


# --- Where mapped -------------------------------------------------------------------


@dataclass(frozen=True)
class MappedRow:
    link: MappingLink
    objective: Objective
    programme: Programme
    version: CurriculumVersion
    module: Module | None
    event: LearningEvent | None


async def visible_mappings(
    db: AsyncSession, access: CurriculumAccess, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MappedRow]]:
    """The mapping links of these items that the user may see, by item.

    Rejected links, deleted objectives and anything in a deleted module, session, version
    or programme are left out, then whatever the user's roles do not show of a version.
    """
    result: dict[uuid.UUID, list[MappedRow]] = defaultdict(list)
    if not item_ids:
        return result
    rows = (
        await db.execute(
            select(MappingLink, Objective, CurriculumVersion, Programme)
            .join(Objective, Objective.id == MappingLink.objective_id)
            .join(CurriculumVersion, CurriculumVersion.id == Objective.version_id)
            .join(Programme, Programme.id == CurriculumVersion.programme_id)
            .where(
                MappingLink.framework_item_id.in_(item_ids),
                MappingLink.status != MappingStatus.REJECTED,
                live_link(),
                Objective.deleted_at.is_(None),
                CurriculumVersion.deleted_at.is_(None),
                Programme.deleted_at.is_(None),
            )
            .order_by(Programme.name, CurriculumVersion.academic_year.desc(), Objective.position)
        )
    ).all()
    if not rows:
        return result

    module_ids = {o.module_id for _, o, _, _ in rows if o.module_id is not None}
    event_ids = {o.learning_event_id for _, o, _, _ in rows if o.learning_event_id is not None}
    events = {
        e.id: e
        for e in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.id.in_(event_ids), LearningEvent.deleted_at.is_(None)
            )
        )
    }
    module_ids |= {e.module_id for e in events.values()}
    modules = {
        m.id: m
        for m in await db.scalars(
            select(Module).where(Module.id.in_(module_ids), Module.deleted_at.is_(None))
        )
    }
    views: dict[uuid.UUID, VisibleVersion | None] = {}
    for link, objective, version, programme in rows:
        if version.id not in views:
            views[version.id] = await visible_version(db, access, version.id)
        seen = views[version.id]
        if seen is None:
            continue
        module: Module | None = None
        event: LearningEvent | None = None
        if objective.level == ObjectiveLevel.PROGRAMME:
            if not seen.view.full:
                continue
        elif objective.level == ObjectiveLevel.MODULE:
            module = modules.get(objective.module_id) if objective.module_id else None
            if module is None or not seen.view.shows_module(module.id):
                continue
        else:
            event = events.get(objective.learning_event_id) if objective.learning_event_id else None
            module = modules.get(event.module_id) if event else None
            if event is None or module is None or not seen.view.shows_event(module.id, event.id):
                continue
        result[link.framework_item_id].append(
            MappedRow(link, objective, programme, version, module, event)
        )
    return result
