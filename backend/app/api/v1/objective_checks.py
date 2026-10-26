"""The objective quality checker: live check of typed wording and bulk check of a version.

Rule-based only (ADR 033): nothing is sent to an AI provider and nothing is saved. The
live checks need ``objectives.edit`` at the scope that would own the objective, the same
as adding one, and are rate limited per user. The bulk check needs ``objectives.edit``
somewhere and lists only the objectives the user may see (ADR 027).
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, RedisDep, too_many_attempts
from app.api.v1.curriculum import Access
from app.api.v1.curriculum_objectives import (
    EventObjectiveEditor,
    ModuleObjectiveEditor,
    OutcomeEditor,
)
from app.core.database import DbSession
from app.models.curriculum import ObjectiveLevel
from app.schemas.objective_quality import (
    CheckedObjectiveRead,
    CheckRead,
    CheckRequest,
    VersionCheckRead,
    check_read,
)
from app.services import objective_checks, rate_limit
from app.services.authorization import AuthorizationError
from app.services.curriculum_read import visible_version
from app.services.objective_quality import CheckContext, load_rules

router = APIRouter(tags=["objective-quality"])

# Typing is checked after a short pause in the editor; this only stops runaway clients.
LIVE_CHECKS_PER_MINUTE = 240
_LIVE_SCOPE = "objective-check"


async def _live(
    body: CheckRequest, level: ObjectiveLevel, user: CurrentUser, db: DbSession, redis: RedisDep
) -> CheckRead:
    limited = await rate_limit.check(redis, _LIVE_SCOPE, str(user.id), LIVE_CHECKS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _LIVE_SCOPE, str(user.id), 60)
    result = await objective_checks.check_text(
        db,
        body.text,
        CheckContext(
            level=level,
            domain=body.domain,
            taxonomy_level_id=body.taxonomy_level_id,
            has_parent_links=body.has_parent_links,
        ),
    )
    return check_read(result)


@router.post("/curriculum-versions/{version_id}/outcome-checks", response_model=CheckRead)
async def check_programme_outcome(
    version_id: uuid.UUID,
    body: CheckRequest,
    actor: OutcomeEditor,
    db: DbSession,
    redis: RedisDep,
) -> CheckRead:
    """Check the wording of a programme outcome as typed."""
    return await _live(body, ObjectiveLevel.PROGRAMME, actor, db, redis)


@router.post("/modules/{module_id}/outcome-checks", response_model=CheckRead)
async def check_module_outcome(
    module_id: uuid.UUID,
    body: CheckRequest,
    actor: ModuleObjectiveEditor,
    db: DbSession,
    redis: RedisDep,
) -> CheckRead:
    """Check the wording of a module outcome as typed."""
    return await _live(body, ObjectiveLevel.MODULE, actor, db, redis)


@router.post("/learning-events/{event_id}/objective-checks", response_model=CheckRead)
async def check_event_objective(
    event_id: uuid.UUID,
    body: CheckRequest,
    actor: EventObjectiveEditor,
    db: DbSession,
    redis: RedisDep,
) -> CheckRead:
    """Check the wording of a session objective as typed."""
    return await _live(body, ObjectiveLevel.LEARNING_EVENT, actor, db, redis)


@router.get("/curriculum-versions/{version_id}/objective-checks", response_model=VersionCheckRead)
async def check_version_objectives(
    version_id: uuid.UUID, access: Access, db: DbSession
) -> VersionCheckRead:
    """Check every objective of a version that the user sees (needs ``objectives.edit``)."""
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    try:
        checked = await objective_checks.check_version(db, visible)
    except AuthorizationError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    rules = load_rules()
    return VersionCheckRead(
        version_id=version_id,
        rules_language=rules.language,
        rules_version=rules.version,
        objectives=[
            CheckedObjectiveRead(
                **check_read(item.result).model_dump(),
                objective_id=item.objective.id,
                level=item.objective.level,
                text=item.objective.text,
                status=item.objective.status,
                domain=item.objective.domain,
                module_id=item.module.id if item.module else None,
                module_code=item.module.code if item.module else None,
                event_id=item.event.id if item.event else None,
                event_title=item.event.title if item.event else None,
                can_edit=item.can_edit,
            )
            for item in checked
        ],
    )
