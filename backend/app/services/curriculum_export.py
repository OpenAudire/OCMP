"""Exports of a curriculum version (Slice 1.27, ADR 056): the full round-trip workbook, the
objectives x framework items matrix, and the JSON of a whole version.

All three read only what the person's roles show of the version (ADR 027) and say so when it is
only part. The workbook is written with the same field definitions and sheets as the imports
(``import_fields``, ``import_fields_data``), so it can be imported back: an item made on the
screens, which has no External ID, is written with its internal id, which an import recognises
(``curriculum_import.key_of``).
"""

from __future__ import annotations

import io
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    Framework,
    FrameworkItem,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    Tagging,
    TagList,
    TagValue,
    TaxonomyLevel,
)
from app.models.curriculum import ObjectiveLevel
from app.models.mapping import MappingStatus
from app.models.tagging import TAGGING_COLUMNS, TaggableType
from app.services import tagging
from app.services.curriculum_import import key_of
from app.services.curriculum_read import VisibleVersion
from app.services.import_fields import LEVEL_WORDS, SHEETS, Lists, build_workbook
from app.services.import_fields_data import MAPPING_SHEETS, TAG_SHEETS
from app.services.mapping_live import live_link

JSON_SCHEMA = "ocmp.curriculum-version"
JSON_SCHEMA_VERSION = 1
LEVEL_WORD = {ObjectiveLevel(v): k for k, v in LEVEL_WORDS.items()}
ROUND_TRIP_HOW = (
    "  This workbook is an export of one curriculum version, in the same sheets as the import "
    "templates. Edit it and import it back (curriculum, tags and mappings are read from their "
    "own sheets).",
    "  Items made on the screens have no External ID of your own: the export writes their "
    "internal id, which the import recognises, so importing the file into the same version "
    "updates and does not duplicate.",
    "  The Status column of the Mappings sheet is information only. An import suggests the "
    "links (or accepts them if you say they were already reviewed).",
    "  Retired objectives are included. Rejected mapping links are not.",
)


@dataclass
class Scope:
    """What of a version the person sees."""

    visible: VisibleVersion
    phases: list[Phase]
    modules: list[Module]
    events: list[LearningEvent]
    objectives: list[Objective]
    module_by_id: dict[uuid.UUID, Module] = field(default_factory=dict)
    event_by_id: dict[uuid.UUID, LearningEvent] = field(default_factory=dict)

    @property
    def partial(self) -> bool:
        return not self.visible.view.full


