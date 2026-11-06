"""Where a published year builds each competency, for students (Slice 1.31, ADR 061).

An institution switch (``settings["explorer"]``, off by default) lets the explorer show, for each
**competency group** of a framework, the modules and sessions of a published version whose
objectives are linked to the group's items. The answer is deliberately thin:

* published versions only, and only what the person's roles show (ADR 027);
* **accepted links only**, with a coverage of at least 1 (waiting, rejected and re-check links are
  not shown); links made by a bulk accept or an import are accepted links and count;
* **competency-group level only**: a group is a top-level framework item that has items below it. A
  link to an item below counts for its group; a link made to the group itself is ignored (the same
  rule as the coverage reports, ADR 050). Item codes and titles below the group are never returned;
* **no scores**: no coverage, depth, confidence, counts of links or percentages, and no reviewer,
  method or status words.

Programme outcomes belong to no module, so they place nothing here.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FrameworkItem, LearningEvent, MappingLink, Module, Objective
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.mapping import MappingStatus
from app.services.curriculum_read import CurriculumAccess, VisibleVersion, visible_version
from app.services.dashboard_metrics import frameworks_in_use
from app.services.mapping_live import live_link
from app.services.policies import explorer_policy_for_version
from app.services.search import visible_objective_ids


@dataclass
class BuiltInSession:
    id: uuid.UUID
    title: str
    week: int | None


@dataclass
class BuiltInModule:
    id: uuid.UUID
    code: str
    name: str
    # Sessions with an objective linked to the group, in teaching order.
    sessions: list[BuiltInSession] = field(default_factory=list)


@dataclass
class CompetencyGroup:
    id: uuid.UUID
    code: str
    title: str
    modules: list[BuiltInModule]


@dataclass
class FrameworkGroups:
    name: str
    version_label: str
    groups: list[CompetencyGroup]


@dataclass
class CompetencyView:
    version: VisibleVersion
    frameworks: list[FrameworkGroups]


async def competency_view(
    db: AsyncSession, access: CurriculumAccess, version_id: uuid.UUID
) -> CompetencyView | None:
    """The groups of each framework in use and where the version builds them, or None when the
    version is not a published one the person sees, or the institution has the view switched off."""
    visible = await visible_version(db, access, version_id)
    if visible is None or visible.version.status is not VersionStatus.PUBLISHED:
        return None
    if not (await explorer_policy_for_version(db, version_id)).show_competency_view:
        return None

    modules = {
        m.id: m
        for m in await db.scalars(
            select(Module)
            .where(Module.version_id == version_id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    }
    module_order = {module_id: index for index, module_id in enumerate(modules)}
    sessions = {
        e.id: e
        for e in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.module_id.in_(list(modules)), LearningEvent.deleted_at.is_(None)
            )
        )
    }
    allowed = await visible_objective_ids(db, visible)

    out: list[FrameworkGroups] = []
    for framework in await frameworks_in_use(db, version_id, visible):
        items = list(
            await db.execute(
                select(FrameworkItem.id, FrameworkItem.parent_id, FrameworkItem.code).where(
                    FrameworkItem.framework_id == framework.id
                )
            )
        )
        parent = {item_id: parent_id for item_id, parent_id, _ in items}
        known = set(parent)
        has_children = {p for p in parent.values() if p in known}

        def top(
            item_id: uuid.UUID, parent: dict[uuid.UUID, uuid.UUID | None] = parent
        ) -> uuid.UUID:
            seen = {item_id}
            while parent.get(item_id) in parent and parent[item_id] not in seen:
                item_id = parent[item_id]  # type: ignore[assignment]
                seen.add(item_id)
            return item_id

        group_ids = {i for i in known if parent[i] not in known and i in has_children}

        rows = await db.execute(
            select(MappingLink.framework_item_id, Objective)
            .join(Objective, Objective.id == MappingLink.objective_id)
            .where(
                MappingLink.framework_item_id.in_(known),
                MappingLink.status == MappingStatus.ACCEPTED,
                MappingLink.coverage >= 1,
                MappingLink.needs_recheck.is_(False),
                Objective.id.in_(allowed),
                live_link(),
            )
        )
        # group -> module -> sessions
        placed: dict[uuid.UUID, dict[uuid.UUID, set[uuid.UUID]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for item_id, objective in rows:
            group = top(item_id)
            if group == item_id or group not in group_ids:
                continue  # a link made to the group itself, or an item with nothing above
            if objective.level is ObjectiveLevel.MODULE and objective.module_id in modules:
                placed[group][objective.module_id]
            elif (
                objective.level is ObjectiveLevel.LEARNING_EVENT
                and objective.learning_event_id in sessions
            ):
                event = sessions[objective.learning_event_id]
                placed[group][event.module_id].add(event.id)

        groups: list[CompetencyGroup] = []
        titles = {
            item_id: (code, title)
            for item_id, code, title in await db.execute(
                select(FrameworkItem.id, FrameworkItem.code, FrameworkItem.title).where(
                    FrameworkItem.id.in_(group_ids)
                )
            )
        }
        for group_id in sorted(group_ids, key=lambda g: (titles[g][0], titles[g][1])):  # code order
            built = []
            for module_id in sorted(placed[group_id], key=lambda m: module_order[m]):
                module = modules[module_id]
                built.append(
                    BuiltInModule(
                        id=module.id,
                        code=module.code,
                        name=module.name,
                        sessions=[
                            BuiltInSession(e.id, e.title, e.week)
                            for e in sorted(
                                (sessions[s] for s in placed[group_id][module_id]),
                                key=lambda e: (e.week is None, e.week or 0, e.position, e.title),
                            )
                        ],
                    )
                )
            groups.append(CompetencyGroup(group_id, *titles[group_id], built))
        if any(g.modules for g in groups):
            out.append(FrameworkGroups(framework.name, framework.version_label, groups))
    return CompetencyView(visible, out)
