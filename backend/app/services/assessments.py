"""Minimal assessments of a module: assessments, their items and the objectives they assess.

Permissions are checked by the API before these functions run (curriculum.edit at the
module, as for sessions); these functions enforce the rules:

- Only draft versions can be changed (ADR 030).
- An assessment's method comes from an active assessment-method tag list.
- An item may assess the objectives of its own module and of that module's sessions
  (live ones); programme outcomes are reached through the objectives' upward links.
- New assessments and items go to the end of their parent. Deleting is a soft delete;
  links to objectives that are deleted later are ignored by reads.

All changes go through ORM objects so the audit log records them (ADR 017).
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assessment,
    AssessmentItem,
    AssessmentItemObjective,
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    TagValue,
)
from app.models.curriculum import ObjectiveLevel
from app.services.authorization import InvalidRequestError
from app.services.curriculum_edit import ensure_editable
from app.services.tagging import set_assessment_method


@dataclass
class ItemWithObjectives:
    item: AssessmentItem
    objective_ids: list[uuid.UUID]


@dataclass
class AssessmentWithItems:
    assessment: Assessment
    method_label: str | None
    items: list[ItemWithObjectives] = field(default_factory=list)


@dataclass(frozen=True)
class AssessmentFields:
    name: str
    method_value_id: uuid.UUID | None = None
    weight: Decimal | None = None
    timing: str = ""
    time_minutes: int = 0


async def module_assessments(db: AsyncSession, module_id: uuid.UUID) -> list[AssessmentWithItems]:
    """The module's live assessments with their live items and the live objectives
    each item assesses, in order."""
    rows = await db.execute(
        select(Assessment, TagValue.label)
        .outerjoin(
            TagValue,
            (TagValue.id == Assessment.method_value_id) & TagValue.deleted_at.is_(None),
        )
        .where(Assessment.module_id == module_id, Assessment.deleted_at.is_(None))
        .order_by(Assessment.position, Assessment.created_at)
    )
    found = {a.id: AssessmentWithItems(a, label) for a, label in rows}
    if not found:
        return []
    items = list(
        await db.scalars(
            select(AssessmentItem)
            .where(
                AssessmentItem.assessment_id.in_(list(found)),
                AssessmentItem.deleted_at.is_(None),
            )
            .order_by(AssessmentItem.position, AssessmentItem.created_at)
        )
    )
    links: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if items:
        link_rows = await db.execute(
            select(AssessmentItemObjective.item_id, AssessmentItemObjective.objective_id)
            .join(Objective, Objective.id == AssessmentItemObjective.objective_id)
            .where(
                AssessmentItemObjective.item_id.in_([i.id for i in items]),
                Objective.deleted_at.is_(None),
            )
            .order_by(Objective.position, Objective.created_at)
        )
        for item_id, objective_id in link_rows:
            links[item_id].append(objective_id)
    for item in items:
        found[item.assessment_id].items.append(ItemWithObjectives(item, links[item.id]))
    return list(found.values())


async def assessment_minutes(
    db: AsyncSession, module_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Learner minutes spent in the live assessments of each module."""
    if not module_ids:
        return {}
    rows = await db.execute(
        select(Assessment.module_id, func.coalesce(func.sum(Assessment.time_minutes), 0))
        .where(Assessment.module_id.in_(module_ids), Assessment.deleted_at.is_(None))
        .group_by(Assessment.module_id)
    )
    return {module_id: int(total) for module_id, total in rows}


async def linkable_objectives(
    db: AsyncSession, module: Module
) -> list[tuple[Objective, LearningEvent | None]]:
    """The live objectives an item of this module may assess (module outcomes first, then
    session objectives by session), each with its session, if any."""
    events = {
        e.id: e
        for e in await db.scalars(
            select(LearningEvent).where(
                LearningEvent.module_id == module.id, LearningEvent.deleted_at.is_(None)
            )
        )
    }
    owners = [Objective.module_id == module.id]
    if events:
        owners.append(Objective.learning_event_id.in_(list(events)))
    objectives = list(
        await db.scalars(
            select(Objective)
            .where(Objective.deleted_at.is_(None), or_(*owners))
            .order_by(Objective.position, Objective.created_at)
        )
    )
    result: list[tuple[Objective, LearningEvent | None]] = [
        (o, None) for o in objectives if o.level == ObjectiveLevel.MODULE
    ]
    session_level = [
        (o, events[o.learning_event_id])
        for o in objectives
        if o.level == ObjectiveLevel.LEARNING_EVENT and o.learning_event_id in events
    ]
    session_level.sort(key=lambda pair: (pair[1].position, pair[1].title, pair[0].position))
    return result + [(o, e) for o, e in session_level]


async def _next_position(db: AsyncSession, column: Any, *conditions: Any) -> int:
    highest = await db.scalar(select(func.max(column)).where(*conditions))
    return 0 if highest is None else int(highest) + 1


async def _set_method(
    db: AsyncSession, assessment: Assessment, method_value_id: uuid.UUID | None
) -> None:
    if assessment.method_value_id == method_value_id:
        return  # unchanged, even if the value has been retired since
    value = None
    if method_value_id is not None:
        value = await db.get(TagValue, method_value_id)
        if value is None:
            raise InvalidRequestError("Unknown assessment method.")
    await set_assessment_method(db, assessment, value)


