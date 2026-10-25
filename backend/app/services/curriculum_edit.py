"""Editing the curriculum structure: phases, modules and learning events.

Permissions are checked by the API before these functions run (ADR 012); these
functions enforce the structural rules:

- Archived versions are read-only. Until publishing rules arrive (Slice 1.5),
  draft and published versions can both be edited.
- A module's phase must be a live phase of the same version (or none, for a
  longitudinal module); module codes are unique among a version's live modules.
- New items go to the end of their parent. Moving an item changes its place among
  its siblings only (phases in the version, modules in their phase or among the
  modules across phases, sessions in their module).
- Deleting is a soft delete. A phase that still holds modules cannot be deleted;
  deleting a module also removes its sessions and all their objectives, and
  deleting a session removes its objectives, with one timestamp so they can be
  restored together.

All changes go through ORM objects so the audit log records them (ADR 017).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, LearningEvent, Module, Objective, Phase, TagValue
from app.models.curriculum import PhaseKind, VersionStatus
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.tagging import set_teaching_format

# Statuses whose structure can be edited. Slice 1.5 makes published versions read-only.
EDITABLE_STATUSES = frozenset({VersionStatus.DRAFT, VersionStatus.PUBLISHED})


def is_editable(version: CurriculumVersion) -> bool:
    """Whether the version's structure may be changed at all."""
    return version.deleted_at is None and version.status in EDITABLE_STATUSES


def ensure_editable(version: CurriculumVersion) -> None:
    """Raises:
    ConflictError: If the version is read-only (archived or deleted).
    """
    if not is_editable(version):
        raise ConflictError("This curriculum version is read-only.")


def _place(
    siblings: Sequence[Phase | Module | LearningEvent],
    item: Phase | Module | LearningEvent,
    position: int,
) -> None:
    """Put ``item`` at index ``position`` among ``siblings`` (in their current order)
    and number them all from 0, changing only the rows whose position differs.

    Raises:
        InvalidRequestError: If the position is outside the list.
    """
    if not 0 <= position < len(siblings):
        raise InvalidRequestError(f"The position must be from 0 to {len(siblings) - 1}.")
    ordered: list[Phase | Module | LearningEvent] = [
        sibling for sibling in siblings if sibling.id != item.id
    ]
    ordered.insert(position, item)
    for index, sibling in enumerate(ordered):
        if sibling.position != index:
            sibling.position = index


async def module_siblings(db: AsyncSession, module: Module) -> list[Module]:
    """The live modules shown in the same group as ``module``, in order: its phase, or
    the modules across phases (including those whose phase was deleted)."""
    live_phases = set(
        await db.scalars(
            select(Phase.id).where(
                Phase.version_id == module.version_id, Phase.deleted_at.is_(None)
            )
        )
    )

    def group(candidate: Module) -> uuid.UUID | None:
        return candidate.phase_id if candidate.phase_id in live_phases else None

    modules = await db.scalars(
        select(Module)
        .where(Module.version_id == module.version_id, Module.deleted_at.is_(None))
        .order_by(Module.position, Module.code)
    )
    return [candidate for candidate in modules if group(candidate) == group(module)]


async def phase_siblings(db: AsyncSession, version_id: uuid.UUID) -> list[Phase]:
    """The version's live phases, in order."""
    return list(
        await db.scalars(
            select(Phase)
            .where(Phase.version_id == version_id, Phase.deleted_at.is_(None))
            .order_by(Phase.position, Phase.name)
        )
    )


async def event_siblings(db: AsyncSession, module_id: uuid.UUID) -> list[LearningEvent]:
    """The module's live sessions, in order."""
    return list(
        await db.scalars(
            select(LearningEvent)
            .where(LearningEvent.module_id == module_id, LearningEvent.deleted_at.is_(None))
            .order_by(LearningEvent.position, LearningEvent.title)
        )
    )


async def _next_position(db: AsyncSession, column: Any, *conditions: Any) -> int:
    highest = await db.scalar(select(func.max(column)).where(*conditions))
    return 0 if highest is None else int(highest) + 1


# --- Phases -------------------------------------------------------------------------


async def create_phase(
    db: AsyncSession,
    version: CurriculumVersion,
    *,
    name: str,
    kind: PhaseKind,
    created_by_id: uuid.UUID | None = None,
) -> Phase:
    """Add a phase at the end of the version."""
    ensure_editable(version)
    phase = Phase(
        version_id=version.id,
        name=name,
        kind=kind,
        position=await _next_position(
            db, Phase.position, Phase.version_id == version.id, Phase.deleted_at.is_(None)
        ),
        created_by_id=created_by_id,
    )
    db.add(phase)
    await db.flush()
    return phase