async def load_scope(db: AsyncSession, visible: VisibleVersion) -> Scope:
    view, version = visible.view, visible.version
    phases = list(
        await db.scalars(
            select(Phase)
            .where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
            .order_by(Phase.position, Phase.created_at)
        )
    )
    modules = [
        m
        for m in await db.scalars(
            select(Module)
            .where(Module.version_id == version.id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
        if view.shows_module(m.id) or m.id in view.events
    ]
    events = [
        e
        for e in await db.scalars(
            select(LearningEvent)
            .where(
                LearningEvent.module_id.in_([m.id for m in modules] or [uuid.uuid4()]),
                LearningEvent.deleted_at.is_(None),
            )
            .order_by(LearningEvent.position, LearningEvent.created_at)
        )
        if view.shows_event(e.module_id, e.id)
    ]
    module_by_id = {m.id: m for m in modules}
    order = {m.id: i for i, m in enumerate(modules)}
    events.sort(key=lambda e: (order[e.module_id], e.position))
    event_by_id = {e.id: e for e in events}
    rank = {ObjectiveLevel.PROGRAMME: 0, ObjectiveLevel.MODULE: 1, ObjectiveLevel.LEARNING_EVENT: 2}
    objectives = []
    for o in await db.scalars(
        select(Objective).where(Objective.version_id == version.id, Objective.deleted_at.is_(None))
    ):
        if o.level is ObjectiveLevel.PROGRAMME:
            if view.full:
                objectives.append(o)
        elif o.level is ObjectiveLevel.MODULE:
            if o.module_id in module_by_id and view.shows_module(o.module_id):
                objectives.append(o)
        elif o.learning_event_id in event_by_id:
            objectives.append(o)

    def sort_key(o: Objective) -> tuple[int, int, int, int]:
        if o.level is ObjectiveLevel.PROGRAMME:
            return (0, 0, 0, o.position)
        if o.level is ObjectiveLevel.MODULE:
            return (rank[o.level], order[o.module_id or uuid.UUID(int=0)], 0, o.position)
        event = event_by_id[o.learning_event_id or uuid.UUID(int=0)]
        return (rank[o.level], order[event.module_id], event.position, o.position)

    objectives.sort(key=sort_key)
    return Scope(visible, phases, modules, events, objectives, module_by_id, event_by_id)


async def _parent_keys(db: AsyncSession, scope: Scope) -> dict[uuid.UUID, list[str]]:
    by_id = {o.id: o for o in scope.objectives}
    out: dict[uuid.UUID, list[str]] = defaultdict(list)
    for child_id, parent_id in await db.execute(
        select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
            ObjectiveLink.child_id.in_(list(by_id) or [uuid.uuid4()])
        )
    ):
        parent = by_id.get(parent_id)
        if parent is not None:
            out[child_id].append(key_of(parent))
    return out


async def _links(
    db: AsyncSession, scope: Scope, *, with_rejected: bool
) -> list[tuple[MappingLink, Objective, FrameworkItem, Framework]]:
    by_id = {o.id: o for o in scope.objectives}
    query = (
        select(MappingLink, FrameworkItem, Framework)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .join(Framework, Framework.id == FrameworkItem.framework_id)
        .where(MappingLink.objective_id.in_(list(by_id) or [uuid.uuid4()]), live_link())
        .order_by(MappingLink.created_at, MappingLink.id)
    )
    if not with_rejected:
        query = query.where(MappingLink.status != MappingStatus.REJECTED)
    return [
        (link, by_id[link.objective_id], item, framework)
        for link, item, framework in (await db.execute(query)).all()
    ]


async def _lists_for(db: AsyncSession, visible: VisibleVersion) -> Lists:
    formats = await tagging.teaching_formats(db, {visible.programme.faculty_id})
    levels = list(await db.scalars(select(TaxonomyLevel).order_by(TaxonomyLevel.position)))
    return Lists(
        formats=tuple(dict.fromkeys(v.label for v, _ in formats)),
        taxonomy_levels=tuple(dict.fromkeys(level.name for level in levels)),
    )


# --- The full round-trip workbook ---------------------------------------------------------


async def _tag_cells(db: AsyncSession, scope: Scope) -> dict[uuid.UUID, str]:
    """The Tags cell of each module, session and objective: its **direct** tags that an import
    could set again (active lists and tags), each as ``list key: label``. Inherited tags are left
    out: they follow from the direct ones."""
    out: dict[uuid.UUID, list[str]] = defaultdict(list)
    for kind, ids in (
        (TaggableType.MODULE, [m.id for m in scope.modules]),
        (TaggableType.LEARNING_EVENT, [e.id for e in scope.events]),
        (TaggableType.OBJECTIVE, [o.id for o in scope.objectives]),
    ):
        column = getattr(Tagging, TAGGING_COLUMNS[kind])
        rows = await db.execute(
            select(column, TagList.key, TagValue.label)
            .join(TagValue, TagValue.id == Tagging.tag_value_id)
            .join(TagList, TagList.id == TagValue.tag_list_id)
            .where(
                column.in_(ids or [uuid.uuid4()]),
                Tagging.inherited_from_id.is_(None),
                TagList.deleted_at.is_(None),
                TagList.is_active.is_(True),
                TagValue.deleted_at.is_(None),
                TagValue.is_active.is_(True),
            )
            .order_by(TagList.key, TagValue.label)
        )
        for item_id, key, label in rows:
            out[item_id].append(f"{key}: {label}")
    return {item_id: "; ".join(tags) for item_id, tags in out.items()}


async def build_roundtrip(db: AsyncSession, visible: VisibleVersion) -> bytes:
    """The whole version in the sheets of the import templates (curriculum, tags, mappings)."""
    scope = await load_scope(db, visible)
    phase_by_id = {p.id: p for p in scope.phases}
    format_label = {
        v.id: v.label
        for v in await db.scalars(
            select(TagValue).where(
                TagValue.id.in_([e.format_value_id for e in scope.events if e.format_value_id])
            )
        )
    }
    level_name = {level.id: level.name for level in await db.scalars(select(TaxonomyLevel))}
    parents = await _parent_keys(db, scope)
    tag_cells = await _tag_cells(db, scope)

    rows: dict[str, list[list[Any]]] = {s.key: [] for s in (*SHEETS, *TAG_SHEETS, *MAPPING_SHEETS)}
    for p in scope.phases:
        rows["phases"].append([key_of(p), p.name, p.kind.value])
    for m in scope.modules:
        phase = phase_by_id.get(m.phase_id) if m.phase_id else None
        rows["modules"].append(
            [
                key_of(m),
                m.code,
                m.name,
                key_of(phase) if phase else None,
                float(m.credits) if m.credits is not None else None,
                m.nqf_level,
                m.description or None,
                m.external_lms_ref,
                tag_cells.get(m.id),
            ]
        )
    for e in scope.events:
        rows["sessions"].append(
            [
                key_of(e),
                key_of(scope.module_by_id[e.module_id]),
                e.title,
                format_label.get(e.format_value_id) if e.format_value_id else None,
                e.contact_minutes,
                e.self_study_minutes,
                e.week,
                e.description or None,
                e.external_lms_ref,
                tag_cells.get(e.id),
            ]
        )
    for o in scope.objectives:
        if o.level is ObjectiveLevel.PROGRAMME:
            owner = None
        elif o.level is ObjectiveLevel.MODULE:
            owner = key_of(scope.module_by_id[o.module_id]) if o.module_id else None
        else:
            owner = key_of(scope.event_by_id[o.learning_event_id]) if o.learning_event_id else None
        rows["objectives"].append(
            [
                key_of(o),
                LEVEL_WORD[o.level],
                owner,
                o.text,
                o.domain.value if o.domain else None,
                level_name.get(o.taxonomy_level_id) if o.taxonomy_level_id else None,
                "; ".join(parents.get(o.id, [])) or None,
                tag_cells.get(o.id),
            ]
        )

    words = {"learning_event": "session"}
    for tag_list in await db.scalars(
        select(TagList)
        .where(TagList.deleted_at.is_(None), TagList.faculty_id.is_(None))
        .order_by(TagList.key)
    ):
        rows["tag_lists"].append(
            [
                tag_list.key,
                tag_list.name,
                tag_list.kind.value,
                tag_list.description or None,
                "; ".join(words.get(t, t) for t in tag_list.entity_types),
            ]
        )
        for value in await db.scalars(
            select(TagValue)
            .where(TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None))
            .order_by(TagValue.position, TagValue.label)
        ):
            rows["tag_values"].append(
                [tag_list.key, value.label, value.code, value.description or None]
            )

    for link, objective, item, framework in await _links(db, scope, with_rejected=False):
        if not link.coverage:
            continue
        rows["mappings"].append(
            [
                key_of(objective),
                framework.key,
                framework.version_label,
                item.code,
                link.coverage,
                link.depth_match.value if link.depth_match else None,
                link.rationale or None,
                link.status.value,
            ]
        )
    return build_workbook(
        await _lists_for(db, visible),
        rows,
        sheets=(*SHEETS, *TAG_SHEETS, *MAPPING_SHEETS),
        heading=(
            f"Export of {visible.programme.code} {visible.version.academic_year} "
            f"({visible.version.status.value}), made {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"
        ),
        how=ROUND_TRIP_HOW,
    )


