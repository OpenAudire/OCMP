"""Comparing two curriculum versions of a programme (ADR 030).

Items are matched first by lineage: copy forward records each copy's original in
``based_on_id``, so an item is followed back (or forward) through the years, also
across intermediate versions and when it has been renamed. Items without lineage
are matched by their natural key: phases by name, modules by code (ignoring case),
sessions by title within matched modules, objectives by text within matched owners.

Assessments are matched the same way (by name within matched modules). The diff lists
added, removed and changed phases, modules, sessions, assessments and objectives
(programme, module and session level) with the fields that differ; an assessment also
shows its number of items. Order, upward links, tags, assessment items themselves, the
objectives they assess and framework mappings are not compared.
"""

import uuid
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assessment,
    AssessmentItem,
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    Phase,
    TagValue,
    TaxonomyLevel,
)
from app.models.curriculum import ObjectiveLevel

# Lineage chains are followed at most this many versions back.
MAX_GENERATIONS = 200


class ItemKind(StrEnum):
    PHASE = "phase"
    MODULE = "module"
    LEARNING_EVENT = "learning_event"
    ASSESSMENT = "assessment"
    OBJECTIVE = "objective"


class Change(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


Value = str | int | None


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: Value
    after: Value


@dataclass(frozen=True)
class ItemChange:
    kind: ItemKind
    change: Change
    # The item in the compared version (None when removed) and in the base version
    # (None when added).
    id: uuid.UUID | None
    base_id: uuid.UUID | None
    label: str
    # Where the item sits: the module of a session, the owner of an objective.
    context: str | None = None
    level: ObjectiveLevel | None = None
    fields: list[FieldChange] = field(default_factory=list)
    order: tuple[int, ...] = ()


@dataclass(frozen=True)
class VersionDiff:
    base: CurriculumVersion
    version: CurriculumVersion
    changes: list[ItemChange]

    def count(self, kind: ItemKind, change: Change) -> int:
        return sum(1 for c in self.changes if c.kind == kind and c.change == change)


@dataclass
class _Snapshot:
    """The live content of one version."""

    phases: dict[uuid.UUID, Phase]
    modules: dict[uuid.UUID, Module]
    events: dict[uuid.UUID, LearningEvent]
    objectives: dict[uuid.UUID, Objective]
    assessments: dict[uuid.UUID, Assessment]
    item_counts: dict[uuid.UUID, int]
    methods: dict[uuid.UUID, str]
    formats: dict[uuid.UUID, str]
    levels: dict[uuid.UUID, str]


async def _snapshot(db: AsyncSession, version: CurriculumVersion) -> _Snapshot:
    phases = await db.scalars(
        select(Phase).where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
    )
    modules = {
        m.id: m
        for m in await db.scalars(
            select(Module).where(Module.version_id == version.id, Module.deleted_at.is_(None))
        )
    }
    events = {
        e.id: e
        for e in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.module_id.in_(list(modules)), LearningEvent.deleted_at.is_(None)
            )
        )
    }
    objectives = {
        o.id: o
        for o in await db.scalars(
            select(Objective).where(
                Objective.version_id == version.id, Objective.deleted_at.is_(None)
            )
        )
        if (o.module_id is None or o.module_id in modules)
        and (o.learning_event_id is None or o.learning_event_id in events)
    }
    assessments = {
        a.id: a
        for a in await db.scalars(
            select(Assessment).where(
                Assessment.module_id.in_(list(modules)), Assessment.deleted_at.is_(None)
            )
        )
    }
    item_counts: dict[uuid.UUID, int] = {}
    if assessments:
        item_counts = dict(
            (
                await db.execute(
                    select(AssessmentItem.assessment_id, func.count())
                    .where(
                        AssessmentItem.assessment_id.in_(list(assessments)),
                        AssessmentItem.deleted_at.is_(None),
                    )
                    .group_by(AssessmentItem.assessment_id)
                )
            ).all()
        )
    method_ids = {a.method_value_id for a in assessments.values() if a.method_value_id}
    methods = dict(
        (
            await db.execute(select(TagValue.id, TagValue.label).where(TagValue.id.in_(method_ids)))
        ).all()
    )
    format_ids = {e.format_value_id for e in events.values() if e.format_value_id}
    level_ids = {o.taxonomy_level_id for o in objectives.values() if o.taxonomy_level_id}
    formats = dict(
        (
            await db.execute(select(TagValue.id, TagValue.label).where(TagValue.id.in_(format_ids)))
        ).all()
    )
    levels = dict(
        (
            await db.execute(
                select(TaxonomyLevel.id, TaxonomyLevel.name).where(TaxonomyLevel.id.in_(level_ids))
            )
        ).all()
    )
    return _Snapshot(
        {p.id: p for p in phases},
        modules,
        events,
        objectives,
        assessments,
        item_counts,
        methods,
        formats,
        levels,
    )


