"""Copying curriculum items with their children, inside one curriculum version.

A copy is placed directly after the item it was copied from (a module copied to
another phase goes to the end of that phase). What a copy takes along (ADR 029):

- a phase: its live modules, each with a new code given by the caller;
- a module: its live sessions and the objectives of the module and its sessions;
- a session: its objectives;
- the items' fields, except the LMS reference (a copy is not the same LMS course);
- objectives with their text, domain, taxonomy level, quality data and status, and
  their upward links: a link to an objective that is copied too points to the copy,
  other links keep their parent;
- a module's assessments with their items and the objectives the items assess (links
  point to the copied objectives);
- taggings of every copied item, direct and inherited; an inherited tagging whose
  source is copied too comes from the copy.

Not copied: framework mappings (reviewed decisions about one objective), role
assignments, deleted rows and links from objectives outside the copy.

Copying a whole version forward to a new academic year (``curriculum_versions``)
reuses these helpers with ``Copies.version_id`` set: the rows go to the new
version, programme outcomes come along, and every copy records its original in
``based_on_id`` (ADR 030).

Permissions are checked by the API; all rows are added through the ORM so the
audit log records them (ADR 017).
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    Tagging,
)
from app.models.curriculum import ObjectiveLevel
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum_edit import (
    ensure_editable,
    event_siblings,
    module_siblings,
    phase_siblings,
)


@dataclass
class Copies:
    """Old id to copied row, for remapping links and taggings."""

    actor_id: uuid.UUID | None
    # Copy forward: the version copied from and the new version (None: same version).
    source_version_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    modules: dict[uuid.UUID, Module] = field(default_factory=dict)
    events: dict[uuid.UUID, LearningEvent] = field(default_factory=dict)
    objectives: dict[uuid.UUID, Objective] = field(default_factory=dict)
    assessment_items: dict[uuid.UUID, AssessmentItem] = field(default_factory=dict)

    @property
    def forward(self) -> bool:
        return self.version_id is not None

    def based_on(self, original_id: uuid.UUID) -> uuid.UUID | None:
        """The original's id, recorded on copies made by copy forward only."""
        return original_id if self.forward else None


def _insert_after(
    siblings: Sequence[Phase | Module | LearningEvent], original_id: uuid.UUID
) -> int:
    """Make room right after the original and return the copy's position."""
    index = next(i for i, sibling in enumerate(siblings) if sibling.id == original_id)
    for offset, sibling in enumerate(siblings):
        wanted = offset if offset <= index else offset + 1
        if sibling.position != wanted:
            sibling.position = wanted
    return index + 1


async def _check_codes(db: AsyncSession, version_id: uuid.UUID, codes: Iterable[str]) -> None:
    """Raises:
    ConflictError: If a code is used twice or already used in the version (ignoring case).
    """
    seen: set[str] = set()
    for code in codes:
        if code.lower() in seen:
            raise ConflictError(f"The code {code} is given to more than one module.")
        seen.add(code.lower())
    if not seen:
        return
    taken = await db.scalar(
        select(Module.code).where(
            Module.version_id == version_id,
            Module.deleted_at.is_(None),
            func.lower(Module.code).in_(sorted(seen)),
        )
    )
    if taken is not None:
        raise ConflictError(f"Another module in this version already has the code {taken}.")


def _copy_event(
    event: LearningEvent, module_id: uuid.UUID, position: int, copies: Copies, title: str
) -> LearningEvent:
    copy = LearningEvent(
        module_id=module_id,
        title=title,
        format_value_id=event.format_value_id,
        contact_minutes=event.contact_minutes,
        self_study_minutes=event.self_study_minutes,
        position=position,
        week=event.week,
        description=event.description,
        external_lms_ref=None,
        external_id=event.external_id if copies.forward else None,
        based_on_id=copies.based_on(event.id),
        created_by_id=copies.actor_id,
    )
    copies.events[event.id] = copy
    return copy


async def copy_module_rows(
    db: AsyncSession,
    module: Module,
    *,
    code: str,
    name: str,
    phase_id: uuid.UUID | None,
    position: int,
    copies: Copies,
) -> Module:
    copy = Module(
        version_id=copies.version_id or module.version_id,
        phase_id=phase_id,
        code=code,
        name=name,
        credits=module.credits,
        nqf_level=module.nqf_level,
        description=module.description,
        external_lms_ref=None,
        external_id=module.external_id if copies.forward else None,
        position=position,
        based_on_id=copies.based_on(module.id),
        created_by_id=copies.actor_id,
    )
    db.add(copy)
    await db.flush()
    copies.modules[module.id] = copy
    for event in await event_siblings(db, module.id):
        db.add(_copy_event(event, copy.id, event.position, copies, event.title))
    await _copy_assessments(db, module, copy, copies)
    return copy


