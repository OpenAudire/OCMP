"""Study guides: upload one, follow its reading, decide the objectives it proposed (ADR 047).

Needs ``objectives.edit`` at the module and ``ai.run`` at the module, on a draft version. The
upload must carry the confirmation that the guide holds no real patient information (the form
fields ``confirmed`` and ``text_version``); without it nothing is read or recorded (422). The
file is read in this request, never stored, and its name is never looked at. The AI then reads it
in a background job; its results are *proposals*, and nothing becomes an objective until a person
accepts it.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RedisDep, SettingsDep, require_permission, too_many_attempts
from app.api.v1.curriculum_edit import module_target_for, not_found, path_id, target_of
from app.api.v1.curriculum_objectives import ModuleObjectiveEditor
from app.core.database import DbSession
from app.core.permissions import Permission, ScopeType
from app.jobs.study_guides import run_study_guide
from app.models import AIRun, ObjectiveProposal, User
from app.models.curriculum import ObjectiveDomain
from app.models.mapping import AIRunStatus, AIRunType
from app.models.proposal import ProposalStatus
from app.services import ai_mapping, rate_limit, study_guide_extraction
from app.services.audit import audit_operation
from app.services.authorization import AuthorizationError, ScopeRef, has_permission
from app.services.study_guide_confirmation import StudyGuideConfirmation
from app.services.study_guide_text import MAX_UPLOAD_BYTES

router = APIRouter(tags=["study-guides"])

UPLOADS_PER_MINUTE = 10
_SCOPE = "study-guide-upload"


class ExtractionRunRead(BaseModel):
    id: uuid.UUID
    status: AIRunStatus
    module_id: uuid.UUID
    # How many pieces of the guide there are, how many are read, how many failed.
    total_items: int
    done_items: int
    failed_items: int
    proposals_created: int
    truncated: bool
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class ProposalRead(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    module_id: uuid.UUID
    text: str
    domain: ObjectiveDomain | None
    source_quote: str
    status: ProposalStatus


class AcceptBody(BaseModel):
    """Optional corrections made while accepting; what is left out stays as proposed."""

    text: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    domain: ObjectiveDomain | None = None
    # True to apply ``domain`` even when it is null (clear the proposed domain).
    set_domain: bool = False


class Accepted(BaseModel):
    proposal: ProposalRead
    objective_id: uuid.UUID


def _proposal_read(proposal: ObjectiveProposal) -> ProposalRead:
    return ProposalRead(
        id=proposal.id,
        run_id=proposal.run_id,
        module_id=proposal.module_id,
        text=proposal.text,
        domain=proposal.domain,
        source_quote=proposal.source_quote,
        status=proposal.status,
    )


async def _run_read(db: AsyncSession, run: AIRun) -> ExtractionRunRead:
    made = (
        await db.scalar(
            select(func.count(ObjectiveProposal.id)).where(ObjectiveProposal.run_id == run.id)
        )
    ) or 0
    return ExtractionRunRead(
        id=run.id,
        status=run.status,
        module_id=uuid.UUID(run.scope["module_id"]),
        total_items=run.total_items,
        done_items=run.done_items,
        failed_items=run.failed_items,
        proposals_created=made,
        truncated=bool(run.scope.get("truncated")),
        error_message=run.error_message,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


async def _proposal_module_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    proposal_id = path_id(request, "proposal_id", "Proposal")
    proposal = await db.get(ObjectiveProposal, proposal_id)
    if proposal is None:
        raise not_found("Proposal")
    target = await module_target_for(request, db, user, proposal.module_id)
    assert target.module is not None
    return ScopeRef(ScopeType.MODULE, target.module.id)


async def _run_module_scope(request: Request, db: AsyncSession, user: User) -> ScopeRef:
    run_id = path_id(request, "run_id", "Run")
    run = await db.get(AIRun, run_id)
    if run is None or run.type != AIRunType.EXTRACTION or "module_id" not in run.scope:
        raise not_found("Run")
    target = await module_target_for(request, db, user, uuid.UUID(run.scope["module_id"]))
    assert target.module is not None
    return ScopeRef(ScopeType.MODULE, target.module.id)


def _editor(scope: Any) -> Any:
    return Depends(require_permission(Permission.OBJECTIVES_EDIT, scope=scope))


ProposalEditor = Annotated[User, _editor(_proposal_module_scope)]
RunEditor = Annotated[User, _editor(_run_module_scope)]


async def _require_ai(db: AsyncSession, user: User, module_id: uuid.UUID) -> None:
    if not await has_permission(db, user, Permission.AI_RUN, ScopeRef(ScopeType.MODULE, module_id)):
        raise AuthorizationError("You do not have permission to use AI here.")


@router.post(
    "/modules/{module_id}/study-guides",
    response_model=ExtractionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_study_guide(
    module_id: uuid.UUID,
    request: Request,
    actor: ModuleObjectiveEditor,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    confirmed: Annotated[bool, Form()],
    text_version: Annotated[str, Form()],
) -> ExtractionRunRead:
    """Read a PDF or Word study guide for the module and queue the AI reading of it.

    The file's name is never read, stored or logged.
    """
    target = target_of(request)
    assert target.module is not None
    await _require_ai(db, actor, target.module.id)
    limited = await rate_limit.check(redis, _SCOPE, str(actor.id), UPLOADS_PER_MINUTE)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _SCOPE, str(actor.id), 60)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 10 MB."
        )
    with audit_operation("study_guide.upload", actor_id=actor.id):
        run = await study_guide_extraction.start_extraction(
            db,
            settings,
            redis,
            actor=actor,
            module=target.module,
            version=target.version,
            content=content,
            confirmation=StudyGuideConfirmation(confirmed=confirmed, text_version=text_version),
        )
    run_study_guide.send(str(run.id))
    return await _run_read(db, run)


@router.get("/modules/{module_id}/study-guide-runs", response_model=list[ExtractionRunRead])
async def list_study_guide_runs(
    module_id: uuid.UUID,
    request: Request,
    actor: ModuleObjectiveEditor,
    db: DbSession,
) -> list[ExtractionRunRead]:
    """The latest readings of study guides for the module (up to five), newest first."""
    target = target_of(request)
    assert target.module is not None
    await _require_ai(db, actor, target.module.id)
    await ai_mapping.expire_stale_runs(db)
    runs = await db.scalars(
        select(AIRun)
        .where(AIRun.type == AIRunType.EXTRACTION)
        .order_by(AIRun.created_at.desc())
        .limit(100)
    )
    mine = [r for r in runs if r.scope.get("module_id") == str(module_id)][:5]
    return [await _run_read(db, run) for run in mine]


@router.get("/modules/{module_id}/objective-proposals", response_model=list[ProposalRead])
async def list_proposals(
    module_id: uuid.UUID,
    actor: ModuleObjectiveEditor,
    request: Request,
    db: DbSession,
) -> list[ProposalRead]:
    """The module's proposed objectives that no one has decided yet, oldest first."""
    target = target_of(request)
    assert target.module is not None
    await _require_ai(db, actor, target.module.id)
    rows = await db.scalars(
        select(ObjectiveProposal)
        .where(
            ObjectiveProposal.module_id == target.module.id,
            ObjectiveProposal.status == ProposalStatus.PENDING,
        )
        .order_by(ObjectiveProposal.created_at, ObjectiveProposal.id)
    )
    return [_proposal_read(p) for p in rows]


