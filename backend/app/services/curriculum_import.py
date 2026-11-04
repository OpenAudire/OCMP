"""Excel import of a curriculum version's structure and objectives (Slice 1.25, ADR 054).

``check`` reads a workbook made from the template (``import_fields``), checks every row and works
out what importing it would do, **without writing anything** (this is the preview and the dry run).
``apply`` runs the same plan through the ordinary editing services (``curriculum_edit``,
``curriculum_objectives``), so every rule of the screens applies and every change is audited, all
in one transaction.

Rows are matched by **External ID** within the version: a known id updates that item, a new id
makes a new one. An import never deletes anything and never moves an item to another owner.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CurriculumVersion,
    ImportJob,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    TaxonomyLevel,
    TaxonomyScale,
    User,
)
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, PhaseKind
from app.services import curriculum_edit, curriculum_objectives, tagging
from app.services.authorization import ConflictError
from app.services.curriculum_edit import EventFields, ModuleFields
from app.services.import_common import (
    CREATE,
    UNCHANGED,
    UPDATE,
    Book,
    Op,
    Plan,
    RowPlan,
    clean_rows,
    differences,
    read_workbook,
)
from app.services.import_fields import (
    LEVEL_WORDS,
    SHEET_BY_KEY,
    SHEETS,
    Lists,
    ParsedRow,
)

_LEVEL_OF = {word: ObjectiveLevel(value) for word, value in LEVEL_WORDS.items()}


# --- Reading the workbook -----------------------------------------------------------------


# --- Cleaning one cell --------------------------------------------------------------------


# --- The state of the version -------------------------------------------------------------


@dataclass
class Existing:
    version: CurriculumVersion
    phases: dict[str, Phase]
    modules: dict[str, Module]
    events: dict[str, LearningEvent]
    objectives: dict[str, Objective]
    modules_by_id: dict[uuid.UUID, Module]
    phases_by_id: dict[uuid.UUID, Phase]
    events_by_id: dict[uuid.UUID, LearningEvent]
    parent_links: dict[uuid.UUID, set[uuid.UUID]]
    formats: dict[str, list[uuid.UUID]]
    format_labels: tuple[str, ...]
    levels: dict[str, list[uuid.UUID]]
    level_labels: tuple[str, ...]

    def lists(self) -> Lists:
        return Lists(formats=self.format_labels, taxonomy_levels=self.level_labels)


async def load_existing(
    db: AsyncSession, version: CurriculumVersion, faculty_id: uuid.UUID, default_scale: str | None
) -> Existing:
    """Everything the import needs to know about the version, the formats and the levels."""
    phases = list(
        await db.scalars(
            select(Phase).where(Phase.version_id == version.id, Phase.deleted_at.is_(None))
        )
    )
    modules = list(
        await db.scalars(
            select(Module).where(Module.version_id == version.id, Module.deleted_at.is_(None))
        )
    )
    events = list(
        await db.scalars(
            select(LearningEvent).where(
                LearningEvent.module_id.in_([m.id for m in modules] or [uuid.uuid4()]),
                LearningEvent.deleted_at.is_(None),
            )
        )
    )
    objectives = list(
        await db.scalars(
            select(Objective).where(
                Objective.version_id == version.id, Objective.deleted_at.is_(None)
            )
        )
    )
    links: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for child_id, parent_id in await db.execute(
        select(ObjectiveLink.child_id, ObjectiveLink.parent_id).where(
            ObjectiveLink.child_id.in_([o.id for o in objectives] or [uuid.uuid4()])
        )
    ):
        links[child_id].add(parent_id)

    formats: dict[str, list[uuid.UUID]] = defaultdict(list)
    labels: dict[str, str] = {}
    for value, _tag_list in await tagging.teaching_formats(db, {faculty_id}):
        formats[value.label.casefold()].append(value.id)
        labels.setdefault(value.label.casefold(), value.label)

    query = select(TaxonomyLevel, TaxonomyScale).join(
        TaxonomyScale, TaxonomyScale.id == TaxonomyLevel.scale_id
    )
    if default_scale:
        query = query.where(TaxonomyScale.key == default_scale)
    levels: dict[str, list[uuid.UUID]] = defaultdict(list)
    level_labels: dict[str, str] = {}
    for level, _scale in (await db.execute(query.order_by(TaxonomyLevel.position))).all():
        levels[level.name.casefold()].append(level.id)
        level_labels.setdefault(level.name.casefold(), level.name)

    return Existing(
        version=version,
        phases={p.external_id: p for p in phases if p.external_id},
        modules={m.external_id: m for m in modules if m.external_id},
        events={e.external_id: e for e in events if e.external_id},
        objectives={o.external_id: o for o in objectives if o.external_id},
        modules_by_id={m.id: m for m in modules},
        phases_by_id={p.id: p for p in phases},
        events_by_id={e.id: e for e in events},
        parent_links=links,
        formats=dict(formats),
        format_labels=tuple(labels.values()),
        levels=dict(levels),
        level_labels=tuple(level_labels.values()),
    )


# --- Checking and planning ----------------------------------------------------------------


async def check(
    db: AsyncSession,
    version: CurriculumVersion,
    content: bytes,
    *,
    max_bytes: int,
    faculty_id: uuid.UUID,
    default_scale: str | None,
) -> Plan:
    """Read, check and plan an import into ``version``. Writes nothing.

    Raises:
        ConflictError: If the version is not a draft.
    """
    curriculum_edit.ensure_editable(version)
    plan = Plan(sheet_keys=tuple(sh.key for sh in SHEETS))
    existing = await load_existing(db, version, faculty_id, default_scale)
    lists = existing.lists()
    book = read_workbook(content, max_bytes, plan, SHEETS)
    if plan.problems and not book.rows:
        return plan

    phase_rows = clean_rows(SHEET_BY_KEY["phases"], book, lists, plan)
    module_rows = clean_rows(SHEET_BY_KEY["modules"], book, lists, plan)
    session_rows = clean_rows(SHEET_BY_KEY["sessions"], book, lists, plan)
    objective_rows = clean_rows(SHEET_BY_KEY["objectives"], book, lists, plan)
    sheet_phases = {v["external_id"] for _, v in phase_rows}
    sheet_modules = {v["external_id"] for _, v in module_rows}
    sheet_sessions = {v["external_id"] for _, v in session_rows}

    _plan_phases(plan, phase_rows, existing, book)
    _plan_modules(plan, module_rows, existing, book, sheet_phases)
    session_module = _plan_sessions(plan, session_rows, existing, book, sheet_modules)
    _plan_objectives(
        plan,
        objective_rows,
        existing,
        book,
        sheet_modules,
        sheet_sessions,
        session_module,
        {v["external_id"]: v for _, v in module_rows},
    )
    if not plan.problems and not plan.rows:
        plan.add(None, None, None, "The workbook has no rows to import.")
    return plan


def _plan_phases(
    plan: Plan, rows: list[tuple[ParsedRow, dict[str, Any]]], existing: Existing, book: Book
) -> None:
    names = {"name": "Name", "kind": "Kind"}
    sheet = SHEET_BY_KEY["phases"]
    for row, values in rows:
        ext = values["external_id"]
        if "kind" in book.columns["phases"]:
            values["kind"] = PhaseKind(values["kind"]) if values.get("kind") else PhaseKind.YEAR
        found = existing.phases.get(ext)
        if found is None:
            plan.rows.append(RowPlan(sheet.key, row.number, ext, CREATE, values["name"]))
            plan.ops.append(Op(sheet.key, row.number, CREATE, ext, values))
            continue
        changed = differences(found, values, names)
        plan.rows.append(
            RowPlan(
                sheet.key,
                row.number,
                ext,
                UPDATE if changed else UNCHANGED,
                values.get("name") or found.name,
                changed,
            )
        )
        if changed:
            plan.ops.append(Op(sheet.key, row.number, UPDATE, ext, values, found))


def _plan_modules(
    plan: Plan,
    rows: list[tuple[ParsedRow, dict[str, Any]]],
    existing: Existing,
    book: Book,
    sheet_phases: set[str],
) -> None:
    names = {
        "code": "Code",
        "name": "Name",
        "credits": "Credits",
        "nqf_level": "NQF level",
        "description": "Description",
        "external_lms_ref": "LMS reference",
    }
    sheet = SHEET_BY_KEY["modules"]
    present = book.columns.get("modules", set())
    # Who holds each code after the import: the version's modules first, then the sheet's rows
    # in order (a module that gets a new code gives up its old one).
    owners: dict[str, str] = {}
    for m in existing.modules_by_id.values():
        owners[m.code.casefold()] = m.external_id or str(m.id)
    # A module made on the screens has no External ID yet: a row with its code adopts it.
    adoptable = {m.code.casefold(): m for m in existing.modules_by_id.values() if not m.external_id}
    for row, values in rows:
        ext = values["external_id"]
        found = existing.modules.get(ext)
        adopting = False
        if found is None and values.get("code"):
            candidate = adoptable.pop(values["code"].casefold(), None)
            if candidate is not None:
                found, adopting = candidate, True
                owners = {k: v for k, v in owners.items() if v != str(candidate.id)}
                values["_adopt"] = True
        if found is not None and not adopting:
            owners = {k: v for k, v in owners.items() if v != ext}
        code = values.get("code") or (found.code if found else None)
        if code is not None:
            taken = owners.get(code.casefold())
            if taken is not None and taken != ext:
                plan.add(sheet.title, row.number, "Code", f"The code {code} is used twice.")
                continue
            owners[code.casefold()] = ext
        phase_ext = values.get("phase")
        if (
            "phase" in present
            and phase_ext is not None
            and phase_ext not in sheet_phases
            and phase_ext not in existing.phases
        ):
            plan.add(
                sheet.title,
                row.number,
                "Phase (External ID)",
                f"No phase has the External ID '{phase_ext}'.",
            )
            continue
        if found is None:
            plan.rows.append(RowPlan(sheet.key, row.number, ext, CREATE, values["name"]))
            plan.ops.append(Op(sheet.key, row.number, CREATE, ext, values))
            continue
        changed = differences(found, values, names)
        if adopting:
            changed.insert(0, "External ID")
        if "phase" in present:
            current = (
                existing.phases_by_id[found.phase_id].external_id
                if found.phase_id in existing.phases_by_id
                else None
            )
            if current != phase_ext:
                changed.append("Phase")
        plan.rows.append(
            RowPlan(
                sheet.key,
                row.number,
                ext,
                UPDATE if changed else UNCHANGED,
                values.get("name") or found.name,
                changed,
            )
        )
        if changed:
            plan.ops.append(Op(sheet.key, row.number, UPDATE, ext, values, found))


def _plan_sessions(
    plan: Plan,
    rows: list[tuple[ParsedRow, dict[str, Any]]],
    existing: Existing,
    book: Book,
    sheet_modules: set[str],
) -> dict[str, str]:
    """Plan the sessions; returns each session's module External ID (sheet and existing)."""
    names = {
        "title": "Title",
        "contact_minutes": "Contact minutes",
        "self_study_minutes": "Self-study minutes",
        "week": "Week",
        "description": "Description",
        "external_lms_ref": "LMS reference",
    }
    sheet = SHEET_BY_KEY["sessions"]
    present = book.columns.get("sessions", set())
    module_of: dict[str, str] = {}
    for ext, event in existing.events.items():
        module = existing.modules_by_id.get(event.module_id)
        if module is not None and module.external_id:
            module_of[ext] = module.external_id
    for row, values in rows:
        ext = values["external_id"]
        module_ext = values["module"]
        if module_ext not in sheet_modules and module_ext not in existing.modules:
            plan.add(
                sheet.title,
                row.number,
                "Module (External ID)",
                f"No module has the External ID '{module_ext}'.",
            )
            continue
        found = existing.events.get(ext)
        if found is not None and module_of.get(ext) != module_ext:
            plan.add(
                sheet.title,
                row.number,
                "Module (External ID)",
                "A session cannot be moved to another module by an import.",
            )
            continue
        module_of[ext] = module_ext
        if "format" in present:
            label = values.get("format")
            ids = existing.formats.get(label.casefold(), []) if label else []
            if label and len(ids) != 1:
                plan.add(
                    sheet.title,
                    row.number,
                    "Teaching format",
                    f"The teaching format '{label}' is in more than one list; rename one.",
                )
                continue
            values["format_value_id"] = ids[0] if ids else None
        for key in ("contact_minutes", "self_study_minutes"):
            if key in present and values.get(key) is None:
                values[key] = 0
        if found is None:
            plan.rows.append(RowPlan(sheet.key, row.number, ext, CREATE, values["title"]))
            plan.ops.append(Op(sheet.key, row.number, CREATE, ext, values))
            continue
        changed = differences(found, values, names)
        if "format" in present and found.format_value_id != values["format_value_id"]:
            changed.append("Teaching format")
        plan.rows.append(
            RowPlan(
                sheet.key,
                row.number,
                ext,
                UPDATE if changed else UNCHANGED,
                values.get("title") or found.title,
                changed,
            )
        )
        if changed:
            plan.ops.append(Op(sheet.key, row.number, UPDATE, ext, values, found))
    return module_of