# --- The matrix: objectives x framework items ---------------------------------------------

_SHADES = {1: "DCEFEC", 2: "BFE0DB", 3: "93CBC4", 4: "5FB0A6", 5: "2E8F84"}


def _tree_order(items: list[FrameworkItem]) -> list[tuple[FrameworkItem, int]]:
    """Items depth first, children by position then code, with their depth."""
    children: dict[uuid.UUID | None, list[FrameworkItem]] = defaultdict(list)
    known = {i.id for i in items}
    for item in items:
        children[item.parent_id if item.parent_id in known else None].append(item)
    for found in children.values():
        found.sort(key=lambda i: (i.position, i.code))
    out: list[tuple[FrameworkItem, int]] = []

    def walk(parent: uuid.UUID | None, depth: int) -> None:
        for item in children.get(parent, []):
            out.append((item, depth))
            walk(item.id, depth + 1)

    walk(None, 0)
    return out


async def build_matrix(db: AsyncSession, visible: VisibleVersion, framework: Framework) -> bytes:
    """Objectives (rows) by the items of one framework (columns); a cell is the coverage score of
    the accepted link (1 to 5). Only accepted links with a coverage of at least 1 count, as in the
    coverage reports; groups show no figure of their own."""
    scope = await load_scope(db, visible)
    items = list(
        await db.scalars(select(FrameworkItem).where(FrameworkItem.framework_id == framework.id))
    )
    ordered = _tree_order(items)
    leaves = {i.id for i, _ in ordered} - {i.parent_id for i, _ in ordered if i.parent_id}
    column = {item.id: index for index, (item, _) in enumerate(ordered)}
    by_objective: dict[uuid.UUID, dict[int, int]] = defaultdict(dict)
    for link, objective, item, found in await _links(db, scope, with_rejected=False):
        if (
            found.id == framework.id
            and link.status is MappingStatus.ACCEPTED
            and link.coverage
            and link.coverage >= 1
        ):
            by_objective[objective.id][column[item.id]] = link.coverage

    book = Workbook()
    ws = book.active
    assert ws is not None
    ws.title = "Matrix"
    head = ["Level", "Module", "Session", "Objective"]
    ws.append([*head, *[item.code for item, _ in ordered], "Items covered"])
    ws.cell(row=1, column=1).font = Font(bold=True)
    fixed = len(head)
    for index, (item, _depth) in enumerate(ordered):
        cell = ws.cell(row=1, column=fixed + 1 + index)
        cell.font = Font(bold=True, italic=item.id not in leaves)
        cell.alignment = Alignment(text_rotation=90, vertical="bottom", horizontal="center")
        ws.column_dimensions[get_column_letter(fixed + 1 + index)].width = 4.5
    for index in range(fixed):
        ws.cell(row=1, column=index + 1).font = Font(bold=True)
    ws.row_dimensions[1].height = 70
    for o in scope.objectives:
        module = scope.module_by_id.get(o.module_id) if o.module_id else None
        event = scope.event_by_id.get(o.learning_event_id) if o.learning_event_id else None
        if event is not None:
            module = scope.module_by_id.get(event.module_id)
        cells = by_objective.get(o.id, {})
        row = [LEVEL_WORD[o.level], module.code if module else None, event.title if event else None]
        row.append(o.text)
        marks: list[Any] = [None] * len(ordered)
        for index, coverage in cells.items():
            marks[index] = coverage
        ws.append([*row, *marks, len(cells)])
        for index, coverage in cells.items():
            cell = ws.cell(row=ws.max_row, column=fixed + 1 + index)
            cell.fill = PatternFill("solid", start_color=_SHADES[min(5, max(1, coverage))])
            cell.alignment = Alignment(horizontal="center")
        ws.cell(row=ws.max_row, column=fixed).alignment = Alignment(wrap_text=True, vertical="top")
    ws.append(
        ["Objectives covering the item", None, None, None]
        + [sum(1 for c in by_objective.values() if index in c) for index in range(len(ordered))]
    )
    for column_letter, width in zip("ABCD", (14, 12, 28, 70), strict=True):
        ws.column_dimensions[column_letter].width = width
    ws.freeze_panes = ws.cell(row=2, column=fixed + 1)

    key = book.create_sheet("Items")
    key.append(["Code", "Title", "Level"])
    for item, depth in ordered:
        key.append([item.code, item.title, depth + 1])
    key.column_dimensions["A"].width = 16
    key.column_dimensions["B"].width = 90
    about = book.create_sheet("About")
    version = visible.version
    lines = [
        ("Report", "Objectives x framework items"),
        (
            "Method",
            "A cell holds the coverage score (1 to 5) of the accepted mapping link between the "
            "objective and the item. Suggested, waiting and rejected links are not shown. "
            "Groups (items with items below them) have no figure of their own.",
        ),
        ("Framework", f"{framework.name} ({framework.version_label})"),
        (
            "Curriculum version",
            f"{visible.programme.code} {visible.programme.name}, {version.academic_year} "
            f"({version.status.value})",
        ),
        ("Made on", f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC"),
    ]
    if scope.partial:
        lines.append(("Only part of the curriculum", "You see only part of this version."))
    for label, value in lines:
        about.append([label, value])
    about.column_dimensions["A"].width = 30
    about.column_dimensions["B"].width = 110
    for cell in about["A"]:
        cell.font = Font(bold=True)
    book.move_sheet("About", offset=-2)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# --- JSON of a whole version ----------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def build_json(db: AsyncSession, visible: VisibleVersion) -> dict[str, Any]:
    """Everything the person sees of the version as one document. Ids are the internal ids (stable
    for the version) and every item also carries its External ID, if it has one."""
    scope = await load_scope(db, visible)
    version, programme = visible.version, visible.programme
    parents = await _parent_keys(db, scope)
    tag_rows = await _taggings(db, scope)
    module_ids = [m.id for m in scope.modules]

    assessments = []
    for a in await db.scalars(
        select(Assessment)
        .where(
            Assessment.module_id.in_(module_ids or [uuid.uuid4()]), Assessment.deleted_at.is_(None)
        )
        .order_by(Assessment.created_at)
    ):
        if a.module_id not in scope.module_by_id or not visible.view.shows_module(a.module_id):
            continue
        items = []
        for item in await db.scalars(
            select(AssessmentItem)
            .where(AssessmentItem.assessment_id == a.id, AssessmentItem.deleted_at.is_(None))
            .order_by(AssessmentItem.position)
        ):
            linked = list(
                await db.scalars(
                    select(AssessmentItemObjective.objective_id).where(
                        AssessmentItemObjective.item_id == item.id
                    )
                )
            )
            items.append(
                {
                    "id": str(item.id),
                    "label": item.label,
                    "marks": float(item.marks) if item.marks is not None else None,
                    "objective_ids": [
                        str(x) for x in linked if x in {o.id for o in scope.objectives}
                    ],
                }
            )
        assessments.append(
            {
                "id": str(a.id),
                "module_id": str(a.module_id),
                "name": a.name,
                "method_value_id": str(a.method_value_id) if a.method_value_id else None,
                "weight": float(a.weight) if a.weight is not None else None,
                "timing": a.timing,
                "time_minutes": a.time_minutes,
                "items": items,
            }
        )

    mapping = [
        {
            "objective_id": str(objective.id),
            "framework": framework.key,
            "framework_version": framework.version_label,
            "item_code": item.code,
            "coverage": link.coverage,
            "depth": link.depth_match.value if link.depth_match else None,
            "rationale": link.rationale or None,
            "source": link.source.value,
            "status": link.status.value,
            "accept_method": link.accept_method.value if link.accept_method else None,
            "needs_recheck": link.needs_recheck,
        }
        for link, objective, item, framework in await _links(db, scope, with_rejected=True)
    ]
    return {
        "schema": JSON_SCHEMA,
        "schema_version": JSON_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "partial": scope.partial,
        "version": {
            "id": str(version.id),
            "programme_code": programme.code,
            "programme_name": programme.name,
            "academic_year": version.academic_year,
            "status": version.status.value,
            "published_at": _iso(version.published_at),
        },
        "phases": [
            {
                "id": str(p.id),
                "external_id": p.external_id,
                "name": p.name,
                "kind": p.kind.value,
                "position": p.position,
            }
            for p in scope.phases
        ],
        "modules": [
            {
                "id": str(m.id),
                "external_id": m.external_id,
                "phase_id": str(m.phase_id) if m.phase_id else None,
                "code": m.code,
                "name": m.name,
                "credits": float(m.credits) if m.credits is not None else None,
                "nqf_level": m.nqf_level,
                "description": m.description,
                "external_lms_ref": m.external_lms_ref,
                "position": m.position,
            }
            for m in scope.modules
        ],
        "sessions": [
            {
                "id": str(e.id),
                "external_id": e.external_id,
                "module_id": str(e.module_id),
                "title": e.title,
                "format_value_id": str(e.format_value_id) if e.format_value_id else None,
                "contact_minutes": e.contact_minutes,
                "self_study_minutes": e.self_study_minutes,
                "week": e.week,
                "description": e.description,
                "external_lms_ref": e.external_lms_ref,
                "position": e.position,
            }
            for e in scope.events
        ],
        "objectives": [
            {
                "id": str(o.id),
                "external_id": o.external_id,
                "level": LEVEL_WORD[o.level],
                "module_id": str(o.module_id) if o.module_id else None,
                "session_id": str(o.learning_event_id) if o.learning_event_id else None,
                "text": o.text,
                "domain": o.domain.value if o.domain else None,
                "taxonomy_level_id": str(o.taxonomy_level_id) if o.taxonomy_level_id else None,
                "status": o.status.value,
                "broader": parents.get(o.id, []),
                "position": o.position,
            }
            for o in scope.objectives
        ],
        "assessments": assessments,
        "tags": tag_rows,
        "mapping_links": mapping,
    }


async def _taggings(db: AsyncSession, scope: Scope) -> dict[str, Any]:
    """The tag lists and values used on the visible items, and the direct taggings."""
    columns = {
        "module": (Tagging.module_id, {m.id for m in scope.modules}),
        "session": (Tagging.learning_event_id, {e.id for e in scope.events}),
        "objective": (Tagging.objective_id, {o.id for o in scope.objectives}),
    }
    taggings = []
    value_ids: set[uuid.UUID] = set()
    for kind, (column, ids) in columns.items():
        for row in await db.scalars(
            select(Tagging).where(
                column.in_(list(ids) or [uuid.uuid4()]), Tagging.inherited_from_id.is_(None)
            )
        ):
            item_id = {
                "module": row.module_id,
                "session": row.learning_event_id,
                "objective": row.objective_id,
            }[kind]
            taggings.append(
                {"item": kind, "item_id": str(item_id), "value_id": str(row.tag_value_id)}
            )
            value_ids.add(row.tag_value_id)
    values = list(
        await db.execute(
            select(TagValue, TagList)
            .join(TagList, TagList.id == TagValue.tag_list_id)
            .where(TagValue.id.in_(value_ids or {uuid.uuid4()}))
        )
    )
    return {
        "values": [
            {
                "id": str(v.id),
                "label": v.label,
                "code": v.code,
                "list_key": tag_list.key,
                "list_name": tag_list.name,
                "list_kind": tag_list.kind.value,
            }
            for v, tag_list in values
        ],
        "taggings": taggings,
    }
