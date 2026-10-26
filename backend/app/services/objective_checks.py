"""Running the objective quality checker against the database (ADR 033).

The rules themselves are pure (``app.services.objective_quality``). This module loads the
taxonomy levels and their verbs, and for the bulk check collects the objectives of one
version that the user may see, with the context the rules need.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import Permission, ScopeType
from app.models import (
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    TaxonomyScale,
)
from app.models.curriculum import ObjectiveLevel, ObjectiveStatus
from app.services.authorization import AuthorizationError
from app.services.curriculum_edit import is_editable
from app.services.curriculum_read import CurriculumAccess, VisibleVersion
from app.services.objective_quality import (
    CheckContext,
    CheckResult,
    LevelVerbs,
    check_objective,
)


async def level_verbs(db: AsyncSession) -> list[LevelVerbs]:
    """Every taxonomy level with its verb list, scales in name order."""
    scales = await db.scalars(
        select(TaxonomyScale)
        .options(selectinload(TaxonomyScale.levels))
        .order_by(TaxonomyScale.name)
    )
    found: list[LevelVerbs] = []
    for index, scale in enumerate(scales):
        found.extend(
            LevelVerbs(
                level_id=level.id,
                level_name=level.name,
                scale_key=scale.key,
                scale_name=scale.name,
                scale_position=index,
                level_position=level.position,
                verbs=tuple(level.verbs),
            )
            for level in scale.levels
        )
    return found


async def check_text(
    db: AsyncSession,
    text: str,
    context: CheckContext,
) -> CheckResult:
    """Check wording typed in the editor; nothing is saved."""
    return check_objective(text, context, await level_verbs(db))


def may_use_checker(access: CurriculumAccess) -> bool:
    """Whether the user holds ``objectives.edit`` anywhere (the bulk check is for editors)."""
    held = [access.instance, *access.scoped.values()]
    return any(Permission.OBJECTIVES_EDIT in permissions for permissions in held)


@dataclass(frozen=True)
class CheckedObjective:
    objective: Objective
    module: Module | None
    event: LearningEvent | None
    result: CheckResult
    can_edit: bool


async def check_version(db: AsyncSession, visible: VisibleVersion) -> list[CheckedObjective]:
    """Check the live objectives of a version that the user sees, in curriculum order.

    Objectives of items the user cannot see are left out (ADR 027). Retired objectives
    are skipped: they are no longer taught."""
    if not may_use_checker(visible.access):
        raise AuthorizationError("You do not have permission to check objectives.")
    version, view, access = visible.version, visible.view, visible.access
    module_id = func.coalesce(Objective.module_id, LearningEvent.module_id)
    rows = (
        await db.execute(
            select(Objective, Module, LearningEvent)
            .outerjoin(LearningEvent, LearningEvent.id == Objective.learning_event_id)
            .outerjoin(Module, Module.id == module_id)
            .where(
                Objective.version_id == version.id,
                Objective.deleted_at.is_(None),
                Objective.status != ObjectiveStatus.RETIRED,
            )
            .order_by(
                Objective.level != ObjectiveLevel.PROGRAMME,
                Module.position,
                Module.code,
                Objective.level != ObjectiveLevel.MODULE,
                LearningEvent.position,
                Objective.position,
                Objective.created_at,
            )
        )
    ).all()

    def shown(objective: Objective, module: Module | None, event: LearningEvent | None) -> bool:
        if objective.level == ObjectiveLevel.PROGRAMME:
            return view.full
        if module is None or module.deleted_at is not None:
            return False
        if objective.level == ObjectiveLevel.MODULE:
            return view.shows_module(module.id)
        return (
            event is not None and event.deleted_at is None and view.shows_event(module.id, event.id)
        )

    chosen = [(o, m, e) for o, m, e in rows if shown(o, m, e)]
    parents: set[uuid.UUID] = set()
    if chosen:
        parent = Objective.__table__.alias("parent")
        linked = await db.scalars(
            select(ObjectiveLink.child_id)
            .join(parent, parent.c.id == ObjectiveLink.parent_id)
            .where(
                ObjectiveLink.child_id.in_([o.id for o, _, _ in chosen]),
                parent.c.deleted_at.is_(None),
            )
        )
        parents = set(linked)

    levels = await level_verbs(db)
    programme_permissions = access.for_programme(visible.programme)
    editable = is_editable(version)
    checked: list[CheckedObjective] = []
    for objective, module, event in chosen:
        held = programme_permissions
        if module is not None:
            held = held | access.at(ScopeType.MODULE, module.id)
        if event is not None:
            held = held | access.at(ScopeType.LEARNING_EVENT, event.id)
        result = check_objective(
            objective.text,
            CheckContext(
                level=objective.level,
                domain=objective.domain,
                taxonomy_level_id=objective.taxonomy_level_id,
                has_parent_links=objective.id in parents,
            ),
            levels,
        )
        checked.append(
            CheckedObjective(
                objective,
                module,
                event,
                result,
                can_edit=editable and Permission.OBJECTIVES_EDIT in held,
            )
        )
    return checked
