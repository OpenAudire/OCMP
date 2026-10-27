"""Reading the mapping workspace: the objectives of one version with their links (ADR 039).

What is listed follows ADR 027 (what the user may see of the version); rejected links are
left out (they are not mappings, ADR 038). ``can_edit`` and ``can_review`` are the
user's ``mapping.edit`` and ``mapping.review`` at each objective's own scope, so the screen
shows buttons only where the API will accept them.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, ScopeType
from app.models import (
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Phase,
)
from app.models.curriculum import ObjectiveLevel
from app.models.mapping import MappingStatus
from app.schemas.mapping import MappingWorkspace, WorkspaceLink, WorkspaceObjective
from app.services.curriculum_edit import is_editable
from app.services.curriculum_read import Permissions, VisibleVersion
from app.services.policies import mapping_policy_for_version

_LEVEL_ORDER = {
    ObjectiveLevel.PROGRAMME: 0,
    ObjectiveLevel.MODULE: 1,
    ObjectiveLevel.LEARNING_EVENT: 2,
}


async def link_read(db: AsyncSession, link: MappingLink) -> WorkspaceLink:
    """One link with the framework item and framework it points at."""
    item = await db.get(FrameworkItem, link.framework_item_id)
    assert item is not None
    framework = await db.get(Framework, item.framework_id)
    assert framework is not None
    return _link(link, item, framework)


def _link(link: MappingLink, item: FrameworkItem, framework: Framework) -> WorkspaceLink:
    return WorkspaceLink(
        id=link.id,
        framework_id=framework.id,
        framework_name=framework.name,
        framework_version_label=framework.version_label,
        item_id=item.id,
        item_code=item.code,
        item_title=item.title,
        coverage=link.coverage,
        depth_match=link.depth_match,
        rationale=link.rationale,
        source=link.source,
        status=link.status,
        accept_method=link.accept_method,
        needs_recheck=link.needs_recheck,
        needs_discussion=link.needs_discussion,
    )


async def mapping_workspace(db: AsyncSession, visible: VisibleVersion) -> MappingWorkspace:
    """The objectives of the version the user may see, each with its links and permissions."""
    version = visible.version
    view = visible.view
    objectives = list(
        await db.scalars(
            select(Objective).where(
                Objective.version_id == version.id, Objective.deleted_at.is_(None)
            )
        )
    )
    event_ids = {o.learning_event_id for o in objectives if o.learning_event_id}
    events = {
        e.id: e
        for e in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.id.in_(event_ids), LearningEvent.deleted_at.is_(None)
            )
        )
    }
    module_ids = {o.module_id for o in objectives if o.module_id} | {
        e.module_id for e in events.values()
    }
    modules = {
        m.id: m
        for m in await db.scalars(
            select(Module).where(Module.id.in_(module_ids), Module.deleted_at.is_(None))
        )
    }
    phases = {
        p.id: p
        for p in await db.scalars(
            select(Phase).where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
        )
    }

    shown: list[tuple[Objective, Module | None, LearningEvent | None]] = []
    for objective in objectives:
        module: Module | None = None
        event: LearningEvent | None = None
        if objective.level == ObjectiveLevel.PROGRAMME:
            if not view.full:
                continue
        elif objective.level == ObjectiveLevel.MODULE:
            module = modules.get(objective.module_id) if objective.module_id else None
            if module is None or not view.shows_module(module.id):
                continue
        else:
            event = events.get(objective.learning_event_id) if objective.learning_event_id else None
            module = modules.get(event.module_id) if event else None
            if event is None or module is None or not view.shows_event(module.id, event.id):
                continue
        shown.append((objective, module, event))

    links: dict[uuid.UUID, list[WorkspaceLink]] = defaultdict(list)
    if shown:
        rows = await db.execute(
            select(MappingLink, FrameworkItem, Framework)
            .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
            .join(Framework, Framework.id == FrameworkItem.framework_id)
            .where(
                MappingLink.objective_id.in_([o.id for o, _, _ in shown]),
                MappingLink.status != MappingStatus.REJECTED,
                Framework.deleted_at.is_(None),
            )
            .order_by(Framework.name, FrameworkItem.code)
        )
        for link, item, framework in rows:
            links[link.objective_id].append(_link(link, item, framework))

    base: Permissions = visible.access.for_programme(visible.programme)

    def held(module: Module | None, event: LearningEvent | None) -> Permissions:
        extra = base
        if module is not None:
            extra = extra | visible.access.at(ScopeType.MODULE, module.id)
        if event is not None:
            extra = extra | visible.access.at(ScopeType.LEARNING_EVENT, event.id)
        return extra

    shown.sort(
        key=lambda row: (
            _LEVEL_ORDER[row[0].level],
            row[1].code if row[1] else "",
            row[2].position if row[2] else 0,
            row[0].position,
            row[0].created_at,
        )
    )
    result = []
    for objective, module, event in shown:
        permissions = held(module, event)
        phase = phases.get(module.phase_id) if module and module.phase_id else None
        result.append(
            WorkspaceObjective(
                id=objective.id,
                text=objective.text,
                level=objective.level,
                phase_id=phase.id if phase else None,
                phase_name=phase.name if phase else None,
                module_id=module.id if module else None,
                module_code=module.code if module else None,
                module_name=module.name if module else None,
                learning_event_id=event.id if event else None,
                learning_event_title=event.title if event else None,
                can_edit=Permission.MAPPING_EDIT in permissions,
                can_review=Permission.MAPPING_REVIEW in permissions,
                links=links.get(objective.id, []),
            )
        )
    policy = await mapping_policy_for_version(db, version.id)
    return MappingWorkspace(
        version_id=version.id,
        academic_year=version.academic_year,
        version_status=version.status,
        programme_id=visible.programme.id,
        programme_name=visible.programme.name,
        editable=is_editable(version),
        four_eyes=policy.four_eyes,
        objectives=result,
    )