async def _copy_assessments(db: AsyncSession, module: Module, copy: Module, copies: Copies) -> None:
    """Copy the module's live assessments and items (their objective links come later,
    with the objectives)."""
    assessments = list(
        await db.scalars(
            select(Assessment)
            .where(Assessment.module_id == module.id, Assessment.deleted_at.is_(None))
            .order_by(Assessment.position, Assessment.created_at)
        )
    )
    if not assessments:
        return
    new_assessments: dict[uuid.UUID, Assessment] = {}
    for assessment in assessments:
        new_assessments[assessment.id] = Assessment(
            module_id=copy.id,
            name=assessment.name,
            method_value_id=assessment.method_value_id,
            weight=assessment.weight,
            timing=assessment.timing,
            time_minutes=assessment.time_minutes,
            position=assessment.position,
            based_on_id=copies.based_on(assessment.id),
            created_by_id=copies.actor_id,
        )
        db.add(new_assessments[assessment.id])
    await db.flush()
    items = await db.scalars(
        select(AssessmentItem)
        .where(
            AssessmentItem.assessment_id.in_(list(new_assessments)),
            AssessmentItem.deleted_at.is_(None),
        )
        .order_by(AssessmentItem.position, AssessmentItem.created_at)
    )
    for item in items:
        new_item = AssessmentItem(
            assessment_id=new_assessments[item.assessment_id].id,
            label=item.label,
            marks=item.marks,
            position=item.position,
            based_on_id=copies.based_on(item.id),
            created_by_id=copies.actor_id,
        )
        db.add(new_item)
        copies.assessment_items[item.id] = new_item
    await db.flush()


async def _copy_item_links(db: AsyncSession, copies: Copies) -> None:
    """Link the copied items to the copies of the objectives they assess."""
    if not copies.assessment_items or not copies.objectives:
        return
    links = await db.scalars(
        select(AssessmentItemObjective).where(
            AssessmentItemObjective.item_id.in_(list(copies.assessment_items)),
            AssessmentItemObjective.objective_id.in_(list(copies.objectives)),
        )
    )
    for link in links:
        db.add(
            AssessmentItemObjective(
                item_id=copies.assessment_items[link.item_id].id,
                objective_id=copies.objectives[link.objective_id].id,
                created_by_id=copies.actor_id,
            )
        )
    await db.flush()


async def _copy_objectives(db: AsyncSession, copies: Copies) -> None:
    """Copy the live objectives of the copied modules and sessions (and, for copy
    forward, the programme outcomes), then their links."""
    await db.flush()
    owners = []
    if copies.source_version_id is not None:
        owners.append(
            and_(
                Objective.version_id == copies.source_version_id,
                Objective.level == ObjectiveLevel.PROGRAMME,
            )
        )
    if copies.modules:
        owners.append(Objective.module_id.in_(list(copies.modules)))
    if copies.events:
        owners.append(Objective.learning_event_id.in_(list(copies.events)))
    if not owners:
        return
    originals = list(
        await db.scalars(
            select(Objective)
            .where(Objective.deleted_at.is_(None), or_(*owners))
            .order_by(Objective.position, Objective.created_at)
        )
    )
    for objective in originals:
        module = copies.modules.get(objective.module_id) if objective.module_id else None
        event = (
            copies.events.get(objective.learning_event_id) if objective.learning_event_id else None
        )
        copy = Objective(
            version_id=copies.version_id or objective.version_id,
            level=objective.level,
            module_id=module.id if module else None,
            learning_event_id=event.id if event else None,
            text=objective.text,
            domain=objective.domain,
            taxonomy_level_id=objective.taxonomy_level_id,
            detected_verb=objective.detected_verb,
            quality_flags=list(objective.quality_flags),
            status=objective.status,
            external_id=objective.external_id if copies.forward else None,
            position=objective.position,
            based_on_id=copies.based_on(objective.id),
            created_by_id=copies.actor_id,
        )
        db.add(copy)
        copies.objectives[objective.id] = copy
    await db.flush()
    if not copies.objectives:
        return

    links = await db.execute(
        select(ObjectiveLink)
        .join(Objective, Objective.id == ObjectiveLink.parent_id)
        .where(ObjectiveLink.child_id.in_(list(copies.objectives)), Objective.deleted_at.is_(None))
    )
    for link in links.scalars():
        parent = copies.objectives.get(link.parent_id)
        if parent is None and copies.forward:
            continue  # links never leave a version
        db.add(
            ObjectiveLink(
                child_id=copies.objectives[link.child_id].id,
                parent_id=parent.id if parent else link.parent_id,
                created_by_id=copies.actor_id,
            )
        )
    await db.flush()


