"""The committee dashboard (Slice 1.28, ADR 058): key indicators with trends, mapping progress by
module, coverage against the last published version, the credits table and the traceability from one
programme outcome to the framework.

Everything is worked out for what the person is allowed to see (ADR 027). Trends come from the daily
snapshots of the whole version, so a person who sees only part of a version gets today's figures for
that part and no trend lines.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    ObjectiveLink,
)
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.mapping import MappingStatus
from app.services import coverage_report, credit_check, dashboard_metrics
from app.services.coverage_engine import Method
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.mapping_live import live_link
from app.services.policies import CoveragePolicy
from app.services.search import visible_objective_ids

MAX_TRACE_ITEMS = 12


@dataclass
class Point:
    date: date
    value: float


@dataclass
class Kpi:
    key: str
    # "percent" (value 0 to 1) or "count".
    unit: str
    value: float | None
    # Words for the reader, with these numbers.
    numerator: int | None = None
    denominator: int | None = None
    series: list[Point] = field(default_factory=list)


@dataclass
class ProgressRow:
    module_id: uuid.UUID
    code: str
    name: str
    objectives: int
    mapped: int
    waiting: int


@dataclass
class GroupCompare:
    id: uuid.UUID
    code: str
    title: str
    now: float
    before: float | None


@dataclass
class Comparison:
    version_id: uuid.UUID
    academic_year: int
    status: VersionStatus
    groups: list[GroupCompare]


@dataclass
class CreditRow:
    module_id: uuid.UUID
    code: str
    name: str
    credits: float | None
    expected_hours: float | None
    planned_hours: float
    difference_percent: float | None
    status: str


@dataclass
class CreditYear:
    name: str
    credits: float
    expected_credits: int | None
    status: str


@dataclass
class CreditTable:
    hours_per_credit: int
    tolerance_percent: int
    credits_per_year: int
    years: list[CreditYear]
    modules: list[CreditRow]


@dataclass
class Dashboard:
    version: CurriculumVersion
    partial: bool
    framework: Framework | None
    frameworks: list[Framework]
    kpis: list[Kpi]
    # The date of the latest snapshot behind the trends (None: none yet or not shown).
    snapshot_on: date | None
    progress: list[ProgressRow]
    low_percent: int
    comparison: Comparison | None
    credits: CreditTable


def _percent(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _kpis(
    live: dict[str, Any],
    framework: Framework | None,
    history: list[tuple[date, dict[str, Any]]],
) -> list[Kpi]:
    objectives = live["objectives"]
    fid = str(framework.id) if framework else None
    fw = live["frameworks"].get(fid) if fid else None

    def points(pick: Any) -> list[Point]:
        out = []
        for day, metrics in history:
            value = pick(metrics)
            if value is not None:
                out.append(Point(day, float(value)))
        return out

    def mapped(m: dict[str, Any]) -> float | None:
        return _percent(m["objectives"]["mapped"], m["objectives"]["total"])

    def weighted(m: dict[str, Any]) -> float | None:
        return (m["frameworks"].get(fid) or {}).get("weighted") if fid else None

    def uncovered(m: dict[str, Any]) -> float | None:
        found = (m["frameworks"].get(fid) or {}) if fid else {}
        return found.get("uncovered")

    return [
        Kpi(
            "mapped",
            "percent",
            _percent(objectives["mapped"], objectives["total"]),
            objectives["mapped"],
            objectives["total"],
            points(mapped),
        ),
        Kpi("coverage", "percent", fw["weighted"] if fw else None, series=points(weighted)),
        Kpi(
            "gaps",
            "count",
            fw["uncovered"] if fw else None,
            fw["uncovered"] if fw else None,
            fw["items"] if fw else None,
            points(uncovered),
        ),
        Kpi(
            "credits",
            "count",
            live["credits"]["issues"],
            live["credits"]["issues"],
            live["credits"]["modules"],
            points(lambda m: m["credits"]["issues"]),
        ),
    ]


async def _progress(db: AsyncSession, visible: VisibleVersion) -> list[ProgressRow]:
    """For each module the person sees: its outcomes and the session objectives under it, how many
    have an accepted link and how many only have one waiting."""
    allowed = await visible_objective_ids(db, visible)
    modules = list(
        await db.scalars(
            select(Module)
            .where(Module.version_id == visible.version.id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    )
    modules = [m for m in modules if visible.view.shows_module(m.id)]
    event_module = dict(
        (
            await db.execute(
                select(LearningEvent.id, LearningEvent.module_id)
                .join(Module, Module.id == LearningEvent.module_id)
                .where(Module.version_id == visible.version.id)
            )
        ).all()
    )
    owner: dict[uuid.UUID, uuid.UUID] = {}
    for objective_id, module_id, event_id in await db.execute(
        select(Objective.id, Objective.module_id, Objective.learning_event_id).where(
            Objective.id.in_(allowed), Objective.level != ObjectiveLevel.PROGRAMME
        )
    ):
        target = module_id or (event_module.get(event_id) if event_id else None)
        if target is not None:
            owner[objective_id] = target
    accepted: set[uuid.UUID] = set()
    waiting: set[uuid.UUID] = set()
    for objective_id, status in await db.execute(
        select(MappingLink.objective_id, MappingLink.status).where(
            MappingLink.objective_id.in_(list(owner) or [uuid.uuid4()]),
            MappingLink.status != MappingStatus.REJECTED,
            live_link(),
        )
    ):
        if status is MappingStatus.ACCEPTED:
            accepted.add(objective_id)
        else:
            waiting.add(objective_id)
    waiting -= accepted
    rows = []
    for module in modules:
        mine = [o for o, m in owner.items() if m == module.id]
        rows.append(
            ProgressRow(
                module.id,
                module.code,
                module.name,
                len(mine),
                sum(1 for o in mine if o in accepted),
                sum(1 for o in mine if o in waiting),
            )
        )
    return rows


async def _previous_published(db: AsyncSession, visible: VisibleVersion) -> VisibleVersion | None:
    """The latest other published version of the programme the person may see."""
    candidates = await db.scalars(
        select(CurriculumVersion)
        .where(
            CurriculumVersion.programme_id == visible.programme.id,
            CurriculumVersion.status == VersionStatus.PUBLISHED,
            CurriculumVersion.id != visible.version.id,
            CurriculumVersion.deleted_at.is_(None),
        )
        .order_by(CurriculumVersion.academic_year.desc(), CurriculumVersion.created_at.desc())
    )
    for candidate in candidates:
        seen = await visible_version(db, visible.access, candidate.id)
        if seen is not None:
            return seen
    return None


def _group_values(report: coverage_report.Report) -> dict[uuid.UUID, float]:
    roots = {i.item.id for i in report.rows if i.item.parent_id is None}
    return {r.item.id: r.value for r in report.rows if r.item.id in roots}


async def _comparison(
    db: AsyncSession,
    visible: VisibleVersion,
    framework: Framework,
    policy: CoveragePolicy,
    now: coverage_report.Report,
) -> Comparison | None:
    before = await _previous_published(db, visible)
    if before is None:
        return None
    then = await coverage_report.build_report(db, before, framework, Method.WEIGHTED, policy)
    values = _group_values(then)
    groups = [
        GroupCompare(r.item.id, r.item.code, r.item.title, r.value, values.get(r.item.id))
        for r in now.rows
        if r.item.parent_id is None
    ]
    return Comparison(
        before.version.id, before.version.academic_year, before.version.status, groups
    )


async def _credit_table(db: AsyncSession, visible: VisibleVersion) -> CreditTable:
    check = await credit_check.version_credit_check(db, visible.version, visible.programme)
    return CreditTable(
        hours_per_credit=check.policy.hours_per_credit,
        tolerance_percent=check.policy.tolerance_percent,
        credits_per_year=check.policy.credits_per_year,
        years=[
            CreditYear(y.name, float(y.credits), y.expected_credits, y.status.value)
            for y in check.years
        ],
        modules=[
            CreditRow(
                m.module_id,
                m.code,
                m.name,
                float(m.credits) if m.credits is not None else None,
                float(m.expected_hours) if m.expected_hours is not None else None,
                float(m.planned_hours),
                float(m.difference_percent) if m.difference_percent is not None else None,
                m.status.value,
            )
            for m in check.modules
            if visible.view.shows_module(m.module_id)
        ],
    )


async def build_dashboard(
    db: AsyncSession,
    visible: VisibleVersion,
    policy: CoveragePolicy,
    framework_id: uuid.UUID | None,
    on: date | None = None,
) -> Dashboard:
    """The whole dashboard for one version. ``framework_id`` picks the framework behind the
    coverage figures; by default the one with the most links."""
    frameworks = await dashboard_metrics.frameworks_in_use(db, visible.version.id, visible)
    chosen = next((f for f in frameworks if f.id == framework_id), None) or (
        frameworks[0] if frameworks else None
    )
    live = await dashboard_metrics.compute_metrics(db, visible, policy)
    history = (
        [] if not visible.view.full else await dashboard_metrics.series(db, visible.version.id, on)
    )
    comparison = None
    if chosen is not None:
        report = await coverage_report.build_report(db, visible, chosen, Method.WEIGHTED, policy)
        comparison = await _comparison(db, visible, chosen, policy, report)
    return Dashboard(
        version=visible.version,
        partial=not visible.view.full,
        framework=chosen,
        frameworks=frameworks,
        kpis=_kpis(live, chosen, history),
        snapshot_on=history[-1][0] if history else None,
        progress=await _progress(db, visible),
        low_percent=policy.weighted_low_percent,
        comparison=comparison,
        credits=await _credit_table(db, visible),
    )


# --- Traceability ---------------------------------------------------------------------------


@dataclass
class TraceGroup:
    """The session objectives under one module outcome (or directly under the programme outcome)."""

    module_outcome_id: uuid.UUID | None
    objectives: int
    sessions: int


@dataclass
class TraceItem:
    id: uuid.UUID
    code: str
    title: str
    # The highest accepted coverage (1 to 5) among the objectives that reach it.
    coverage: int
    objectives: int


@dataclass
class TraceModuleOutcome:
    id: uuid.UUID
    text: str
    module_code: str | None


@dataclass
class Trace:
    outcomes: list[tuple[uuid.UUID, str]]
    outcome: tuple[uuid.UUID, str] | None
    module_outcomes: list[TraceModuleOutcome]
    groups: list[TraceGroup]
    items: list[TraceItem]
    items_total: int
    # Edges between neighbouring columns: module outcome -> group (same index) is implied;
    # group index -> item id.
    reaches: list[tuple[int, uuid.UUID]]
    module_count: int
    session_objectives: int
    sessions: int


async def build_trace(
    db: AsyncSession,
    visible: VisibleVersion,
    framework: Framework | None,
    outcome_id: uuid.UUID | None,
) -> Trace:
    """How one programme outcome is taught and which framework items it reaches: the module
    outcomes under it, the session objectives under those, and the items their accepted links
    reach. Only what the person sees."""
    allowed = await visible_objective_ids(db, visible)
    rows = {o.id: o for o in await db.scalars(select(Objective).where(Objective.id.in_(allowed)))}
    programme = sorted(
        (o for o in rows.values() if o.level is ObjectiveLevel.PROGRAMME),
        key=lambda o: (o.position, o.created_at),
    )
    outcomes = [(o.id, o.text) for o in programme]
    picked = next((o for o in programme if o.id == outcome_id), None) or (
        programme[0] if programme else None
    )
    if picked is None:
        return Trace(outcomes, None, [], [], [], 0, [], 0, 0, 0)

    children: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for child_id, parent_id in await db.execute(
        select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
            ObjectiveLink.child_id.in_(list(rows)), ObjectiveLink.parent_id.in_(list(rows))
        )
    ):
        children[parent_id].append(child_id)

    below = [c for c in children.get(picked.id, []) if c in rows]
    module_outcomes = sorted(
        (rows[c] for c in below if rows[c].level is ObjectiveLevel.MODULE),
        key=lambda o: (o.position, o.created_at),
    )
    direct_sessions = [c for c in below if rows[c].level is ObjectiveLevel.LEARNING_EVENT]
    modules = {
        m.id: m
        for m in await db.scalars(select(Module).where(Module.version_id == visible.version.id))
    }
    event_ids = {o.learning_event_id for o in rows.values() if o.learning_event_id is not None}

    def sessions_of(ids: list[uuid.UUID]) -> int:
        return len({rows[i].learning_event_id for i in ids if rows[i].learning_event_id})

    groups: list[TraceGroup] = []
    members: list[list[uuid.UUID]] = []
    for mo in module_outcomes:
        mine = [c for c in children.get(mo.id, []) if c in rows]
        members.append([mo.id, *mine])
        groups.append(TraceGroup(mo.id, len(mine), sessions_of(mine)))
    # Session objectives linked straight to the programme outcome, and to no module outcome under
    # it, are shown on their own; one that is also under a module outcome is shown there.
    covered = {i for group in members for i in group}
    alone = [c for c in direct_sessions if c not in covered]
    if alone:
        members.append(alone)
        groups.append(TraceGroup(None, len(alone), sessions_of(alone)))
    all_ids = {i for group in members for i in group} | {picked.id}

    items: dict[uuid.UUID, dict[str, Any]] = {}
    reaches: set[tuple[int, uuid.UUID]] = set()
    if framework is not None and all_ids:
        query = (
            select(
                MappingLink.objective_id,
                FrameworkItem.id,
                FrameworkItem.code,
                FrameworkItem.title,
                MappingLink.coverage,
            )
            .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
            .where(
                FrameworkItem.framework_id == framework.id,
                MappingLink.objective_id.in_(all_ids),
                MappingLink.status == MappingStatus.ACCEPTED,
                MappingLink.coverage >= 1,
                live_link(),
            )
        )
        where = {i: index for index, group in enumerate(members) for i in group}
        for objective_id, item_id, code, title, coverage in await db.execute(query):
            found = items.setdefault(
                item_id, {"code": code, "title": title, "coverage": 0, "objectives": set()}
            )
            found["coverage"] = max(found["coverage"], coverage)
            found["objectives"].add(objective_id)
            if objective_id in where:
                reaches.add((where[objective_id], item_id))
    ordered = sorted(
        items.items(), key=lambda kv: (-len(kv[1]["objectives"]), -kv[1]["coverage"], kv[1]["code"])
    )
    shown = ordered[:MAX_TRACE_ITEMS]
    shown_ids = {item_id for item_id, _ in shown}
    session_objective_ids = [i for i in all_ids if rows[i].level is ObjectiveLevel.LEARNING_EVENT]
    return Trace(
        outcomes=outcomes,
        outcome=(picked.id, picked.text),
        module_outcomes=[
            TraceModuleOutcome(
                mo.id, mo.text, modules[mo.module_id].code if mo.module_id in modules else None
            )
            for mo in module_outcomes
        ],
        groups=groups,
        items=[
            TraceItem(item_id, v["code"], v["title"], v["coverage"], len(v["objectives"]))
            for item_id, v in shown
        ],
        items_total=len(ordered),
        reaches=sorted(
            ((g, i) for g, i in reaches if i in shown_ids), key=lambda e: (e[0], str(e[1]))
        ),
        module_count=len({mo.module_id for mo in module_outcomes if mo.module_id}),
        session_objectives=len(session_objective_ids),
        sessions=len({rows[i].learning_event_id for i in session_objective_ids} & event_ids),
    )
