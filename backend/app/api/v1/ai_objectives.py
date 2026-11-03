"""AI help with one objective as it is being written: a measurable rewrite and a suggested domain
and taxonomy level (Slice 1.17, ADR 046).

The wording is whatever the editor holds, so it works for an objective not yet saved. Nothing is
saved here and nothing is accepted: the screen shows the suggestion and the person applies it by
saving the objective in the ordinary way. It needs ``objectives.edit`` at the scope that would own
the objective (the same as the quality checker) and ``ai.run`` at the programme (a programme
outcome) or the module (a module outcome or a session objective). A refusal because AI is off,
restricted, over budget or because the privacy guard found personal information is a 409 with the
reason; a provider failure is a 502.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, StringConstraints

from app.api.deps import CurrentUser, RedisDep, SettingsDep, too_many_attempts
from app.api.v1.ai_settings import Transport
from app.api.v1.curriculum_edit import target_of
from app.api.v1.curriculum_objectives import (
    EventObjectiveEditor,
    ModuleObjectiveEditor,
    OutcomeEditor,
)
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel
from app.services import ai_objectives, rate_limit
from app.services.authorization import AuthorizationError, ScopeRef, has_permission
from app.services.objective_quality import CheckContext

router = APIRouter(tags=["ai-objectives"])

# Each call costs money, so the limit is far below the live checker's.
AI_CALLS_PER_MINUTE = 20
_SCOPE = "objective-ai"

ObjectiveWording = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class AiObjectiveRequest(BaseModel):
    task: Literal["rewrite", "classify"]
    text: ObjectiveWording
    domain: ObjectiveDomain | None = None
    taxonomy_level_id: uuid.UUID | None = None
    has_parent_links: bool | None = None


class RewriteRead(BaseModel):
    text: str
    rationale: str
    # The AI found the wording already measurable and gave it back as it was.
    unchanged: bool


class ClassificationRead(BaseModel):
    domain: ObjectiveDomain | None
    taxonomy_level_id: uuid.UUID | None
    taxonomy_level_name: str | None
    scale_name: str | None
    confidence: Decimal
    rationale: str


class AiObjectiveRead(BaseModel):
    task: Literal["rewrite", "classify"]
    run_id: uuid.UUID
    rewrite: RewriteRead | None = None
    classification: ClassificationRead | None = None


async def _suggest(
    request: Request,
    body: AiObjectiveRequest,
    level: ObjectiveLevel,
    actor: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    transport: Transport,
) -> AiObjectiveRead:
    target = target_of(request)
    if level is ObjectiveLevel.PROGRAMME:
        scope = ScopeRef(ScopeType.PROGRAMME, target.visible.programme.id)
    else:
        assert target.module is not None
        scope = ScopeRef(ScopeType.MODULE, target.module.id)
    if not await has_permission(db, actor, Permission.AI_RUN, scope):
        raise AuthorizationError("You do not have permission to use AI here.")
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), AI_CALLS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)

    if body.task == "rewrite":
        suggestion = await ai_objectives.rewrite(
            db,
            settings,
            actor_id=actor.id,
            text=body.text,
            level=level,
            transport=transport,
            context=CheckContext(
                level=level,
                domain=body.domain,
                taxonomy_level_id=body.taxonomy_level_id,
                has_parent_links=body.has_parent_links,
            ),
        )
        return AiObjectiveRead(
            task="rewrite",
            run_id=suggestion.run_id,
            rewrite=RewriteRead(
                text=suggestion.text, rationale=suggestion.rationale, unchanged=suggestion.unchanged
            ),
        )
    found = await ai_objectives.classify(
        db, settings, actor_id=actor.id, text=body.text, level=level, transport=transport
    )
    return AiObjectiveRead(
        task="classify",
        run_id=found.run_id,
        classification=ClassificationRead(
            domain=found.domain,
            taxonomy_level_id=found.taxonomy_level_id,
            taxonomy_level_name=found.taxonomy_level_name,
            scale_name=found.scale_name,
            confidence=found.confidence,
            rationale=found.rationale,
        ),
    )


@router.post("/curriculum-versions/{version_id}/outcome-ai", response_model=AiObjectiveRead)
async def ai_for_programme_outcome(
    version_id: uuid.UUID,
    body: AiObjectiveRequest,
    request: Request,
    actor: OutcomeEditor,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    transport: Transport,
) -> AiObjectiveRead:
    """Suggest a rewrite or a domain and level for a programme outcome."""
    return await _suggest(
        request, body, ObjectiveLevel.PROGRAMME, actor, db, redis, settings, transport
    )


@router.post("/modules/{module_id}/outcome-ai", response_model=AiObjectiveRead)
async def ai_for_module_outcome(
    module_id: uuid.UUID,
    body: AiObjectiveRequest,
    request: Request,
    actor: ModuleObjectiveEditor,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    transport: Transport,
) -> AiObjectiveRead:
    """Suggest a rewrite or a domain and level for a module outcome."""
    return await _suggest(
        request, body, ObjectiveLevel.MODULE, actor, db, redis, settings, transport
    )


@router.post("/learning-events/{event_id}/objective-ai", response_model=AiObjectiveRead)
async def ai_for_event_objective(
    event_id: uuid.UUID,
    body: AiObjectiveRequest,
    request: Request,
    actor: EventObjectiveEditor,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    transport: Transport,
) -> AiObjectiveRead:
    """Suggest a rewrite or a domain and level for a session objective."""
    return await _suggest(
        request, body, ObjectiveLevel.LEARNING_EVENT, actor, db, redis, settings, transport
    )
