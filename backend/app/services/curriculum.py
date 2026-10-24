"""Curriculum rules that the database alone does not enforce."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, LearningEvent, Module, Objective, ObjectiveLink
from app.models.curriculum import (
    OBJECTIVE_LEVEL_RANK,
    ObjectiveDomain,
    ObjectiveLevel,
)
from app.services.authorization import ConflictError, InvalidRequestError

ObjectiveOwner = CurriculumVersion | Module | LearningEvent


async def add_objective(
    db: AsyncSession,
    owner: ObjectiveOwner,
    text: str,
    *,
    domain: ObjectiveDomain | None = None,
    position: int = 0,
    created_by_id: uuid.UUID | None = None,
) -> Objective:
    """Add an objective to a version (programme outcome), module or learning event.

    The level follows from the owner, and the objective records the owner's
    curriculum version.

    Raises:
        InvalidRequestError: If the owner is deleted or the text is blank.
    """
    if getattr(owner, "deleted_at", None) is not None:
        raise InvalidRequestError("Cannot add objectives to a deleted item.")
    if not text.strip():
        raise InvalidRequestError("Objective text cannot be empty.")

    objective = Objective(
        text=text.strip(),
        domain=domain,
        position=position,
        created_by_id=created_by_id,
    )
    if isinstance(owner, CurriculumVersion):
        objective.level = ObjectiveLevel.PROGRAMME
        objective.version_id = owner.id
    elif isinstance(owner, Module):
        objective.level = ObjectiveLevel.MODULE
        objective.version_id = owner.version_id
        objective.module_id = owner.id
    else:
        version_id = await db.scalar(select(Module.version_id).where(Module.id == owner.module_id))
        if version_id is None:
            raise InvalidRequestError("The learning event's module does not exist.")
        objective.level = ObjectiveLevel.LEARNING_EVENT
        objective.version_id = version_id
        objective.learning_event_id = owner.id
    db.add(objective)
    await db.flush()
    return objective


async def link_objectives(
    db: AsyncSession,
    child: Objective,
    parent: Objective,
    *,
    created_by_id: uuid.UUID | None = None,
) -> ObjectiveLink:
    """Link a narrower objective upward to a broader one it contributes to.

    Rules: both live and in the same curriculum version; the parent is at a
    broader level; a session objective links to outcomes of its own module
    (or to programme outcomes).

    Raises:
        InvalidRequestError: If a rule is broken.
        ConflictError: If the link already exists.
    """
    if child.is_deleted or parent.is_deleted:
        raise InvalidRequestError("Cannot link deleted objectives.")
    if child.version_id != parent.version_id:
        raise InvalidRequestError("Objectives must be in the same curriculum version.")
    if OBJECTIVE_LEVEL_RANK[parent.level] <= OBJECTIVE_LEVEL_RANK[child.level]:
        raise InvalidRequestError(
            f"A {child.level.value} objective can only link to a broader level."
        )
    if child.level == ObjectiveLevel.LEARNING_EVENT and parent.level == ObjectiveLevel.MODULE:
        event_module = await db.scalar(
            select(LearningEvent.module_id).where(LearningEvent.id == child.learning_event_id)
        )
        if event_module != parent.module_id:
            raise InvalidRequestError("A session objective links to its own module's outcomes.")

    exists = await db.scalar(
        select(ObjectiveLink.id).where(
            ObjectiveLink.child_id == child.id, ObjectiveLink.parent_id == parent.id
        )
    )
    if exists:
        raise ConflictError("These objectives are already linked.")

    link = ObjectiveLink(child_id=child.id, parent_id=parent.id, created_by_id=created_by_id)
    db.add(link)
    await db.flush()
    return link
