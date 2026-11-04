"""The coverage report and the gap report of one version against one framework (Slice 1.21,
ADR 050): reads the accepted links and hands them to the coverage engine.

What is counted:

* only links with status ``accepted``, live (``live_link()``, ADR 043), with a coverage of at
  least 1, whose objective is live, not retired, and shown to the user by their roles (ADR 027);
* links waiting for a decision (suggested, needing a second review) are counted apart, per item,
  so a gap can say "two suggestions are waiting";
* links accepted in bulk and links that need a re-check are counted and flagged on every item.

Every figure is labelled with its method, the settings behind it, the version, the framework and
the time it was made (brief: "every report states its method and date").
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    Phase,
)
from app.models.curriculum import ObjectiveLevel
from app.models.mapping import AcceptMethod, MappingStatus
from app.services.coverage_engine import (
    DEFINITIONS,
    Item,
    ItemResult,
    Link,
    Method,
    Params,
    Status,
    Summary,
    Tree,
    compute,
    heatmap,
    summarise,
)
from app.services.curriculum_read import VisibleVersion
from app.services.mapping_live import live_link
from app.services.policies import CoveragePolicy
from app.services.search import visible_objective_ids

MAX_UNMAPPED = 200

PROGRAMME = "programme"
NO_PHASE = "none"


def params_of(policy: CoveragePolicy) -> Params:
    return Params(
        multiple_n=policy.multiple_match_n,
        subordinate_min_share=policy.subordinate_min_percent / 100,
        below_depth_factor=policy.below_depth_percent / 100,
        weighted_low=policy.weighted_low_percent / 100,
    )


def definition(method: Method, policy: CoveragePolicy) -> str:
    """The method's wording with the institution's numbers in it."""
    return DEFINITIONS[method].format(
        n=policy.multiple_match_n,
        share=policy.subordinate_min_percent,
        factor=policy.below_depth_percent,
        low=policy.weighted_low_percent,
    )


@dataclass(frozen=True)
class Column:
    key: str
    # "phase", "programme" (programme outcomes) or "none" (modules without a phase).
    kind: str
    label: str


@dataclass
class Report:
    version: CurriculumVersion
    framework: Framework
    method: Method
    definition: str
    params: Params
    policy: CoveragePolicy
    generated_at: datetime
    # The user sees only part of the version: the figures cover only that part.
    partial: bool
    tree: Tree
    rows: list[ItemResult]
    summary: Summary
    columns: list[Column]
    grid: dict[uuid.UUID, dict[str, float]]
    objectives_in_scope: int
    links: list[Link] = field(default_factory=list)


@dataclass
class UnmappedObjective:
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    module_id: uuid.UUID | None
    module_code: str | None
    event_id: uuid.UUID | None
    event_title: str | None
    # Suggestions or reviews are waiting, but nothing is accepted.
    waiting: int


@dataclass
class Gap:
    result: ItemResult
    # The groups above the item, outermost first.
    path: list[Item]
    reason: str


@dataclass
class GapReport:
    report: Report
    gaps: list[Gap]
    unlinked: list[UnmappedObjective]
    only_waiting: list[UnmappedObjective]
    unlinked_total: int
    only_waiting_total: int


async def _framework_tree(db: AsyncSession, framework: Framework) -> Tree:
    rows = await db.execute(
        select(
            FrameworkItem.id,
            FrameworkItem.code,
            FrameworkItem.title,
            FrameworkItem.parent_id,
            FrameworkItem.depth,
            FrameworkItem.position,
        ).where(FrameworkItem.framework_id == framework.id)
    )
    return Tree.of(Item(*row) for row in rows)


async def _columns(
    db: AsyncSession, version_id: uuid.UUID
) -> tuple[list[Column], dict[uuid.UUID, str], dict[uuid.UUID, uuid.UUID]]:
    """The heatmap's columns (phases in order), the column of each module and the module of each
    session."""
    phases = list(
        await db.scalars(
            select(Phase)
            .where(Phase.version_id == version_id, Phase.deleted_at.is_(None))
            .order_by(Phase.position)
        )
    )
    phase_ids = {p.id for p in phases}
    module_column: dict[uuid.UUID, str] = {}
    for module_id, phase_id in await db.execute(
        select(Module.id, Module.phase_id).where(
            Module.version_id == version_id, Module.deleted_at.is_(None)
        )
    ):
        module_column[module_id] = str(phase_id) if phase_id in phase_ids else NO_PHASE
    event_module = dict(
        (
            await db.execute(
                select(LearningEvent.id, LearningEvent.module_id)
                .join(Module, Module.id == LearningEvent.module_id)
                .where(Module.version_id == version_id, LearningEvent.deleted_at.is_(None))
            )
        ).all()
    )
    columns = [Column(key=str(p.id), kind="phase", label=p.name) for p in phases]
    return columns, module_column, event_module


async def build_report(
    db: AsyncSession,
    visible: VisibleVersion,
    framework: Framework,
    method: Method,
    policy: CoveragePolicy,
) -> Report:
    """The coverage of ``framework`` by the accepted links of the objectives the user sees."""
    params = params_of(policy)
    tree = await _framework_tree(db, framework)
    allowed = await visible_objective_ids(db, visible)
    columns, module_column, event_module = await _columns(db, visible.version.id)

    rows = await db.execute(
        select(MappingLink, Objective)
        .join(Objective, Objective.id == MappingLink.objective_id)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .where(
            FrameworkItem.framework_id == framework.id,
            MappingLink.status != MappingStatus.REJECTED,
            Objective.id.in_(allowed),
            live_link(),
        )
    )
    links: list[Link] = []
    waiting: dict[uuid.UUID, int] = defaultdict(int)
    used_columns: set[str] = set()
    for link, objective in rows:
        if link.status is not MappingStatus.ACCEPTED:
            waiting[link.framework_item_id] += 1
            continue
        if not link.coverage or link.coverage < 1:
            continue
        if objective.level is ObjectiveLevel.PROGRAMME:
            column = PROGRAMME
        elif objective.level is ObjectiveLevel.MODULE:
            column = (
                module_column.get(objective.module_id, NO_PHASE)
                if objective.module_id
                else NO_PHASE
            )
        else:
            module_id = (
                event_module.get(objective.learning_event_id)
                if objective.learning_event_id
                else None
            )
            column = module_column.get(module_id, NO_PHASE) if module_id else NO_PHASE
        used_columns.add(column)
        links.append(
            Link(
                item_id=link.framework_item_id,
                objective_id=objective.id,
                coverage=link.coverage,
                depth=link.depth_match.value if link.depth_match else None,
                bulk=link.accept_method is AcceptMethod.BULK,
                needs_recheck=link.needs_recheck,
                column=column,
            )
        )
    # Columns that hold objectives even without links: programme outcomes and modules without
    # a phase, so a reader sees where the curriculum has no place in the grid.
    in_scope = await db.execute(
        select(Objective.level, func.count())
        .where(Objective.id.in_(allowed))
        .group_by(Objective.level)
    )
    counts = dict(in_scope.all())
    if counts.get(ObjectiveLevel.PROGRAMME) or PROGRAMME in used_columns:
        columns.append(Column(key=PROGRAMME, kind="programme", label=""))
    if NO_PHASE in used_columns or any(c == NO_PHASE for c in module_column.values()):
        columns.append(Column(key=NO_PHASE, kind="none", label=""))
    results = compute(tree, links, method, params, waiting)
    total_waiting = sum(waiting.values())
    return Report(
        version=visible.version,
        framework=framework,
        method=method,
        definition=definition(method, policy),
        params=params,
        policy=policy,
        generated_at=datetime.now(UTC),
        partial=not visible.view.full,
        tree=tree,
        rows=results,
        summary=summarise(tree, links, params, total_waiting),
        columns=columns,
        grid=heatmap(tree, links, method, [c.key for c in columns], params),
        objectives_in_scope=sum(counts.values()),
        links=links,
    )


def _reason(result: ItemResult, method: Method, params: Params) -> str:
    if result.status is Status.NONE:
        if method is Method.SUBORDINATE and not result.is_leaf:
            return "none of the items below it is covered"
        return "no accepted link"
    if method is Method.MULTIPLE:
        return f"{result.links} of {params.multiple_n} accepted links"
    if method is Method.SUBORDINATE:
        return f"{result.leaves_covered} of {result.leaves} items below it covered"
    return f"{round(result.value * 100)}% of the coverage wanted"


async def build_gaps(
    db: AsyncSession,
    visible: VisibleVersion,
    framework: Framework,
    method: Method,
    policy: CoveragePolicy,
) -> GapReport:
    """Framework items with no or low coverage, and objectives with no accepted mapping."""
    report = await build_report(db, visible, framework, method, policy)
    gaps: list[Gap] = []
    for result in report.rows:
        if result.status is Status.COVERED or not result.is_leaf:
            continue
        path: list[Item] = []
        parent = result.item.parent_id
        while parent is not None and parent in report.tree.by_id:
            path.append(report.tree.by_id[parent])
            parent = report.tree.by_id[parent].parent_id
        gaps.append(Gap(result, list(reversed(path)), _reason(result, method, report.params)))
    # Items with nothing at all first, then the partial ones; each in tree order.
    gaps.sort(key=lambda g: g.result.status is not Status.NONE)

    allowed = await visible_objective_ids(db, visible)
    accepted = (
        select(MappingLink.objective_id)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .where(
            FrameworkItem.framework_id == framework.id,
            MappingLink.status == MappingStatus.ACCEPTED,
            live_link(),
        )
    )
    pending = (
        select(MappingLink.objective_id, func.count())
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .where(
            FrameworkItem.framework_id == framework.id,
            MappingLink.status.in_([MappingStatus.SUGGESTED, MappingStatus.NEEDS_SECOND_REVIEW]),
            live_link(),
        )
        .group_by(MappingLink.objective_id)
    )
    pending_count = dict((await db.execute(pending)).all())
    module_code = dict(
        (
            await db.execute(
                select(Module.id, Module.code).where(Module.version_id == visible.version.id)
            )
        ).all()
    )
    sessions = {
        event_id: (module_id, title)
        for event_id, module_id, title in await db.execute(
            select(LearningEvent.id, LearningEvent.module_id, LearningEvent.title)
            .join(Module, Module.id == LearningEvent.module_id)
            .where(Module.version_id == visible.version.id)
        )
    }
    objectives = await db.scalars(
        select(Objective)
        .where(Objective.id.in_(allowed), Objective.id.not_in(accepted))
        .order_by(Objective.level, Objective.position, Objective.created_at)
    )
    unlinked: list[UnmappedObjective] = []
    only_waiting: list[UnmappedObjective] = []
    for objective in objectives:
        session = sessions.get(objective.learning_event_id) if objective.learning_event_id else None
        module_id = session[0] if session else objective.module_id
        entry = UnmappedObjective(
            id=objective.id,
            text=objective.text,
            level=objective.level,
            module_id=module_id,
            module_code=module_code.get(module_id) if module_id else None,
            event_id=objective.learning_event_id,
            event_title=session[1] if session else None,
            waiting=pending_count.get(objective.id, 0),
        )
        (only_waiting if entry.waiting else unlinked).append(entry)
    return GapReport(
        report=report,
        gaps=gaps,
        unlinked=unlinked[:MAX_UNMAPPED],
        only_waiting=only_waiting[:MAX_UNMAPPED],
        unlinked_total=len(unlinked),
        only_waiting_total=len(only_waiting),
    )