Row = Phase | Module | LearningEvent | Assessment | Objective


async def _follow[R: (Phase, Module, LearningEvent, Assessment, Objective)](
    db: AsyncSession, model: type[Row], rows: dict[uuid.UUID, R], targets: set[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Each row whose ``based_on_id`` chain reaches one of ``targets``, with that target."""
    found: dict[uuid.UUID, uuid.UUID] = {}
    frontier = {row_id: row.based_on_id for row_id, row in rows.items() if row.based_on_id}
    for _ in range(MAX_GENERATIONS):
        waiting: dict[uuid.UUID, uuid.UUID] = {}
        for row_id, ancestor in frontier.items():
            if ancestor in targets:
                found[row_id] = ancestor
            elif ancestor is not None:
                waiting[row_id] = ancestor
        if not waiting:
            break
        parents = dict(
            (
                await db.execute(
                    select(model.id, model.based_on_id).where(model.id.in_(set(waiting.values())))
                )
            ).all()
        )
        frontier = {
            row_id: parent
            for row_id, ancestor in waiting.items()
            if (parent := parents.get(ancestor)) is not None
        }
        if not frontier:
            break
    return found


class _Matches:
    """A one-to-one pairing of base rows and compared rows."""

    def __init__(self) -> None:
        self.to_new: dict[uuid.UUID, uuid.UUID] = {}
        self.to_base: dict[uuid.UUID, uuid.UUID] = {}

    def pair(self, base_id: uuid.UUID, new_id: uuid.UUID) -> None:
        if base_id not in self.to_new and new_id not in self.to_base:
            self.to_new[base_id] = new_id
            self.to_base[new_id] = base_id


async def _match[R: (Phase, Module, LearningEvent, Assessment, Objective)](
    db: AsyncSession,
    model: type[Row],
    base: dict[uuid.UUID, R],
    new: dict[uuid.UUID, R],
    key: Callable[[R, bool], Hashable | None],
) -> _Matches:
    """Pair rows by lineage (either direction), then the rest by ``key(row, is_base)``."""
    matches = _Matches()
    for new_id, base_id in (await _follow(db, model, new, set(base))).items():
        matches.pair(base_id, new_id)
    for base_id, new_id in (await _follow(db, model, base, set(new))).items():
        matches.pair(base_id, new_id)
    by_key: dict[Hashable, uuid.UUID] = {}
    for base_id, row in base.items():
        if base_id not in matches.to_new and (k := key(row, True)) is not None:
            by_key.setdefault(k, base_id)
    for new_id, row in new.items():
        if new_id in matches.to_base or (k := key(row, False)) is None:
            continue
        if (found := by_key.get(k)) is not None:
            matches.pair(found, new_id)
    return matches


def _fold(text: str) -> str:
    return " ".join(text.split()).casefold()


def _credits(value: Decimal | int | None) -> str | None:
    return None if value is None else format(Decimal(value).normalize(), "f")


def _fields(before: dict[str, Value], after: dict[str, Value]) -> list[FieldChange]:
    return [
        FieldChange(name, before[name], after[name])
        for name in after
        if before[name] != after[name]
    ]


def _changes(
    kind: ItemKind,
    matches: _Matches,
    base: dict[uuid.UUID, Any],
    new: dict[uuid.UUID, Any],
    describe: Callable[[Any, bool], tuple[str, str | None, tuple[int, ...], dict[str, Value]]],
    level: Callable[[Any], ObjectiveLevel | None] = lambda _row: None,
) -> Iterable[ItemChange]:
    for new_id, row in new.items():
        label, context, order, values = describe(row, False)
        base_id = matches.to_base.get(new_id)
        if base_id is None:
            yield ItemChange(
                kind, Change.ADDED, new_id, None, label, context, level(row), [], order
            )
            continue
        changed = _fields(describe(base[base_id], True)[3], values)
        if changed:
            yield ItemChange(
                kind, Change.CHANGED, new_id, base_id, label, context, level(row), changed, order
            )
    for base_id, row in base.items():
        if base_id not in matches.to_new:
            label, context, order, _values = describe(row, True)
            yield ItemChange(
                kind, Change.REMOVED, None, base_id, label, context, level(row), [], order
            )


async def diff_versions(
    db: AsyncSession, base: CurriculumVersion, version: CurriculumVersion
) -> VersionDiff:
    """What changed from ``base`` to ``version``."""
    old, new = await _snapshot(db, base), await _snapshot(db, version)

    phases = await _match(db, Phase, old.phases, new.phases, lambda p, _b: _fold(p.name))
    modules = await _match(db, Module, old.modules, new.modules, lambda m, _b: m.code.casefold())

    def event_key(event: LearningEvent, is_base: bool) -> Hashable | None:
        module_id = modules.to_new.get(event.module_id) if is_base else event.module_id
        return None if module_id is None else (module_id, _fold(event.title))

    events = await _match(db, LearningEvent, old.events, new.events, event_key)

    def assessment_key(assessment: Assessment, is_base: bool) -> Hashable | None:
        module_id = modules.to_new.get(assessment.module_id) if is_base else assessment.module_id
        return None if module_id is None else (module_id, _fold(assessment.name))

    assessments = await _match(db, Assessment, old.assessments, new.assessments, assessment_key)

    def owner(objective: Objective, is_base: bool) -> uuid.UUID | None:
        """The objective's owner, as an id in the compared version."""
        if objective.level == ObjectiveLevel.PROGRAMME:
            return version.id
        if objective.level == ObjectiveLevel.MODULE:
            assert objective.module_id is not None
            return modules.to_new.get(objective.module_id) if is_base else objective.module_id
        assert objective.learning_event_id is not None
        if is_base:
            return events.to_new.get(objective.learning_event_id)
        return objective.learning_event_id

    def objective_key(objective: Objective, is_base: bool) -> Hashable | None:
        found = owner(objective, is_base)
        return None if found is None else (found, _fold(objective.text))

    objectives = await _match(db, Objective, old.objectives, new.objectives, objective_key)

    def snap(is_base: bool) -> _Snapshot:
        return old if is_base else new

    def describe_phase(
        phase: Phase, _is_base: bool
    ) -> tuple[str, None, tuple[int, ...], dict[str, Value]]:
        return phase.name, None, (phase.position,), {"name": phase.name, "kind": phase.kind.value}

    def module_label(module: Module) -> str:
        return f"{module.code} {module.name}"

    def module_order(module: Module, s: _Snapshot) -> tuple[int, ...]:
        phase = s.phases.get(module.phase_id) if module.phase_id else None
        return (phase.position if phase else 10_000, module.position)

    def describe_module(
        module: Module, is_base: bool
    ) -> tuple[str, None, tuple[int, ...], dict[str, Value]]:
        s = snap(is_base)
        phase = s.phases.get(module.phase_id) if module.phase_id else None
        # Phases compare by identity: the matched phase counts as the same phase.
        phase_ref: Value = None
        if phase is not None:
            phase_ref = str(phases.to_new.get(phase.id, phase.id) if is_base else phase.id)
        return (
            module_label(module),
            None,
            module_order(module, s),
            {
                "code": module.code,
                "name": module.name,
                "phase": phase_ref,
                "credits": _credits(module.credits),
                "nqf_level": module.nqf_level,
                "description": module.description,
                "external_lms_ref": module.external_lms_ref,
            },
        )

    def describe_event(
        event: LearningEvent, is_base: bool
    ) -> tuple[str, str, tuple[int, ...], dict[str, Value]]:
        s = snap(is_base)
        module = s.modules[event.module_id]
        return (
            event.title,
            module_label(module),
            (*module_order(module, s), event.position),
            {
                "title": event.title,
                "format": s.formats.get(event.format_value_id) if event.format_value_id else None,
                "contact_minutes": event.contact_minutes,
                "self_study_minutes": event.self_study_minutes,
                "week": event.week,
                "description": event.description,
                "external_lms_ref": event.external_lms_ref,
            },
        )

    def describe_assessment(
        assessment: Assessment, is_base: bool
    ) -> tuple[str, str, tuple[int, ...], dict[str, Value]]:
        s = snap(is_base)
        module = s.modules[assessment.module_id]
        return (
            assessment.name,
            module_label(module),
            (*module_order(module, s), assessment.position),
            {
                "name": assessment.name,
                "method": (
                    s.methods.get(assessment.method_value_id)
                    if assessment.method_value_id
                    else None
                ),
                "weight": _credits(assessment.weight),
                "timing": assessment.timing,
                "time_minutes": assessment.time_minutes,
                "items": s.item_counts.get(assessment.id, 0),
            },
        )

    def describe_objective(
        objective: Objective, is_base: bool
    ) -> tuple[str, str | None, tuple[int, ...], dict[str, Value]]:
        s = snap(is_base)
        context: str | None = None
        order: tuple[int, ...] = (-1,)
        if objective.module_id is not None:
            module = s.modules[objective.module_id]
            context = module_label(module)
            order = (*module_order(module, s), -1)
        elif objective.learning_event_id is not None:
            event = s.events[objective.learning_event_id]
            module = s.modules[event.module_id]
            context = f"{module.code} · {event.title}"
            order = (*module_order(module, s), event.position)
        return (
            objective.text,
            context,
            (*order, objective.position),
            {
                "text": objective.text,
                "domain": objective.domain.value if objective.domain else None,
                "taxonomy_level": (
                    s.levels.get(objective.taxonomy_level_id)
                    if objective.taxonomy_level_id
                    else None
                ),
                "status": objective.status.value,
            },
        )

    changes = [
        *_changes(ItemKind.PHASE, phases, old.phases, new.phases, describe_phase),
        *_changes(ItemKind.MODULE, modules, old.modules, new.modules, describe_module),
        *_changes(ItemKind.LEARNING_EVENT, events, old.events, new.events, describe_event),
        *_changes(
            ItemKind.ASSESSMENT,
            assessments,
            old.assessments,
            new.assessments,
            describe_assessment,
        ),
        *_changes(
            ItemKind.OBJECTIVE,
            objectives,
            old.objectives,
            new.objectives,
            describe_objective,
            level=lambda objective: objective.level,
        ),
    ]
    # Phases were compared by identity; show their names.
    names = {str(p.id): p.name for p in [*old.phases.values(), *new.phases.values()]}
    for item in changes:
        for index, change in enumerate(item.fields):
            if change.field == "phase":
                item.fields[index] = FieldChange(
                    "phase",
                    names.get(str(change.before)) if change.before else None,
                    names.get(str(change.after)) if change.after else None,
                )
    kinds = list(ItemKind)
    changes.sort(key=lambda c: (kinds.index(c.kind), c.order, c.label))
    return VersionDiff(base, version, changes)