async def _copy_taggings(db: AsyncSession, copies: Copies) -> None:
    """Copy the taggings of every copied item; inherited ones from a copied source
    come from the source's copy."""
    columns = (
        ("module_id", copies.modules),
        ("learning_event_id", copies.events),
        ("objective_id", copies.objectives),
    )
    conditions = [getattr(Tagging, column).in_(list(rows)) for column, rows in columns if rows]
    if not conditions:
        return
    pending = list(
        await db.scalars(select(Tagging).where(or_(*conditions)).order_by(Tagging.created_at))
    )
    copied: dict[uuid.UUID, Tagging] = {}
    added: list[tuple[uuid.UUID, Tagging]] = []
    in_copy = {tagging.id for tagging in pending}
    # A source copied too must be copied (and flushed, for its id) first; sources form
    # chains, never cycles.
    while pending:
        waiting = []
        for tagging in pending:
            source = tagging.inherited_from_id
            if source in in_copy and source not in copied:
                waiting.append(tagging)
                continue
            new = Tagging(
                tag_value_id=tagging.tag_value_id,
                inherited_from_id=copied[source].id if source in copied else source,
                created_by_id=copies.actor_id,
            )
            for column, rows in columns:
                old = getattr(tagging, column)
                if old is not None:
                    setattr(new, column, rows[old].id)
            db.add(new)
            added.append((tagging.id, new))
        await db.flush()
        copied.update(added)
        added.clear()
        if len(waiting) == len(pending):  # pragma: no cover - would need a cycle
            raise InvalidRequestError("The tags of this item cannot be copied.")
        pending = waiting


async def copy_children(db: AsyncSession, copies: Copies) -> None:
    await _copy_objectives(db, copies)
    await _copy_item_links(db, copies)
    await _copy_taggings(db, copies)


async def phase_modules(db: AsyncSession, phase: Phase) -> list[Module]:
    """The live modules of a phase, in order."""
    return list(
        await db.scalars(
            select(Module)
            .where(Module.phase_id == phase.id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.code)
        )
    )


# --- Public functions ---------------------------------------------------------------


async def copy_event(
    db: AsyncSession,
    event: LearningEvent,
    version: CurriculumVersion,
    *,
    title: str,
    created_by_id: uuid.UUID | None = None,
) -> LearningEvent:
    """Copy a session, with its objectives, right after it in the same module."""
    ensure_editable(version)
    copies = Copies(created_by_id)
    position = _insert_after(await event_siblings(db, event.module_id), event.id)
    copy = _copy_event(event, event.module_id, position, copies, title)
    db.add(copy)
    await copy_children(db, copies)
    return copy


async def copy_module(
    db: AsyncSession,
    module: Module,
    version: CurriculumVersion,
    *,
    code: str,
    name: str,
    to_other_phase: bool = False,
    phase_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
) -> Module:
    """Copy a module with its sessions and all their objectives.

    The copy goes right after the module or, with ``to_other_phase``, to the end of
    ``phase_id`` (None: across phases).

    Raises:
        ConflictError: If the version is read-only or the code is taken.
        InvalidRequestError: If the phase is not a live phase of the version.
    """
    ensure_editable(version)
    await _check_codes(db, version.id, [code])
    if not to_other_phase or phase_id == module.phase_id:
        target_phase = module.phase_id
        position = _insert_after(await module_siblings(db, module), module.id)
    else:
        target_phase = phase_id
        if target_phase is not None:
            found = await db.scalar(
                select(Phase.id).where(
                    Phase.id == target_phase,
                    Phase.version_id == version.id,
                    Phase.deleted_at.is_(None),
                )
            )
            if found is None:
                raise InvalidRequestError(
                    "The phase must be a phase of the same curriculum version."
                )
        highest = await db.scalar(
            select(func.max(Module.position)).where(
                Module.version_id == version.id, Module.deleted_at.is_(None)
            )
        )
        position = 0 if highest is None else highest + 1
    copies = Copies(created_by_id)
    copy = await copy_module_rows(
        db,
        module,
        code=code,
        name=name,
        phase_id=target_phase,
        position=position,
        copies=copies,
    )
    await copy_children(db, copies)
    return copy


async def copy_phase(
    db: AsyncSession,
    phase: Phase,
    version: CurriculumVersion,
    *,
    name: str,
    module_codes: dict[uuid.UUID, str],
    created_by_id: uuid.UUID | None = None,
) -> Phase:
    """Copy a phase, right after it, with all its modules (each under a new code).

    Raises:
        ConflictError: If the version is read-only or a code is taken.
        InvalidRequestError: If ``module_codes`` does not give exactly one code for each
            of the phase's modules.
    """
    ensure_editable(version)
    modules = await phase_modules(db, phase)
    if set(module_codes) != {module.id for module in modules}:
        raise InvalidRequestError("Give one new code for each module of the phase.")
    await _check_codes(db, version.id, module_codes.values())

    position = _insert_after(await phase_siblings(db, version.id), phase.id)
    copy = Phase(
        version_id=version.id,
        name=name,
        kind=phase.kind,
        position=position,
        created_by_id=created_by_id,
    )
    db.add(copy)
    await db.flush()

    highest = await db.scalar(
        select(func.max(Module.position)).where(
            Module.version_id == version.id, Module.deleted_at.is_(None)
        )
    )
    start = 0 if highest is None else highest + 1
    copies = Copies(created_by_id)
    for offset, module in enumerate(modules):
        await copy_module_rows(
            db,
            module,
            code=module_codes[module.id],
            name=module.name,
            phase_id=copy.id,
            position=start + offset,
            copies=copies,
        )
    await copy_children(db, copies)
    return copy
