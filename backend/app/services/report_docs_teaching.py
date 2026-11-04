"""The teaching reports (Slice 1.24, ADR 053) as report documents: teaching formats and contact
hours, the curriculum relationship report, the role balance report (health profile) and the
assessment methods report.

Like every report they show only what the reader's roles show (ADR 027). Hours are worked out from
the minutes of the sessions (contact time and self-study time).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.profiles import Feature
from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    LearningEvent,
    MappingLink,
    Module,
    ObjectiveLink,
    Phase,
    TagList,
    TagValue,
)
from app.models.curriculum import Objective, ObjectiveLevel
from app.models.mapping import MappingStatus
from app.models.tagging import TaggableType, TagListKind
from app.services.authorization import InvalidRequestError
from app.services.coverage_report import _framework_tree
from app.services.institution_settings import get_institution, parse_settings
from app.services.mapping_live import live_link
from app.services.objective_checks import visible_objectives
from app.services.report_context import ReportContext, common_about
from app.services.report_export import Column, Kind, ReportDoc, Section
from app.services.role_balance import Resolution, resolve, split_minutes
from app.services.tagging import item_tags

NO_PHASE = "(no phase)"
NO_FORMAT = "No format set"
NOT_MAPPED = "Not mapped to this framework"
MAX_ROWS = 5000
MAX_LISTED = 200


def _now() -> datetime:
    return datetime.now(UTC)


def hours(minutes: int | float) -> float:
    return round(minutes / 60, 1)


@dataclass
class Teaching:
    """The phases, modules and sessions the reader may see, after the phase filter."""

    phases: dict[uuid.UUID, Phase]
    modules: dict[uuid.UUID, Module]
    events: list[LearningEvent]
    formats: dict[uuid.UUID, str] = field(default_factory=dict)

    def phase_key(self, module_id: uuid.UUID) -> uuid.UUID | None:
        module = self.modules.get(module_id)
        return module.phase_id if module and module.phase_id in self.phases else None

    def phase_name(self, key: uuid.UUID | None) -> str:
        return self.phases[key].name if key in self.phases else NO_PHASE

    def phase_order(self) -> list[uuid.UUID | None]:
        used = {self.phase_key(m) for m in self.modules}
        ordered: list[uuid.UUID | None] = [
            p.id for p in sorted(self.phases.values(), key=lambda p: p.position) if p.id in used
        ]
        if None in used:
            ordered.append(None)
        return ordered

    def format_label(self, event: LearningEvent) -> str:
        return (
            self.formats.get(event.format_value_id, NO_FORMAT)
            if event.format_value_id
            else NO_FORMAT
        )


async def load_teaching(ctx: ReportContext) -> Teaching:
    view = ctx.visible.view
    version_id = ctx.visible.version.id
    db = ctx.db
    phases = {
        p.id: p
        for p in await db.scalars(
            select(Phase).where(Phase.version_id == version_id, Phase.deleted_at.is_(None))
        )
    }
    modules: dict[uuid.UUID, Module] = {}
    for module in await db.scalars(
        select(Module)
        .where(Module.version_id == version_id, Module.deleted_at.is_(None))
        .order_by(Module.position, Module.code)
    ):
        if ctx.phase_id is not None and module.phase_id != ctx.phase_id:
            continue
        if view.shows_module(module.id) or module.id in view.events:
            modules[module.id] = module
    events = [
        e
        for e in await db.scalars(
            select(LearningEvent)
            .where(LearningEvent.module_id.in_(list(modules) or [uuid.uuid4()]))
            .where(LearningEvent.deleted_at.is_(None))
            .order_by(LearningEvent.week.is_(None), LearningEvent.week, LearningEvent.position)
        )
        if view.shows_event(e.module_id, e.id)
    ]
    wanted = {e.format_value_id for e in events if e.format_value_id}
    formats = {}
    if wanted:
        formats = {
            v.id: v.label for v in await db.scalars(select(TagValue).where(TagValue.id.in_(wanted)))
        }
    return Teaching(phases, modules, events, formats)


def _about(
    ctx: ReportContext, title: str, method: str, made: datetime, extra: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    return [
        ("Report", title),
        ("Method", method),
        *extra,
        *common_about(ctx.visible, made.strftime("%Y-%m-%d %H:%M UTC"), not ctx.visible.view.full),
    ]


# --- Teaching formats and contact hours -------------------------------------------------------


async def build_formats(ctx: ReportContext) -> ReportDoc:
    made = _now()
    teaching = await load_teaching(ctx)
    method = "Sum of the minutes of the sessions, by teaching format, phase and module"

    by_format: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_phase: dict[uuid.UUID | None, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0, 0])
    )
    by_module: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])
    for event in teaching.events:
        label = teaching.format_label(event)
        for bucket in (
            by_format[label],
            by_phase[teaching.phase_key(event.module_id)][label],
            by_module[event.module_id],
        ):
            bucket[0] += 1
            bucket[1] += event.contact_minutes
            bucket[2] += event.self_study_minutes
    total_contact = sum(b[1] for b in by_format.values())

    columns = [
        Column("Sessions", Kind.INTEGER),
        Column("Contact hours", Kind.NUMBER),
        Column("Self-study hours", Kind.NUMBER),
    ]
    formats = Section(
        "By teaching format",
        [Column("Teaching format"), *columns, Column("Share of contact time", Kind.PERCENT)],
        [],
        note=(
            "All the sessions you may see. The format is the teaching-method tag "
            "set on the session."
        ),
    )
    for label, (n, contact, study) in sorted(by_format.items(), key=lambda kv: -kv[1][1]):
        formats.rows.append(
            [
                label,
                n,
                hours(contact),
                hours(study),
                contact / total_contact if total_contact else 0.0,
            ]
        )
    formats.rows.append(
        [
            "All formats",
            sum(b[0] for b in by_format.values()),
            hours(total_contact),
            hours(sum(b[2] for b in by_format.values())),
            1.0 if total_contact else 0.0,
        ]
    )

    phases = Section(
        "By phase and format",
        [
            Column("Phase"),
            Column("Teaching format"),
            *columns,
            Column("Share of the phase's contact time", Kind.PERCENT),
        ],
        [],
        note="Each phase's formats, then its total.",
    )
    for key in teaching.phase_order():
        formats_here = by_phase.get(key, {})
        phase_contact = sum(b[1] for b in formats_here.values())
        for label, (n, contact, study) in sorted(formats_here.items(), key=lambda kv: -kv[1][1]):
            phases.rows.append(
                [
                    teaching.phase_name(key),
                    label,
                    n,
                    hours(contact),
                    hours(study),
                    contact / phase_contact if phase_contact else 0.0,
                ]
            )
        phases.rows.append(
            [
                teaching.phase_name(key),
                "All formats",
                sum(b[0] for b in formats_here.values()),
                hours(phase_contact),
                hours(sum(b[2] for b in formats_here.values())),
                1.0 if phase_contact else 0.0,
            ]
        )

    modules = Section(
        "By module",
        [Column("Module"), Column("Name"), Column("Phase"), *columns],
        [],
        note="Contact time and self-study time of each module's sessions, as planned.",
    )
    for module in teaching.modules.values():
        n, contact, study = by_module.get(module.id, [0, 0, 0])
        modules.rows.append(
            [
                module.code,
                module.name,
                teaching.phase_name(teaching.phase_key(module.id)),
                n,
                hours(contact),
                hours(study),
            ]
        )
    programme = Section(
        "Programme",
        [Column("Measure"), Column("Value", Kind.NUMBER)],
        [
            ["Sessions", float(sum(b[0] for b in by_format.values()))],
            ["Contact hours", hours(total_contact)],
            ["Self-study hours", hours(sum(b[2] for b in by_format.values()))],
        ],
        note="Everything you may see in this version.",
    )
    return ReportDoc(
        key="formats",
        title="Teaching formats and contact hours",
        about=_about(
            ctx,
            "Teaching formats and contact hours",
            "Contact and self-study minutes of the sessions, added up by teaching "
            "format, phase and module.",
            made,
            [],
        ),
        method=method,
        made_on=made,
        sections=[programme, formats, phases, modules],
    )


# --- Curriculum relationship ------------------------------------------------------------------


async def build_relationship(ctx: ReportContext) -> ReportDoc:
    made = _now()
    teaching = await load_teaching(ctx)
    chosen = await visible_objectives(ctx.db, ctx.visible)
    by_event: dict[uuid.UUID, list[Objective]] = defaultdict(list)
    for objective, _, event in chosen:
        if objective.level is ObjectiveLevel.LEARNING_EVENT and event is not None:
            by_event[event.id].append(objective)
    tags = await item_tags(
        ctx.db,
        {
            TaggableType.LEARNING_EVENT: [e.id for e in teaching.events],
            TaggableType.OBJECTIVE: [o.id for found in by_event.values() for o in found],
        },
    )

    def tag_text(kind: TaggableType, item_id: uuid.UUID) -> str:
        return "; ".join(
            f"{t.tag_list.name}: {t.value.label}" for t in tags.get((kind, item_id), [])
        )

    order = {key: index for index, key in enumerate(teaching.phase_order())}
    events = sorted(
        teaching.events,
        key=lambda e: (
            order.get(teaching.phase_key(e.module_id), 999),
            teaching.modules[e.module_id].position,
            e.week is None,
            e.week or 0,
            e.position,
        ),
    )
    section = Section(
        "Sessions, objectives and tags",
        [
            Column("Phase"),
            Column("Module"),
            Column("Week", Kind.INTEGER),
            Column("Session"),
            Column("Teaching format"),
            Column("Session tags"),
            Column("Objective"),
            Column("Objective tags"),
        ],
        [],
        note=(
            "One row for each session and objective of that session (a session "
            "with no objective has "
            "one row). Tags are the tags set on the session or the objective, and "
            "those they inherit."
        ),
    )
    capped = False
    for event in events:
        module = teaching.modules[event.module_id]
        base = [
            teaching.phase_name(teaching.phase_key(module.id)),
            module.code,
            event.week,
            event.title,
            teaching.format_label(event),
            tag_text(TaggableType.LEARNING_EVENT, event.id),
        ]
        objectives = sorted(by_event.get(event.id, []), key=lambda o: (o.position, o.created_at))
        for objective in objectives or [None]:  # type: ignore[list-item]
            if len(section.rows) >= MAX_ROWS:
                capped = True
                break
            section.rows.append(
                [
                    *base,
                    objective.text if objective else None,
                    tag_text(TaggableType.OBJECTIVE, objective.id) if objective else None,
                ]
            )
    if capped:
        section.note += f" Cut at {MAX_ROWS} rows."
    return ReportDoc(
        key="relationship",
        title="Curriculum relationship report",
        about=_about(
            ctx,
            "Curriculum relationship report",
            "Each session with its objectives and their tags, one row each.",
            made,
            [],
        ),
        method="Session, objective and tags, one row each",
        made_on=made,
        sections=[section],
    )


# --- Role balance (health profile) ------------------------------------------------------------


async def build_role_balance(ctx: ReportContext) -> ReportDoc:
    institution = await get_institution(ctx.db)
    features = parse_settings(institution.settings).features if institution else frozenset()
    if Feature.ROLE_BALANCE_REPORT not in features:
        raise InvalidRequestError(
            "The role balance report belongs to the health profile, which this institution has "
            "not turned on."
        )
    framework = await ctx.framework()
    made = _now()
    teaching = await load_teaching(ctx)
    tree = await _framework_tree(ctx.db, framework)
    root_of: dict[uuid.UUID, uuid.UUID] = {}
    for item in tree.items:
        current = item
        while current.parent_id is not None and current.parent_id in tree.by_id:
            current = tree.by_id[current.parent_id]
        root_of[item.id] = current.id
    groups = tree.groups()

    chosen = await visible_objectives(ctx.db, ctx.visible)
    # Objectives of modules and sessions in the phases being reported on (programme outcomes
    # belong to no phase).
    everything = {
        o.id: (o, m) for o, m, _e in chosen if o.level is not ObjectiveLevel.PROGRAMME and m
    }
    in_scope = {oid: (o, m.id) for oid, (o, m) in everything.items() if m.id in teaching.modules}
    rows = await ctx.db.execute(
        select(MappingLink.objective_id, MappingLink.framework_item_id).where(
            MappingLink.status == MappingStatus.ACCEPTED,
            MappingLink.coverage >= 1,
            MappingLink.objective_id.in_(list(everything) or [uuid.uuid4()]),
            MappingLink.framework_item_id.in_(list(root_of) or [uuid.uuid4()]),
            live_link(),
        )
    )
    own: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for objective_id, item_id in rows:
        own[objective_id].add(root_of[item_id])
    up_links: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for child_id, parent_id in await ctx.db.execute(
        select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
            ObjectiveLink.child_id.in_(list(in_scope) or [uuid.uuid4()])
        )
    ):
        parent = everything.get(parent_id)
        if parent is not None and parent[0].level is ObjectiveLevel.MODULE:
            up_links[child_id].append(parent_id)
    module_groups: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for oid, (objective, module) in everything.items():
        if objective.level is ObjectiveLevel.MODULE:
            module_groups[module.id] |= own.get(oid, set())

    def resolution(objective_id: uuid.UUID, module_id: uuid.UUID) -> Resolution:
        parents = [own.get(p, set()) for p in up_links.get(objective_id, [])]
        return resolve(own.get(objective_id, set()), parents, module_groups.get(module_id, set()))

    # Objectives: per phase, how many count for each group (and how many of those are estimated).
    objectives_in_phase: dict[uuid.UUID | None, int] = defaultdict(int)
    per_group_objectives: dict[tuple[uuid.UUID | None, uuid.UUID], int] = defaultdict(int)
    estimated_objectives: dict[tuple[uuid.UUID | None, uuid.UUID], int] = defaultdict(int)
    unmapped_objectives: dict[uuid.UUID | None, int] = defaultdict(int)
    event_resolutions: dict[uuid.UUID, list[Resolution]] = defaultdict(list)
    for objective_id, (objective, module_id) in in_scope.items():
        key = teaching.phase_key(module_id)
        objectives_in_phase[key] += 1
        if objective.level is ObjectiveLevel.LEARNING_EVENT:
            found = resolution(objective_id, module_id)
            if objective.learning_event_id:
                event_resolutions[objective.learning_event_id].append(found)
        else:
            found = Resolution(frozenset(own.get(objective_id, set())), False)
        if not found.groups:
            unmapped_objectives[key] += 1
        for group_id in found.groups:
            per_group_objectives[(key, group_id)] += 1
            if found.estimated:
                estimated_objectives[(key, group_id)] += 1

    # Teaching time: equal share per objective, divided among the objective's groups.
    minutes_in_phase: dict[uuid.UUID | None, float] = defaultdict(float)
    per_group_minutes: dict[tuple[uuid.UUID | None, uuid.UUID], float] = defaultdict(float)
    estimated_minutes: dict[tuple[uuid.UUID | None, uuid.UUID], float] = defaultdict(float)
    unmapped_minutes: dict[uuid.UUID | None, float] = defaultdict(float)
    for event in teaching.events:
        key = teaching.phase_key(event.module_id)
        minutes_in_phase[key] += event.contact_minutes
        resolutions = event_resolutions.get(event.id) or [
            resolve([], None, module_groups.get(event.module_id, set()))
        ]
        for target, minutes, estimated in split_minutes(event.contact_minutes, resolutions):
            if target is None:
                unmapped_minutes[key] += minutes
                continue
            per_group_minutes[(key, target)] += minutes
            if estimated:
                estimated_minutes[(key, target)] += minutes

    time = Section(
        "Teaching time by group and phase",
        [
            Column("Phase"),
            Column("Group"),
            Column("Contact hours", Kind.NUMBER),
            Column("of which estimated", Kind.NUMBER),
            Column("Share of the phase's contact time", Kind.PERCENT),
        ],
        [],
        note=(
            "Each objective of a session gets an equal share of the session's contact time, "
            "divided among the framework groups the objective is accepted for. Where a session "
            "objective has no accepted link of its own, its groups are estimated from the module "
            "outcomes it links up to (or, with no upward link, from the outcomes of its module); "
            "the estimated hours are shown apart. What is not found is 'not mapped'. The shares "
            "of a phase add up to 100%."
        ),
    )
    count = Section(
        "Objectives by group and phase",
        [
            Column("Phase"),
            Column("Group"),
            Column("Objectives", Kind.INTEGER),
            Column("of which estimated", Kind.INTEGER),
            Column("Share of the phase's objectives", Kind.PERCENT),
        ],
        [],
        note=(
            "Module outcomes and session objectives counted for the group (session objectives "
            "without a link of their own are estimated as above). An objective that maps to two "
            "groups counts for both, so a phase's shares can add up to more than 100%."
        ),
    )
    for key in teaching.phase_order():
        name = teaching.phase_name(key)
        total_minutes = minutes_in_phase.get(key, 0.0)
        total_objectives = objectives_in_phase.get(key, 0)
        for group in groups:
            minutes = per_group_minutes.get((key, group.id), 0.0)
            time.rows.append(
                [
                    name,
                    f"{group.code} {group.title}",
                    hours(minutes),
                    hours(estimated_minutes.get((key, group.id), 0.0)),
                    minutes / total_minutes if total_minutes else 0.0,
                ]
            )
            n = per_group_objectives.get((key, group.id), 0)
            count.rows.append(
                [
                    name,
                    f"{group.code} {group.title}",
                    n,
                    estimated_objectives.get((key, group.id), 0),
                    n / total_objectives if total_objectives else 0.0,
                ]
            )
        unmapped = unmapped_minutes.get(key, 0.0)
        time.rows.append(
            [
                name,
                NOT_MAPPED,
                hours(unmapped),
                0.0,
                unmapped / total_minutes if total_minutes else 0.0,
            ]
        )
        n = unmapped_objectives.get(key, 0)
        count.rows.append(
            [name, NOT_MAPPED, n, 0, n / total_objectives if total_objectives else 0.0]
        )
    return ReportDoc(
        key="role-balance",
        title="Role balance report",
        about=_about(
            ctx,
            "Role balance report",
            "The share of teaching time and of objectives that goes to each top-level group of the "
            "framework, in each phase.",
            made,
            [("Framework", f"{framework.name} ({framework.version_label})")],
        ),
        method="Share of teaching time and objectives per framework group and phase",
        made_on=made,
        sections=[time, count],
    )


# --- Assessment methods -----------------------------------------------------------------------


async def build_assessment_methods(ctx: ReportContext) -> ReportDoc:
    made = _now()
    teaching = await load_teaching(ctx)
    module_ids = list(teaching.modules) or [uuid.uuid4()]
    chosen = await visible_objectives(ctx.db, ctx.visible)
    objectives = {o.id: (o, m, e) for o, m, e in chosen if o.level is not ObjectiveLevel.PROGRAMME}

    values = list(
        await ctx.db.execute(
            select(TagValue, TagList)
            .join(TagList, TagList.id == TagValue.tag_list_id)
            .where(
                TagList.kind == TagListKind.ASSESSMENT_METHOD,
                TagList.deleted_at.is_(None),
                TagValue.deleted_at.is_(None),
            )
            .order_by(TagList.name, TagValue.position, TagValue.label)
        )
    )
    assessments = list(
        await ctx.db.scalars(
            select(Assessment).where(
                Assessment.module_id.in_(module_ids), Assessment.deleted_at.is_(None)
            )
        )
    )
    assessed: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)  # method value -> objective ids
    assessed_any: set[uuid.UUID] = set()
    by_assessment = {a.id: a for a in assessments}
    if by_assessment:
        for assessment_id, objective_id in await ctx.db.execute(
            select(AssessmentItem.assessment_id, AssessmentItemObjective.objective_id)
            .join(AssessmentItemObjective, AssessmentItemObjective.item_id == AssessmentItem.id)
            .where(
                AssessmentItem.assessment_id.in_(list(by_assessment)),
                AssessmentItem.deleted_at.is_(None),
            )
        ):
            if objective_id not in objectives:
                continue
            assessed_any.add(objective_id)
            method = by_assessment[assessment_id].method_value_id
            if method is not None:
                assessed[method].add(objective_id)
    tags = await item_tags(
        ctx.db,
        {
            TaggableType.MODULE: list(teaching.modules),
            TaggableType.OBJECTIVE: list(objectives),
        },
    )
    tagged_modules: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    tagged_objectives: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    tagged_any: set[uuid.UUID] = set()
    for (kind, item_id), found in tags.items():
        for tag in found:
            if tag.tag_list.kind is not TagListKind.ASSESSMENT_METHOD:
                continue
            if kind is TaggableType.MODULE:
                tagged_modules[tag.value.id].add(item_id)
            elif kind is TaggableType.OBJECTIVE:
                tagged_objectives[tag.value.id].add(item_id)
                tagged_any.add(item_id)

    by_method = Section(
        "By assessment method",
        [
            Column("Method"),
            Column("Assessments", Kind.INTEGER),
            Column("Modules with such an assessment", Kind.INTEGER),
            Column("Objectives assessed by them", Kind.INTEGER),
            Column("Modules tagged with the method", Kind.INTEGER),
            Column("Objectives tagged with the method", Kind.INTEGER),
        ],
        [],
        note=(
            "Every value of the assessment-method tag lists. 'Assessed' means an item "
            "of an assessment of "
            "that method is linked to the objective; 'tagged' means the method is a tag on the "
            "module or objective (including tags passed down)."
        ),
    )
    for value, tag_list in values:
        mine = [a for a in assessments if a.method_value_id == value.id]
        by_method.rows.append(
            [
                f"{tag_list.name}: {value.label}",
                len(mine),
                len({a.module_id for a in mine}),
                len(assessed.get(value.id, set())),
                len(tagged_modules.get(value.id, set())),
                len(tagged_objectives.get(value.id, set())),
            ]
        )
    without = [
        (o, m, e)
        for o, m, e in chosen
        if o.level is not ObjectiveLevel.PROGRAMME
        and o.id not in assessed_any
        and o.id not in tagged_any
    ]
    unassessed = Section(
        f"Objectives with no assessment method ({len(without)})",
        [Column("Kind"), Column("Module"), Column("Session"), Column("Objective")],
        [
            [
                "Module outcome" if o.level is ObjectiveLevel.MODULE else "Session",
                m.code if m else None,
                e.title if e else None,
                o.text,
            ]
            for o, m, e in without[:MAX_LISTED]
        ],
        note=(
            "Module outcomes and session objectives that no assessment item is linked "
            "to and that have "
            "no assessment-method tag."
            + (f" Showing {MAX_LISTED} of {len(without)}." if len(without) > MAX_LISTED else "")
        ),
    )
    return ReportDoc(
        key="assessments",
        title="Assessment methods report",
        about=_about(
            ctx,
            "Assessment methods report",
            "Assessments and tags by assessment method, from the assessments of each "
            "module and the "
            "assessment-method tags. A basic view: full blueprints come in a later phase.",
            made,
            [],
        ),
        method="Assessments and assessment-method tags by method",
        made_on=made,
        sections=[by_method, unassessed],
    )
