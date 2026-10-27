"""Editing objectives: programme outcomes, module outcomes and session objectives.

Permissions are checked by the API before these functions run (ADR 012, ADR 031).
The rules enforced here:

- Only objectives of draft versions can be changed (ADR 030).
- The level follows from the owner; the objective records the owner's version.
- Upward links go from a narrower to a broader objective of the same version, and a
  session objective links to outcomes of its own module or to programme outcomes
  (``link_objectives`` in ``app.services.curriculum``). Which broader objectives a
  person may *choose* depends on what they can see (``parent_options``); links to
  objectives they cannot see are left as they are when they change the others.
- Anyone who may edit sets draft or ready for review; approved and retired need
  ``objectives.approve`` (``can_approve``, decided by the API from the objective's scope).
  Changing the text of an approved objective without that permission sends it back to
  ready for review (ADR 032).
- Changing the text flags the objective's accepted mapping links for re-check.
- Deleting is a soft delete; links, mappings and taggings stay and are ignored by reads.

All changes go through ORM objects so the audit log records them (ADR 017).
"""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    TaxonomyLevel,
)
from app.models.curriculum import EDITOR_OBJECTIVE_STATUSES, ObjectiveLevel, ObjectiveStatus
from app.services.authorization import AuthorizationError, InvalidRequestError
from app.services.curriculum import ObjectiveOwner, add_objective, link_objectives
from app.services.curriculum_edit import ensure_editable
from app.services.curriculum_read import VersionView
from app.services.mapping import flag_for_recheck
from app.services.mapping_live import restore_links, soft_delete_links


async def parent_options(
    db: AsyncSession,
    view: VersionView,
    level: ObjectiveLevel,
    version_id: uuid.UUID,
    module_id: uuid.UUID | None,
) -> list[Objective]:
    """The broader objectives an objective at ``level`` (owned in ``module_id``) may link
    to: the programme outcomes, and for a session objective its module's outcomes, for
    anyone who sees the objective's item. Programme outcomes first, then module outcomes,
    in order."""
    wanted = []
    # Read-only exception to ADR 027 (ADR 032): whoever sees any part of the version, even
    # a single session, sees the programme outcomes and their own module's outcomes, so
    # they can choose upward links. Nothing else above their scope is shown.
    if level != ObjectiveLevel.PROGRAMME and view.visible:
        wanted.append(Objective.level == ObjectiveLevel.PROGRAMME)
    if (
        level == ObjectiveLevel.LEARNING_EVENT
        and module_id
        and (view.shows_module(module_id) or module_id in view.events)
    ):
        wanted.append(
            (Objective.level == ObjectiveLevel.MODULE) & (Objective.module_id == module_id)
        )
    if not wanted:
        return []
    found = await db.scalars(
        select(Objective)
        .where(
            Objective.version_id == version_id,
            Objective.deleted_at.is_(None),
            or_(*wanted),
        )
        .order_by(Objective.position, Objective.created_at)
    )
    rank = {ObjectiveLevel.PROGRAMME: 0, ObjectiveLevel.MODULE: 1}
    return sorted(found, key=lambda o: rank[o.level])


def _check_status(status: ObjectiveStatus, can_approve: bool) -> None:
    if status not in EDITOR_OBJECTIVE_STATUSES and not can_approve:
        raise AuthorizationError(
            "Only a module coordinator or above can approve or retire an objective."
        )


async def _check_taxonomy_level(db: AsyncSession, level_id: uuid.UUID | None) -> None:
    if level_id is not None and await db.get(TaxonomyLevel, level_id) is None:
        raise InvalidRequestError("Unknown taxonomy level.")


async def _sync_parents(
    db: AsyncSession,
    child: Objective,
    wanted: list[uuid.UUID],
    options: list[Objective],
    created_by_id: uuid.UUID | None,
) -> None:
    """Make the child's links to the ``options`` match ``wanted``; others are untouched."""
    by_id = {option.id: option for option in options}
    unknown = [parent_id for parent_id in wanted if parent_id not in by_id]
    if unknown:
        raise InvalidRequestError("Choose upward links from the objectives offered.")
    wanted_ids = set(wanted)
    existing = list(
        await db.scalars(select(ObjectiveLink).where(ObjectiveLink.child_id == child.id))
    )
    linked = set()
    for link in existing:
        if link.parent_id in by_id and link.parent_id not in wanted_ids:
            await db.delete(link)
        else:
            linked.add(link.parent_id)
    for parent_id in dict.fromkeys(wanted):
        if parent_id not in linked:
            await link_objectives(db, child, by_id[parent_id], created_by_id=created_by_id)
    await db.flush()


