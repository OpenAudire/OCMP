"""AI mapping runs: start one for a draft version, follow its progress, cancel it (ADR 045).

Starting a run needs ``ai.run`` and ``mapping.edit`` at the programme, or at the module when
the run is limited to one module. A version the user cannot see is a 404 (ADR 027); a refusal
because AI is off, restricted or not set up is a 409 with the reason. The run is queued and a
background job does the work; results are ``suggested`` links in the review queue.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, SettingsDep
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.jobs.mapping import run_ai_mapping
from app.models import AIRun, Framework, Module, User
from app.models.mapping import AIRunStatus, AIRunType
from app.services import ai_mapping
from app.services.audit import audit_operation
from app.services.authorization import AuthorizationError, ScopeRef, has_permission
from app.services.curriculum_read import CurriculumAccess, VisibleVersion, visible_version
from app.services.mapping_shortlist import DEFAULT_K

router = APIRouter(tags=["ai-mapping"])


class AiRunCreate(BaseModel):
    framework_id: uuid.UUID
    # Limit the run to one module (its outcomes and its sessions' objectives).
    module_id: uuid.UUID | None = None
    top_k: int = Field(default=DEFAULT_K, ge=ai_mapping.MIN_K, le=ai_mapping.MAX_K)


class AiRunRead(BaseModel):
    id: uuid.UUID
    status: AIRunStatus
    version_id: uuid.UUID
    framework_id: uuid.UUID
    module_id: uuid.UUID | None
    prompt_version: str
    provider: str
    model: str
    top_k: int
    total_items: int
    done_items: int
    failed_items: int
    links_created: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def run_read(run: AIRun) -> AiRunRead:
    module = run.scope.get("module_id")
    return AiRunRead(
        id=run.id,
        status=run.status,
        version_id=uuid.UUID(run.scope["version_id"]),
        framework_id=uuid.UUID(run.scope["framework_id"]),
        module_id=uuid.UUID(module) if module else None,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        top_k=int(run.parameters.get("top_k", DEFAULT_K)),
        total_items=run.total_items,
        done_items=run.done_items,
        failed_items=run.failed_items,
        links_created=run.links_created,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost=run.estimated_cost,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.")


async def _visible(
    db: DbSession, access: CurriculumAccess, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise _not_found("Curriculum version")
    return visible


async def _require_runner(
    db: DbSession, user: User, visible: VisibleVersion, module_id: uuid.UUID | None
) -> None:
    """``ai.run`` and ``mapping.edit`` at the module (a run limited to it) or the programme."""
    if module_id is not None:
        scope = ScopeRef(ScopeType.MODULE, module_id)
    else:
        scope = ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
    for permission in (Permission.AI_RUN, Permission.MAPPING_EDIT):
        if not await has_permission(db, user, permission, scope):
            raise AuthorizationError("You do not have permission to run AI mapping here.")


async def _run_for(
    db: DbSession, access: CurriculumAccess, user: User, run_id: uuid.UUID
) -> tuple[AIRun, VisibleVersion]:
    run = await db.get(AIRun, run_id)
    if run is None or run.type != AIRunType.MAPPING or "version_id" not in run.scope:
        raise _not_found("Run")
    visible = await visible_version(db, access, uuid.UUID(run.scope["version_id"]))
    if visible is None:
        raise _not_found("Run")
    module = run.scope.get("module_id")
    await _require_runner(db, user, visible, uuid.UUID(module) if module else None)
    return run, visible


@router.post(
    "/curriculum-versions/{version_id}/ai-mapping-runs",
    response_model=AiRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_ai_mapping(
    version_id: uuid.UUID,
    body: AiRunCreate,
    access: Access,
    actor: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> AiRunRead:
    """Queue a run that suggests links from the objectives to a framework."""
    visible = await _visible(db, access, version_id)
    module = None
    if body.module_id is not None:
        module = await db.get(Module, body.module_id)
        if (
            module is None
            or module.is_deleted
            or module.version_id != version_id
            or not visible.view.shows_module(module.id)
        ):
            raise _not_found("Module")
    await _require_runner(db, actor, visible, body.module_id)
    framework = await db.get(Framework, body.framework_id)
    if framework is None or framework.is_deleted:
        raise _not_found("Framework")
    with audit_operation("mapping.ai_run_start", actor_id=actor.id):
        run = await ai_mapping.start_run(
            db,
            settings,
            actor_id=actor.id,
            version=visible.version,
            framework=framework,
            module=module,
            top_k=body.top_k,
        )
    run_ai_mapping.send(str(run.id))
    return run_read(run)


@router.get("/curriculum-versions/{version_id}/ai-mapping-runs", response_model=list[AiRunRead])
async def list_ai_mapping_runs(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> list[AiRunRead]:
    """The latest runs of a version (up to ten), newest first."""
    visible = await _visible(db, access, version_id)
    await _require_runner(db, actor, visible, None)
    runs = await db.scalars(
        select(AIRun)
        .where(AIRun.type == AIRunType.MAPPING)
        .order_by(AIRun.created_at.desc())
        .limit(100)
    )
    mine = [run for run in runs if run.scope.get("version_id") == str(version_id)]
    return [run_read(run) for run in mine[:10]]


@router.get("/ai-mapping-runs/{run_id}", response_model=AiRunRead)
async def get_ai_mapping_run(
    run_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> AiRunRead:
    """A run's state and progress (poll this while it is queued or running)."""
    run, _ = await _run_for(db, access, actor, run_id)
    return run_read(run)


@router.post("/ai-mapping-runs/{run_id}/cancel", response_model=AiRunRead)
async def cancel_ai_mapping_run(
    run_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> AiRunRead:
    """Stop a run before its next objective. Suggestions already made stay."""
    run, _ = await _run_for(db, access, actor, run_id)
    return run_read(await ai_mapping.cancel_run(db, run))
