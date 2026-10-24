"""Curriculum scopes for authorization: programme > module > learning event.

A module's parent scope is its programme (through its curriculum version), so
a role held for a programme applies to every version's modules and sessions.
Soft-deleted rows, and rows under a soft-deleted version, are not scopes.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ScopeType
from app.models import CurriculumVersion, LearningEvent, Module, Objective, Programme
from app.models.curriculum import ObjectiveLevel
from app.services.authorization import ScopeRef, register_scope


async def _programme_parent(db: AsyncSession, programme_id: uuid.UUID) -> ScopeRef | None:
    faculty_id = await db.scalar(
        select(Programme.faculty_id).where(
            Programme.id == programme_id, Programme.deleted_at.is_(None)
        )
    )
    return ScopeRef(ScopeType.FACULTY, faculty_id) if faculty_id else None


async def _module_parent(db: AsyncSession, module_id: uuid.UUID) -> ScopeRef | None:
    programme_id = await db.scalar(
        select(CurriculumVersion.programme_id)
        .join(Module, Module.version_id == CurriculumVersion.id)
        .where(
            Module.id == module_id,
            Module.deleted_at.is_(None),
            CurriculumVersion.deleted_at.is_(None),
        )
    )
    return ScopeRef(ScopeType.PROGRAMME, programme_id) if programme_id else None


async def _learning_event_parent(db: AsyncSession, event_id: uuid.UUID) -> ScopeRef | None:
    module_id = await db.scalar(
        select(LearningEvent.module_id).where(
            LearningEvent.id == event_id, LearningEvent.deleted_at.is_(None)
        )
    )
    return ScopeRef(ScopeType.MODULE, module_id) if module_id else None


def register() -> None:
    """Register the curriculum scope types with the authorization service."""
    register_scope(ScopeType.PROGRAMME, _programme_parent)
    register_scope(ScopeType.MODULE, _module_parent)
    register_scope(ScopeType.LEARNING_EVENT, _learning_event_parent)


async def objective_scope(db: AsyncSession, objective: Objective) -> ScopeRef:
    """The scope an objective (and its mappings and tags) belongs to."""
    if objective.level == ObjectiveLevel.LEARNING_EVENT:
        assert objective.learning_event_id is not None
        return ScopeRef(ScopeType.LEARNING_EVENT, objective.learning_event_id)
    if objective.level == ObjectiveLevel.MODULE:
        assert objective.module_id is not None
        return ScopeRef(ScopeType.MODULE, objective.module_id)
    programme_id = await db.scalar(
        select(CurriculumVersion.programme_id).where(CurriculumVersion.id == objective.version_id)
    )
    assert programme_id is not None
    return ScopeRef(ScopeType.PROGRAMME, programme_id)