async def create_objective(
    db: AsyncSession,
    owner: ObjectiveOwner,
    version: CurriculumVersion,
    fields: dict[str, Any],
    *,
    options: list[Objective],
    can_approve: bool = False,
    created_by_id: uuid.UUID | None = None,
) -> Objective:
    """Add an objective at the end of its owner's list.

    ``fields`` holds ``text`` and optionally ``domain``, ``taxonomy_level_id``,
    ``status`` and ``parent_ids``; ``options`` are the broader objectives on offer.

    Raises:
        ConflictError: If the version is read-only.
        AuthorizationError: If the status needs approval rights the user lacks.
        InvalidRequestError: If the text is blank, a level or link is not valid.
    """
    ensure_editable(version)
    if fields.get("status") is not None:
        _check_status(fields["status"], can_approve)
    await _check_taxonomy_level(db, fields.get("taxonomy_level_id"))
    if isinstance(owner, CurriculumVersion):
        conditions = [Objective.level == ObjectiveLevel.PROGRAMME]
    elif isinstance(owner, Module):
        conditions = [Objective.module_id == owner.id, Objective.level == ObjectiveLevel.MODULE]
    else:
        conditions = [Objective.learning_event_id == owner.id]
    highest = await db.scalar(
        select(Objective.position)
        .where(Objective.version_id == version.id, Objective.deleted_at.is_(None), *conditions)
        .order_by(Objective.position.desc())
        .limit(1)
    )
    objective = await add_objective(
        db,
        owner,
        fields["text"],
        domain=fields.get("domain"),
        position=0 if highest is None else highest + 1,
        created_by_id=created_by_id,
    )
    objective.taxonomy_level_id = fields.get("taxonomy_level_id")
    if fields.get("status") is not None:
        objective.status = fields["status"]
    await _sync_parents(db, objective, fields.get("parent_ids", []), options, created_by_id)
    await db.flush()
    return objective


_REQUIRED = frozenset({"text", "status"})


async def update_objective(
    db: AsyncSession,
    objective: Objective,
    version: CurriculumVersion,
    changes: dict[str, Any],
    *,
    options: list[Objective],
    can_approve: bool = False,
    created_by_id: uuid.UUID | None = None,
) -> Objective:
    """Change an objective. ``changes`` holds only the fields sent (``null`` clears the
    domain and taxonomy level); ``parent_ids`` replaces the links to the objectives on
    offer.

    Raises:
        ConflictError: If the version is read-only.
        AuthorizationError: If the status or text change needs approval rights the user lacks.
        InvalidRequestError: If text or status is cleared, or a level or link is not valid.
    """
    ensure_editable(version)
    for key in _REQUIRED:
        if key in changes and changes[key] is None:
            raise InvalidRequestError(f"The objective's {key} cannot be empty.")
    old_status = objective.status
    new_status = changes.get("status", old_status)
    if new_status != old_status:
        # Leaving approved or retired is as much an approval decision as entering them.
        _check_status(new_status, can_approve)
        _check_status(old_status, can_approve)
    text_changed = "text" in changes and changes["text"] != objective.text
    if text_changed and not can_approve and old_status not in EDITOR_OBJECTIVE_STATUSES:
        if old_status == ObjectiveStatus.RETIRED:
            raise AuthorizationError("Only a module coordinator or above can change a retired one.")
        changes = {**changes, "status": ObjectiveStatus.READY_FOR_REVIEW}
    if (
        "taxonomy_level_id" in changes
        and changes["taxonomy_level_id"] != objective.taxonomy_level_id
    ):
        await _check_taxonomy_level(db, changes["taxonomy_level_id"])
    for key in ("text", "domain", "taxonomy_level_id", "status"):
        if key in changes:
            setattr(objective, key, changes[key])
    if "parent_ids" in changes:
        await _sync_parents(db, objective, changes["parent_ids"] or [], options, created_by_id)
    if text_changed:
        await flag_for_recheck(db, objective)
    await db.flush()
    return objective


async def delete_objective(
    db: AsyncSession, objective: Objective, version: CurriculumVersion
) -> None:
    """Soft-delete an objective together with its mapping links (ADR 043)."""
    ensure_editable(version)
    objective.soft_delete()
    assert objective.deleted_at is not None
    await soft_delete_links(db, [objective.id], at=objective.deleted_at)
    await db.flush()


async def restore_objective(
    db: AsyncSession, objective: Objective, version: CurriculumVersion
) -> None:
    """Undelete an objective and the mapping links that were deleted with it (ADR 043).

    Links a person removed earlier are gone for good, and links deleted at another time stay
    deleted. No endpoint calls this yet.
    """
    ensure_editable(version)
    await restore_links(db, objective)
    objective.restore()
    await db.flush()


async def owner_module_id(db: AsyncSession, objective: Objective) -> uuid.UUID | None:
    """The module an objective belongs to (its own, or its session's); none for outcomes
    of the programme."""
    if objective.module_id is not None:
        return objective.module_id
    if objective.learning_event_id is not None:
        return await db.scalar(
            select(LearningEvent.module_id).where(LearningEvent.id == objective.learning_event_id)
        )
    return None