async def update_phase(
    db: AsyncSession, phase: Phase, version: CurriculumVersion, changes: dict[str, Any]
) -> Phase:
    """Change a phase's name or kind."""
    ensure_editable(version)
    for key in ("name", "kind"):
        if key in changes and changes[key] is not None:
            setattr(phase, key, changes[key])
    await db.flush()
    return phase


async def move_phase(
    db: AsyncSession, phase: Phase, version: CurriculumVersion, position: int
) -> Phase:
    """Move a phase to ``position`` (from 0) among the version's phases."""
    ensure_editable(version)
    _place(await phase_siblings(db, version.id), phase, position)
    await db.flush()
    return phase


async def delete_phase(db: AsyncSession, phase: Phase, version: CurriculumVersion) -> None:
    """Soft-delete an empty phase.

    Raises:
        ConflictError: If the phase still holds modules.
    """
    ensure_editable(version)
    holds = await db.scalar(
        select(func.count(Module.id)).where(
            Module.phase_id == phase.id, Module.deleted_at.is_(None)
        )
    )
    if holds:
        raise ConflictError("Move or delete the phase's modules first.")
    phase.soft_delete()
    await db.flush()


# --- Modules ------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleFields:
    code: str
    name: str
    phase_id: uuid.UUID | None = None
    credits: Decimal | None = None
    nqf_level: int | None = None
    description: str = ""
    external_lms_ref: str | None = None


async def _check_phase(
    db: AsyncSession, version: CurriculumVersion, phase_id: uuid.UUID | None
) -> None:
    if phase_id is None:
        return
    found = await db.scalar(
        select(Phase.id).where(
            Phase.id == phase_id, Phase.version_id == version.id, Phase.deleted_at.is_(None)
        )
    )
    if found is None:
        raise InvalidRequestError("The phase must be a phase of the same curriculum version.")


async def _check_code(
    db: AsyncSession, version_id: uuid.UUID, code: str, module_id: uuid.UUID | None = None
) -> None:
    query = select(Module.id).where(
        Module.version_id == version_id,
        Module.deleted_at.is_(None),
        func.lower(Module.code) == code.lower(),
    )
    if module_id is not None:
        query = query.where(Module.id != module_id)
    if await db.scalar(query) is not None:
        raise ConflictError(f"Another module in this version already has the code {code}.")


async def create_module(
    db: AsyncSession,
    version: CurriculumVersion,
    fields: ModuleFields,
    *,
    created_by_id: uuid.UUID | None = None,
) -> Module:
    """Add a module at the end of the version (in a phase, or longitudinal).

    Raises:
        ConflictError: If the version is read-only or the code is taken.
        InvalidRequestError: If the phase is not a live phase of the version.
    """
    ensure_editable(version)
    await _check_phase(db, version, fields.phase_id)
    await _check_code(db, version.id, fields.code)
    module = Module(
        version_id=version.id,
        phase_id=fields.phase_id,
        code=fields.code,
        name=fields.name,
        credits=fields.credits,
        nqf_level=fields.nqf_level,
        description=fields.description,
        external_lms_ref=fields.external_lms_ref,
        position=await _next_position(
            db, Module.position, Module.version_id == version.id, Module.deleted_at.is_(None)
        ),
        created_by_id=created_by_id,
    )
    db.add(module)
    await db.flush()
    return module


_MODULE_REQUIRED = frozenset({"code", "name"})
_MODULE_FIELDS = _MODULE_REQUIRED | {
    "phase_id",
    "credits",
    "nqf_level",
    "description",
    "external_lms_ref",
}


async def update_module(
    db: AsyncSession, module: Module, version: CurriculumVersion, changes: dict[str, Any]
) -> Module:
    """Change a module's fields. ``changes`` holds only the fields sent.

    Raises:
        ConflictError: If the version is read-only or the new code is taken.
        InvalidRequestError: If a required field is cleared or the phase is not valid.
    """
    ensure_editable(version)
    for key in _MODULE_REQUIRED:
        if key in changes and changes[key] is None:
            raise InvalidRequestError(f"The module's {key} cannot be empty.")
    if "phase_id" in changes:
        await _check_phase(db, version, changes["phase_id"])
    if changes.get("code") is not None:
        await _check_code(db, version.id, changes["code"], module.id)
    for key, value in changes.items():
        if key in _MODULE_FIELDS:
            setattr(module, key, "" if key == "description" and value is None else value)
    await db.flush()
    return module