@router.post("/objective-proposals/{proposal_id}/accept", response_model=Accepted)
async def accept_proposal(
    proposal_id: uuid.UUID,
    body: AcceptBody,
    request: Request,
    actor: ProposalEditor,
    db: DbSession,
    settings: SettingsDep,
) -> Accepted:
    """Make a proposal a draft objective of its module, with the corrections sent."""
    from app.jobs.embeddings import enqueue_objective

    target = target_of(request)
    assert target.module is not None
    proposal = await db.get(ObjectiveProposal, proposal_id)
    assert proposal is not None
    objective = await study_guide_extraction.accept_proposal(
        db,
        proposal,
        actor=actor,
        module=target.module,
        version=target.version,
        text=body.text,
        domain=body.domain,
        change_domain=body.set_domain,
    )
    enqueue_objective(settings, objective.id)
    return Accepted(proposal=_proposal_read(proposal), objective_id=objective.id)


@router.post("/objective-proposals/{proposal_id}/reject", response_model=ProposalRead)
async def reject_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    actor: ProposalEditor,
    db: DbSession,
) -> ProposalRead:
    """Reject a proposal; it is kept so the same wording is not proposed again."""
    proposal = await db.get(ObjectiveProposal, proposal_id)
    assert proposal is not None
    with audit_operation("study_guide.proposal_reject", actor_id=actor.id):
        await study_guide_extraction.reject_proposal(db, proposal, actor=actor)
    return _proposal_read(proposal)


@router.post("/study-guide-runs/{run_id}/cancel", response_model=ExtractionRunRead)
async def cancel_study_guide_run(
    run_id: uuid.UUID,
    request: Request,
    actor: RunEditor,
    db: DbSession,
) -> ExtractionRunRead:
    """Stop a reading that has not finished; proposals already made stay."""
    run = await db.get(AIRun, run_id)
    assert run is not None
    target = target_of(request)
    assert target.module is not None
    await _require_ai(db, actor, target.module.id)
    await ai_mapping.cancel_run(db, run)
    return await _run_read(db, run)