async def create_assessment(
    db: AsyncSession,
    module: Module,
    version: CurriculumVersion,
    fields: AssessmentFields,
    *,
    created_by_id: uuid.UUID | None = None,
) -> Assessment:
    """Add an assessment at the end of a module.

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If the method is not from a usable assessment-method list.
    """
    ensure_editable(version)
    assessment = Assessment(
        module_id=module.id,
        name=fields.name,
        weight=fields.weight,
        timing=fields.timing,
        time_minutes=fields.time_minutes,
        position=await _next_position(
            db,
            Assessment.position,
            Assessment.module_id == module.id,
            Assessment.deleted_at.is_(None),
        ),
        created_by_id=created_by_id,
    )
    db.add(assessment)
    await db.flush()
    await _set_method(db, assessment, fields.method_value_id)
    return assessment


_ASSESSMENT_NOT_NULL = frozenset({"name", "timing", "time_minutes"})
_ASSESSMENT_FIELDS = _ASSESSMENT_NOT_NULL | {"weight"}


async def update_assessment(
    db: AsyncSession, assessment: Assessment, version: CurriculumVersion, changes: dict[str, Any]
) -> Assessment:
    """Change an assessment. ``changes`` holds only the fields sent.

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If a required field is cleared or the method is not usable.
    """
    ensure_editable(version)
    for key in _ASSESSMENT_NOT_NULL:
        if key in changes and changes[key] is None:
            raise InvalidRequestError(f"The assessment's {key} cannot be empty.")
    for key, value in changes.items():
        if key in _ASSESSMENT_FIELDS:
            setattr(assessment, key, value)
    if "method_value_id" in changes:
        await _set_method(db, assessment, changes["method_value_id"])
    await db.flush()
    return assessment


async def delete_assessment(
    db: AsyncSession, assessment: Assessment, version: CurriculumVersion
) -> None:
    """Soft-delete an assessment and its items."""
    ensure_editable(version)
    items = await db.scalars(
        select(AssessmentItem).where(
            AssessmentItem.assessment_id == assessment.id, AssessmentItem.deleted_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    for item in items:
        item.deleted_at = now
    assessment.deleted_at = now
    await db.flush()


async def _check_objectives(
    db: AsyncSession, module: Module, objective_ids: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    """The ids without repeats, if each is an objective this module's items may assess.

    Raises:
        InvalidRequestError: If one is not.
    """
    wanted = list(dict.fromkeys(objective_ids))
    if not wanted:
        return []
    allowed = {o.id for o, _event in await linkable_objectives(db, module)}
    if not set(wanted) <= allowed:
        raise InvalidRequestError(
            "An item can only assess objectives of its own module or of its sessions."
        )
    return wanted


async def _set_objectives(
    db: AsyncSession,
    item: AssessmentItem,
    wanted: list[uuid.UUID],
    created_by_id: uuid.UUID | None,
) -> None:
    """Make the item's links match ``wanted``; links to objectives that were deleted
    meanwhile are kept as they are (they are ignored by reads)."""
    existing = {
        link.objective_id: link
        for link in await db.scalars(
            select(AssessmentItemObjective).where(AssessmentItemObjective.item_id == item.id)
        )
    }
    live: set[uuid.UUID] = set()
    if existing:
        live = set(
            await db.scalars(
                select(Objective.id).where(
                    Objective.id.in_(list(existing)), Objective.deleted_at.is_(None)
                )
            )
        )
    for objective_id, link in existing.items():
        if objective_id in live and objective_id not in wanted:
            await db.delete(link)
    for objective_id in wanted:
        if objective_id not in existing:
            db.add(
                AssessmentItemObjective(
                    item_id=item.id, objective_id=objective_id, created_by_id=created_by_id
                )
            )
    await db.flush()


async def create_item(
    db: AsyncSession,
    assessment: Assessment,
    module: Module,
    version: CurriculumVersion,
    *,
    label: str,
    marks: Decimal | None,
    objective_ids: Sequence[uuid.UUID],
    created_by_id: uuid.UUID | None = None,
) -> AssessmentItem:
    """Add an item at the end of an assessment, assessing the given objectives.

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If an objective may not be assessed by this module's items.
    """
    ensure_editable(version)
    wanted = await _check_objectives(db, module, objective_ids)
    item = AssessmentItem(
        assessment_id=assessment.id,
        label=label,
        marks=marks,
        position=await _next_position(
            db,
            AssessmentItem.position,
            AssessmentItem.assessment_id == assessment.id,
            AssessmentItem.deleted_at.is_(None),
        ),
        created_by_id=created_by_id,
    )
    db.add(item)
    await db.flush()
    await _set_objectives(db, item, wanted, created_by_id)
    return item


async def update_item(
    db: AsyncSession,
    item: AssessmentItem,
    module: Module,
    version: CurriculumVersion,
    changes: dict[str, Any],
    *,
    updated_by_id: uuid.UUID | None = None,
) -> AssessmentItem:
    """Change an item. ``changes`` holds only the fields sent (``objective_ids`` replaces
    the objectives it assesses).

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If the label is cleared or an objective is not allowed.
    """
    ensure_editable(version)
    if "label" in changes and changes["label"] is None:
        raise InvalidRequestError("The item's label cannot be empty.")
    wanted = None
    if "objective_ids" in changes:
        wanted = await _check_objectives(db, module, changes["objective_ids"] or [])
    for key in ("label", "marks"):
        if key in changes:
            setattr(item, key, changes[key])
    await db.flush()
    if wanted is not None:
        await _set_objectives(db, item, wanted, updated_by_id)
    return item


async def delete_item(db: AsyncSession, item: AssessmentItem, version: CurriculumVersion) -> None:
    """Soft-delete an item."""
    ensure_editable(version)
    item.soft_delete()
    await db.flush()