def _plan_objectives(
    plan: Plan,
    rows: list[tuple[ParsedRow, dict[str, Any]]],
    existing: Existing,
    book: Book,
    sheet_modules: set[str],
    sheet_sessions: set[str],
    session_module: dict[str, str],
    module_values: dict[str, dict[str, Any]],
) -> None:
    sheet = SHEET_BY_KEY["objectives"]
    present = book.columns.get("objectives", set())
    # Every objective the import knows: External ID -> (level, module External ID or None).
    known: dict[str, tuple[ObjectiveLevel, str | None]] = {}
    for ext, objective in existing.objectives.items():
        module = existing.modules_by_id.get(objective.module_id) if objective.module_id else None
        if objective.level is ObjectiveLevel.LEARNING_EVENT:
            event = existing.events_by_id.get(objective.learning_event_id or uuid.uuid4())
            module = existing.modules_by_id.get(event.module_id) if event else None
        known[ext] = (objective.level, module.external_id if module else None)
    owner_of: dict[str, str | None] = {}
    for ext, objective in existing.objectives.items():
        if objective.level is ObjectiveLevel.MODULE and objective.module_id:
            m = existing.modules_by_id.get(objective.module_id)
            owner_of[ext] = m.external_id if m else None
        elif objective.level is ObjectiveLevel.LEARNING_EVENT and objective.learning_event_id:
            e = existing.events_by_id.get(objective.learning_event_id)
            owner_of[ext] = e.external_id if e else None
        else:
            owner_of[ext] = None
    current_owner = dict(owner_of)
    for row, values in rows:
        level = _LEVEL_OF[values["level"]]
        owner = values.get("owner")
        module_ext: str | None = None
        if level is ObjectiveLevel.PROGRAMME:
            if owner:
                plan.add(
                    sheet.title,
                    row.number,
                    "Owner (External ID)",
                    "A programme outcome has no owner.",
                )
                continue
        elif level is ObjectiveLevel.MODULE:
            if not owner or (owner not in sheet_modules and owner not in existing.modules):
                plan.add(
                    sheet.title,
                    row.number,
                    "Owner (External ID)",
                    "A module outcome needs the External ID of a module"
                    + (f" ('{owner}' is not one)." if owner else "."),
                )
                continue
            module_ext = owner
        else:
            if not owner or (owner not in sheet_sessions and owner not in existing.events):
                plan.add(
                    sheet.title,
                    row.number,
                    "Owner (External ID)",
                    "A session objective needs the External ID of a session"
                    + (f" ('{owner}' is not one)." if owner else "."),
                )
                continue
            module_ext = session_module.get(owner)
        known[values["external_id"]] = (level, module_ext)
        owner_of[values["external_id"]] = owner
    # Second pass: now every objective of the sheet is known, check the upward links.
    for row, values in rows:
        ext = values["external_id"]
        if ext not in known:
            continue
        level, module_ext = known[ext]
        owner = values.get("owner")
        found = existing.objectives.get(ext)
        if found is not None and (
            found.level is not level or current_owner.get(ext) != (owner or None)
        ):
            plan.add(
                sheet.title,
                row.number,
                "Level",
                "An import cannot change the level or the owner of an existing objective.",
            )
            continue
        bad = False
        broader = values.get("broader") or []
        for parent in broader:
            relation = known.get(parent)
            if relation is None:
                plan.add(
                    sheet.title,
                    row.number,
                    "Broader objectives (External IDs)",
                    f"No objective has the External ID '{parent}'.",
                )
                bad = True
                continue
            parent_level, parent_module = relation
            allowed = (
                level is ObjectiveLevel.MODULE and parent_level is ObjectiveLevel.PROGRAMME
            ) or (
                level is ObjectiveLevel.LEARNING_EVENT
                and (
                    parent_level is ObjectiveLevel.PROGRAMME
                    or (parent_level is ObjectiveLevel.MODULE and parent_module == module_ext)
                )
            )
            if not allowed:
                plan.add(
                    sheet.title,
                    row.number,
                    "Broader objectives (External IDs)",
                    f"'{parent}' is not a broader objective this one may link to.",
                )
                bad = True
        if bad:
            continue
        if "domain" in present:
            values["domain"] = ObjectiveDomain(values["domain"]) if values.get("domain") else None
        if "taxonomy_level" in present:
            label = values.get("taxonomy_level")
            ids = existing.levels.get(label.casefold(), []) if label else []
            if label and len(ids) != 1:
                plan.add(
                    sheet.title,
                    row.number,
                    "Taxonomy level",
                    f"The taxonomy level '{label}' matches more than one level; "
                    "set the default taxonomy scale.",
                )
                continue
            values["taxonomy_level_id"] = ids[0] if ids else None
        values["_level"] = level
        values["_owner"] = owner
        label = values["text"][:80]
        if found is None:
            plan.rows.append(RowPlan(sheet.key, row.number, ext, CREATE, label))
            plan.ops.append(Op(sheet.key, row.number, CREATE, ext, values))
            continue
        changed = differences(found, values, {"text": "Text", "domain": "Domain"})
        if "taxonomy_level" in present and found.taxonomy_level_id != values["taxonomy_level_id"]:
            changed.append("Taxonomy level")
        have = existing.parent_links.get(found.id, set())
        for parent in broader:
            target = existing.objectives.get(parent)
            if target is None or target.id not in have:
                changed.append("Broader objectives")
                break
        plan.rows.append(
            RowPlan(sheet.key, row.number, ext, UPDATE if changed else UNCHANGED, label, changed)
        )
        if changed:
            plan.ops.append(Op(sheet.key, row.number, UPDATE, ext, values, found))