async def move_module(
    db: AsyncSession, module: Module, version: CurriculumVersion, position: int
) -> Module:
    """Move a module to ``position`` (from 0) within its phase, or among the modules
    across phases. Moving it to another phase is a change of its ``phase_id``."""
    ensure_editable(version)
    _place(await module_siblings(db, module), module, position)
    await db.flush()
    return module


async def _soft_delete_objectives(db: AsyncSession, *conditions: Any, at: datetime) -> int:
    objectives = list(
        await db.scalars(select(Objective).where(Objective.deleted_at.is_(None), *conditions))
    )
    for objective in objectives:
        objective.deleted_at = at
    return len(objectives)


async def delete_module(db: AsyncSession, module: Module, version: CurriculumVersion) -> None:
    """Soft-delete a module with its sessions and their objectives."""
    ensure_editable(version)
    now = datetime.now(UTC)
    events = list(
        await db.scalars(
            select(LearningEvent).where(
                LearningEvent.module_id == module.id, LearningEvent.deleted_at.is_(None)
            )
        )
    )
    if events:
        await _soft_delete_objectives(
            db, Objective.learning_event_id.in_([e.id for e in events]), at=now
        )
    await _soft_delete_objectives(db, Objective.module_id == module.id, at=now)
    for event in events:
        event.deleted_at = now
    module.deleted_at = now
    await db.flush()


# --- Learning events ----------------------------------------------------------------


@dataclass(frozen=True)
class EventFields:
    title: str
    format_value_id: uuid.UUID | None = None
    contact_minutes: int = 0
    self_study_minutes: int = 0
    week: int | None = None
    description: str = ""
    external_lms_ref: str | None = None


async def _set_format(
    db: AsyncSession, event: LearningEvent, format_value_id: uuid.UUID | None
) -> None:
    if event.format_value_id == format_value_id:
        return  # unchanged, even if the value has been retired since
    value = None
    if format_value_id is not None:
        value = await db.get(TagValue, format_value_id)
        if value is None:
            raise InvalidRequestError("Unknown teaching format.")
    await set_teaching_format(db, event, value)


async def create_event(
    db: AsyncSession,
    module: Module,
    version: CurriculumVersion,
    fields: EventFields,
    *,
    created_by_id: uuid.UUID | None = None,
) -> LearningEvent:
    """Add a session at the end of a module.

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If the format is not from a usable teaching-method list.
    """
    ensure_editable(version)
    event = LearningEvent(
        module_id=module.id,
        title=fields.title,
        contact_minutes=fields.contact_minutes,
        self_study_minutes=fields.self_study_minutes,
        week=fields.week,
        description=fields.description,
        external_lms_ref=fields.external_lms_ref,
        position=await _next_position(
            db,
            LearningEvent.position,
            LearningEvent.module_id == module.id,
            LearningEvent.deleted_at.is_(None),
        ),
        created_by_id=created_by_id,
    )
    db.add(event)
    await db.flush()
    await _set_format(db, event, fields.format_value_id)
    return event


_EVENT_NOT_NULL = frozenset({"title", "contact_minutes", "self_study_minutes"})
_EVENT_FIELDS = _EVENT_NOT_NULL | {"week", "description", "external_lms_ref"}


async def update_event(
    db: AsyncSession, event: LearningEvent, version: CurriculumVersion, changes: dict[str, Any]
) -> LearningEvent:
    """Change a session's fields. ``changes`` holds only the fields sent.

    Raises:
        ConflictError: If the version is read-only.
        InvalidRequestError: If a required field is cleared or the format is not usable.
    """
    ensure_editable(version)
    for key in _EVENT_NOT_NULL:
        if key in changes and changes[key] is None:
            raise InvalidRequestError(f"The session's {key} cannot be empty.")
    for key, value in changes.items():
        if key in _EVENT_FIELDS:
            setattr(event, key, "" if key == "description" and value is None else value)
    if "format_value_id" in changes:
        await _set_format(db, event, changes["format_value_id"])
    await db.flush()
    return event


async def move_event(
    db: AsyncSession, event: LearningEvent, version: CurriculumVersion, position: int
) -> LearningEvent:
    """Move a session to ``position`` (from 0) within its module."""
    ensure_editable(version)
    _place(await event_siblings(db, event.module_id), event, position)
    await db.flush()
    return event


async def delete_event(db: AsyncSession, event: LearningEvent, version: CurriculumVersion) -> None:
    """Soft-delete a session and its objectives."""
    ensure_editable(version)
    now = datetime.now(UTC)
    await _soft_delete_objectives(db, Objective.learning_event_id == event.id, at=now)
    event.deleted_at = now
    await db.flush()
