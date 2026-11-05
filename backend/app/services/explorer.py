"""The curriculum explorer for students and staff (Slice 1.29, ADR 059): published versions only.

Two reads: one module with its outcomes, its sessions by week with their objectives and its
assessments with what each item assesses, and one teaching week across the modules. They show only
what the person's roles show of the version (ADR 027), only live, non-retired objectives, and
**never framework mappings**: the explorer answers "what is taught and assessed" in the
curriculum's own words.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearningEvent, Module, Objective, TagValue
from app.models.curriculum import ObjectiveLevel, ObjectiveStatus, VersionStatus
from app.models.tagging import TaggableType
from app.services import assessments as assessment_service
from app.services.curriculum_read import CurriculumAccess, VisibleVersion, visible_version
from app.services.tagging import item_tags


@dataclass
class ExplorerObjective:
    id: uuid.UUID
    text: str


@dataclass
class ExplorerTag:
    list_name: str
    label: str


@dataclass
class ExplorerSession:
    id: uuid.UUID
    title: str
    week: int | None
    format: str | None
    contact_minutes: int
    self_study_minutes: int
    description: str
    objectives: list[ExplorerObjective]
    module_id: uuid.UUID
    module_code: str
    module_name: str


@dataclass
class ExplorerItem:
    id: uuid.UUID
    label: str
    marks: int | None
    objectives: list[ExplorerObjective]


@dataclass
class ExplorerAssessment:
    id: uuid.UUID
    name: str
    method: str | None
    weight: float | None
    timing: str
    time_minutes: int
    items: list[ExplorerItem]
    # Every objective the assessment's items assess, once each, in curriculum order.
    covered: list[ExplorerObjective] = field(default_factory=list)


@dataclass
class ExplorerModule:
    module: Module
    version: VisibleVersion
    outcomes: list[ExplorerObjective]
    sessions: list[ExplorerSession]
    assessments: list[ExplorerAssessment]
    tags: list[ExplorerTag]
    contact_minutes: int
    self_study_minutes: int


@dataclass
class ExplorerWeek:
    version: VisibleVersion
    week: int
    # The weeks that have sessions, in order (the stepper's range).
    weeks: list[int]
    sessions: list[ExplorerSession]


def _shown(objective: Objective) -> bool:
    return objective.status is not ObjectiveStatus.RETIRED


async def _objectives_of(
    db: AsyncSession, level: ObjectiveLevel, owner_column: object, owner_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ExplorerObjective]]:
    out: dict[uuid.UUID, list[ExplorerObjective]] = defaultdict(list)
    if not owner_ids:
        return out
    rows = await db.scalars(
        select(Objective)
        .where(
            Objective.deleted_at.is_(None),
            Objective.level == level,
            owner_column.in_(owner_ids),  # type: ignore[attr-defined]
        )
        .order_by(Objective.position, Objective.created_at)
    )
    for objective in rows:
        if _shown(objective):
            owner = (
                objective.module_id
                if level is ObjectiveLevel.MODULE
                else objective.learning_event_id
            )
            assert owner is not None
            out[owner].append(ExplorerObjective(objective.id, objective.text))
    return out


async def _sessions(
    db: AsyncSession, visible: VisibleVersion, modules: list[Module], week: int | None = None
) -> list[ExplorerSession]:
    """The live sessions of these modules the person sees, with their objectives, in teaching
    order (week, then position; sessions without a week last). ``week`` keeps one week."""
    by_id = {m.id: m for m in modules}
    query = (
        select(LearningEvent, TagValue.label)
        .outerjoin(
            TagValue, (TagValue.id == LearningEvent.format_value_id) & TagValue.deleted_at.is_(None)
        )
        .where(LearningEvent.module_id.in_(list(by_id)), LearningEvent.deleted_at.is_(None))
    )
    if week is not None:
        query = query.where(LearningEvent.week == week)
    rows = [
        (event, label)
        for event, label in await db.execute(query)
        if visible.view.shows_event(event.module_id, event.id)
    ]
    objectives = await _objectives_of(
        db,
        ObjectiveLevel.LEARNING_EVENT,
        Objective.learning_event_id,
        [event.id for event, _ in rows],
    )
    order = {m.id: index for index, m in enumerate(modules)}
    rows.sort(
        key=lambda r: (
            r[0].week is None,
            r[0].week or 0,
            order[r[0].module_id],
            r[0].position,
            r[0].title,
        )
    )
    return [
        ExplorerSession(
            id=event.id,
            title=event.title,
            week=event.week,
            format=label,
            contact_minutes=event.contact_minutes,
            self_study_minutes=event.self_study_minutes,
            description=event.description,
            objectives=objectives.get(event.id, []),
            module_id=event.module_id,
            module_code=by_id[event.module_id].code,
            module_name=by_id[event.module_id].name,
        )
        for event, label in rows
    ]


async def module_view(
    db: AsyncSession, access: CurriculumAccess, module_id: uuid.UUID
) -> ExplorerModule | None:
    """One module of a published version, if the person sees the module itself."""
    module = await db.scalar(
        select(Module).where(Module.id == module_id, Module.deleted_at.is_(None))
    )
    if module is None:
        return None
    visible = await visible_version(db, access, module.version_id)
    if (
        visible is None
        or visible.version.status is not VersionStatus.PUBLISHED
        or not visible.view.shows_module(module.id)
    ):
        return None
    outcomes = (await _objectives_of(db, ObjectiveLevel.MODULE, Objective.module_id, [module.id]))[
        module.id
    ]
    sessions = await _sessions(db, visible, [module])

    known: dict[uuid.UUID, ExplorerObjective] = {o.id: o for o in outcomes}
    for session in sessions:
        known.update({o.id: o for o in session.objectives})
    order = {oid: index for index, oid in enumerate(known)}
    assessments: list[ExplorerAssessment] = []
    for found in await assessment_service.module_assessments(db, module.id):
        items = [
            ExplorerItem(
                i.item.id,
                i.item.label,
                int(i.item.marks) if i.item.marks is not None else None,
                [known[o] for o in i.objective_ids if o in known],
            )
            for i in found.items
        ]
        covered = {o.id: o for item in items for o in item.objectives}
        assessments.append(
            ExplorerAssessment(
                id=found.assessment.id,
                name=found.assessment.name,
                method=found.method_label,
                weight=float(found.assessment.weight)
                if found.assessment.weight is not None
                else None,
                timing=found.assessment.timing,
                time_minutes=found.assessment.time_minutes,
                items=items,
                covered=sorted(covered.values(), key=lambda o: order[o.id]),
            )
        )
    tags = (await item_tags(db, {TaggableType.MODULE: [module.id]}, with_reach=False)).get(
        (TaggableType.MODULE, module.id), []
    )
    contact = await db.scalar(
        select(func.coalesce(func.sum(LearningEvent.contact_minutes), 0)).where(
            LearningEvent.module_id == module.id, LearningEvent.deleted_at.is_(None)
        )
    )
    study = await db.scalar(
        select(func.coalesce(func.sum(LearningEvent.self_study_minutes), 0)).where(
            LearningEvent.module_id == module.id, LearningEvent.deleted_at.is_(None)
        )
    )
    return ExplorerModule(
        module=module,
        version=visible,
        outcomes=outcomes,
        sessions=sessions,
        assessments=assessments,
        tags=[ExplorerTag(t.tag_list.name, t.value.label) for t in tags],
        contact_minutes=int(contact or 0),
        self_study_minutes=int(study or 0),
    )


async def week_view(
    db: AsyncSession, access: CurriculumAccess, version_id: uuid.UUID, week: int
) -> ExplorerWeek | None:
    """The sessions of one teaching week across the modules the person sees, in a published
    version."""
    visible = await visible_version(db, access, version_id)
    if visible is None or visible.version.status is not VersionStatus.PUBLISHED:
        return None
    modules = [
        m
        for m in await db.scalars(
            select(Module)
            .where(Module.version_id == version_id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
        if visible.view.full or visible.view.shows_module(m.id) or m.id in visible.view.events
    ]
    if not modules:
        return ExplorerWeek(visible, week, [], [])
    weeks = sorted(
        {
            w
            for module_id, event_id, w in await db.execute(
                select(LearningEvent.module_id, LearningEvent.id, LearningEvent.week).where(
                    LearningEvent.module_id.in_([m.id for m in modules]),
                    LearningEvent.deleted_at.is_(None),
                    LearningEvent.week.is_not(None),
                )
            )
            if w is not None and visible.view.shows_event(module_id, event_id)
        }
    )
    return ExplorerWeek(visible, week, weeks, await _sessions(db, visible, modules, week))