# --- Applying -----------------------------------------------------------------------------

_RANK = {ObjectiveLevel.PROGRAMME: 0, ObjectiveLevel.MODULE: 1, ObjectiveLevel.LEARNING_EVENT: 2}


@dataclass
class Applied:
    summary: dict[str, dict[str, int]]
    objective_ids: list[uuid.UUID]
    job_id: uuid.UUID


async def apply(
    db: AsyncSession,
    version: CurriculumVersion,
    plan: Plan,
    existing: Existing,
    actor: User,
    *,
    can_approve: bool,
) -> Applied:
    """Carry out a plan that has no problems, in one transaction.

    Raises:
        ConflictError: If the plan has problems, or the data changed in a way that makes two items
            share a code or External ID (preview again).
    """
    if plan.problems:
        raise ConflictError("The file has problems; fix them and preview again.")
    phases = dict(existing.phases)
    modules = dict(existing.modules)
    events = dict(existing.events)
    objectives = dict(existing.objectives)
    touched: list[uuid.UUID] = []
    by_sheet: dict[str, list[Op]] = defaultdict(list)
    for op in plan.ops:
        by_sheet[op.sheet].append(op)
    actor_id = actor.id
    try:
        for op in by_sheet["phases"]:
            v = op.values
            if op.existing is None:
                phase = await curriculum_edit.create_phase(
                    db,
                    version,
                    name=v["name"],
                    kind=v.get("kind") or PhaseKind.YEAR,
                    created_by_id=actor_id,
                )
                phase.external_id = op.external_id
                phases[op.external_id] = phase
            else:
                phase_changes: dict[str, Any] = {
                    k: v[k] for k in ("name", "kind") if k in v and v[k] is not None
                }
                await curriculum_edit.update_phase(db, op.existing, version, phase_changes)

        for op in by_sheet["modules"]:
            v = op.values
            phase_id = None
            if v.get("phase"):
                phase_id = phases[v["phase"]].id
            if op.existing is None:
                module = await curriculum_edit.create_module(
                    db,
                    version,
                    ModuleFields(
                        code=v["code"],
                        name=v["name"],
                        phase_id=phase_id,
                        credits=v.get("credits"),
                        nqf_level=v.get("nqf_level"),
                        description=v.get("description") or "",
                        external_lms_ref=v.get("external_lms_ref"),
                    ),
                    created_by_id=actor_id,
                )
                module.external_id = op.external_id
                modules[op.external_id] = module
            else:
                module_changes: dict[str, Any] = {
                    k: v[k]
                    for k in (
                        "code",
                        "name",
                        "credits",
                        "nqf_level",
                        "description",
                        "external_lms_ref",
                    )
                    if k in v
                }
                if "phase" in v:
                    module_changes["phase_id"] = phase_id
                await curriculum_edit.update_module(db, op.existing, version, module_changes)
                if v.get("_adopt"):
                    op.existing.external_id = op.external_id
                    modules[op.external_id] = op.existing
        await db.flush()

        for op in by_sheet["sessions"]:
            v = op.values
            if op.existing is None:
                event = await curriculum_edit.create_event(
                    db,
                    modules[v["module"]],
                    version,
                    EventFields(
                        title=v["title"],
                        format_value_id=v.get("format_value_id"),
                        contact_minutes=v.get("contact_minutes") or 0,
                        self_study_minutes=v.get("self_study_minutes") or 0,
                        week=v.get("week"),
                        description=v.get("description") or "",
                        external_lms_ref=v.get("external_lms_ref"),
                    ),
                    created_by_id=actor_id,
                )
                event.external_id = op.external_id
                events[op.external_id] = event
            else:
                event_changes: dict[str, Any] = {
                    k: v[k]
                    for k in (
                        "title",
                        "contact_minutes",
                        "self_study_minutes",
                        "week",
                        "description",
                        "external_lms_ref",
                        "format_value_id",
                    )
                    if k in v
                }
                await curriculum_edit.update_event(db, op.existing, version, event_changes)
        await db.flush()

        ordered = sorted(
            by_sheet["objectives"],
            key=lambda o: (_RANK[o.values["_level"]], o.row),
        )
        for op in ordered:
            v = op.values
            level: ObjectiveLevel = v["_level"]
            parents = [objectives[p] for p in (v.get("broader") or []) if p in objectives]
            fields: dict[str, Any] = {}
            for key in ("text", "domain", "taxonomy_level_id"):
                if key in v:
                    fields[key] = v[key]
            if parents:
                fields["parent_ids"] = [p.id for p in parents]
            if op.existing is None:
                owner: Any
                if level is ObjectiveLevel.PROGRAMME:
                    owner = version
                elif level is ObjectiveLevel.MODULE:
                    owner = modules[v["_owner"]]
                else:
                    owner = events[v["_owner"]]
                objective = await curriculum_objectives.create_objective(
                    db,
                    owner,
                    version,
                    fields,
                    options=parents,
                    can_approve=can_approve,
                    created_by_id=actor_id,
                )
                objective.external_id = op.external_id
                objectives[op.external_id] = objective
            else:
                objective = await curriculum_objectives.update_objective(
                    db,
                    op.existing,
                    version,
                    fields,
                    options=parents,
                    can_approve=can_approve,
                    created_by_id=actor_id,
                )
            touched.append(objective.id)
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "The curriculum changed while the import was being applied (a code or External ID "
            "is now taken). Preview the file again."
        ) from exc

    summary = plan.counts()
    job = ImportJob(
        kind="curriculum",
        version_id=version.id,
        status="applied",
        summary=summary,
        created_by_id=actor_id,
    )
    db.add(job)
    await db.flush()
    return Applied(summary, touched, job.id)


def problem_counts(plan: Plan) -> Counter[str]:
    """How many problems each sheet has (for the preview's headline)."""
    return Counter(p.sheet or "file" for p in plan.problems)
