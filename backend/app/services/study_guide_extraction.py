"""Reading a study guide into proposed objectives (Slice 1.18, ADR 047).

1. ``start_extraction``: the uploader's confirmation is recorded first (the file is not read
   before), the text is read from the file in this process (the file is not stored, and its name
   is never read), the pieces of text are kept in Redis for an hour and a run is queued.
2. ``execute_extraction`` (the background job): one guarded call for each piece of the guide, the
   answer checked (every objective must carry a quote that is words of that piece), and each
   objective saved as a *pending proposal*. The run commits after every piece.
3. A person accepts a proposal (``accept_proposal``: an ordinary draft objective through the
   objective service) or rejects it. Nothing becomes curriculum on its own.

The privacy guard refuses study-guide text without the confirmation receipt, so the receipt is
re-issued from the recorded confirmation (``recorded_receipt``) inside the job.
"""

import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.errors import (
    AIBudgetExceededError,
    AIError,
    AIRefusedError,
    PersonalDataRefusedError,
    ProviderError,
)
from app.ai.extraction_answer import Proposed, parse_extraction
from app.ai.objective_answers import InvalidAnswer
from app.core.config import Settings
from app.core.logging import get_logger
from app.models import AIRun, CurriculumVersion, Module, Objective, ObjectiveProposal, User
from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, ObjectiveStatus
from app.models.mapping import AIRunStatus, AIRunType
from app.models.proposal import ProposalStatus
from app.services import ai_gateway, curriculum_objectives
from app.services.ai_mapping import ACTIVE, MAX_IN_ROW, expire_stale_runs
from app.services.ai_objectives import ask_with_retry
from app.services.audit import audit_operation
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.curriculum_edit import ensure_editable
from app.services.study_guide_confirmation import (
    StudyGuideConfirmation,
    confirm_no_patient_information,
    recorded_receipt,
)
from app.services.study_guide_text import read_guide

logger = get_logger(__name__)

TEXT_TTL_SECONDS = 3600
_SPACE = re.compile(r"\s+")


def text_key(run_id: uuid.UUID) -> str:
    return f"study-guide:{run_id}"


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold()


async def start_extraction(
    db: AsyncSession,
    settings: Settings,
    redis: Redis,
    *,
    actor: User,
    module: Module,
    version: CurriculumVersion,
    content: bytes,
    confirmation: StudyGuideConfirmation | None,
) -> AIRun:
    """Check, confirm, read and queue a run (the caller queues the job).

    Raises:
        ConflictError: If the version is not a draft, or a run for this module is going.
        InvalidRequestError: If the confirmation is missing or stale, or the file cannot be used.
        AIRefusedError: If AI is off, restricted or not set up (nothing was recorded).
    """
    ensure_editable(version)
    await expire_stale_runs(db)
    running = await db.scalars(
        select(AIRun).where(AIRun.type == AIRunType.EXTRACTION, AIRun.status.in_(ACTIVE))
    )
    if any(r.scope.get("module_id") == str(module.id) for r in running):
        raise ConflictError("A study guide for this module is already being read.")
    provider, model = await ai_gateway.ensure_ready(db, settings)
    # The confirmation comes first: the file is not read until it is recorded.
    receipt = await confirm_no_patient_information(db, actor.id, confirmation, content=content)
    guide = read_guide(content)
    run = AIRun(
        type=AIRunType.EXTRACTION,
        status=AIRunStatus.QUEUED,
        provider=provider,
        model=model,
        prompt_version=f"{prompts.EXTRACT.name}:{prompts.EXTRACT.version}",
        scope={
            "module_id": str(module.id),
            "version_id": str(version.id),
            "document_sha256": receipt.document_sha256,
            "truncated": guide.truncated,
        },
        total_items=len(guide.chunks),
        created_by_id=actor.id,
    )
    db.add(run)
    await db.flush()
    await redis.set(
        text_key(run.id),
        json.dumps({"chunks": guide.chunks, "truncated": guide.truncated}),
        ex=TEXT_TTL_SECONDS,
    )
    return run


async def _existing_texts(db: AsyncSession, module: Module) -> set[str]:
    """Wording the module already has as an objective, or has had proposed (rejected ones too:
    a rejection is a person's "no", so the same wording is not put to them again)."""
    objectives = await db.scalars(
        select(Objective.text).where(
            Objective.module_id == module.id,
            Objective.level == ObjectiveLevel.MODULE,
            Objective.deleted_at.is_(None),
        )
    )
    proposals = await db.scalars(
        select(ObjectiveProposal.text).where(ObjectiveProposal.module_id == module.id)
    )
    return {_normalise(t) for t in [*objectives, *proposals]}


async def _save(
    db: AsyncSession, run: AIRun, module: Module, found: list[Proposed], known: set[str]
) -> int:
    made = 0
    for item in found:
        key = _normalise(item.text)
        if key in known:
            continue
        known.add(key)
        db.add(
            ObjectiveProposal(
                run_id=run.id,
                module_id=module.id,
                text=item.text,
                domain=item.domain,
                source_quote=item.source_quote,
                created_by_id=run.created_by_id,
            )
        )
        made += 1
    await db.flush()
    return made


async def execute_extraction(
    db: AsyncSession,
    settings: Settings,
    redis: Redis,
    run_id: uuid.UUID,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    after_piece: Callable[[], Awaitable[None]] | None = None,
) -> AIRun:
    """Do a queued run. Never raises for the ordinary ways a run ends; the run row says how."""
    run = await db.get(AIRun, run_id)
    if run is None or run.status != AIRunStatus.QUEUED or run.type != AIRunType.EXTRACTION:
        raise InvalidRequestError("This run cannot be started.")
    run.status = AIRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    await db.flush()
    if after_piece:
        await after_piece()

    notes: list[str] = []
    in_row = attempts = 0
    try:
        stored = await redis.get(text_key(run.id))
        receipt = await recorded_receipt(db, run.created_by_id, run.scope["document_sha256"])
        module = await db.get(Module, uuid.UUID(run.scope["module_id"]))
        if stored is None:
            raise InvalidRequestError(
                "The uploaded text is no longer kept. Upload the study guide again."
            )
        if receipt is None or module is None or module.is_deleted:
            raise InvalidRequestError("The confirmation or the module could not be found.")
        payload = json.loads(stored)
        known = await _existing_texts(db, module)
        if payload.get("truncated"):
            notes.append("only the first part of a long study guide was read")
        for piece in payload["chunks"]:
            await db.refresh(run)
            if run.status != AIRunStatus.RUNNING:
                break
            try:
                found = await ask_with_retry(
                    db,
                    settings,
                    run,
                    prompts.EXTRACT,
                    {"module_title": module.name, "study_guide_text": piece},
                    transport,
                    partial(parse_extraction, guide_text=piece),
                    receipt,
                )
                attempts += 1
                in_row = 0
                await _save(db, run, module, found, known)
            except PersonalDataRefusedError:
                attempts += 1
                run.failed_items += 1
                notes.append("some parts were skipped because they may hold personal information")
            except AIBudgetExceededError as exc:
                run.status = AIRunStatus.BUDGET_EXCEEDED
                run.error_message = str(exc)[:1000]
                break
            except AIRefusedError as exc:
                run.status = AIRunStatus.FAILED
                run.error_message = str(exc)[:1000]
                break
            except (ProviderError, InvalidAnswer) as exc:
                attempts += 1
                run.failed_items += 1
                in_row = in_row + 1 if isinstance(exc, ProviderError) else 0
                if in_row >= MAX_IN_ROW:
                    run.status = AIRunStatus.FAILED
                    run.error_message = "The AI provider failed several times in a row."
                    run.done_items += 1
                    break
            run.done_items += 1
            await db.flush()
            if after_piece:
                await after_piece()
    except AIError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except InvalidRequestError as exc:
        run.status = AIRunStatus.FAILED
        run.error_message = str(exc)[:1000]
    except Exception as exc:
        logger.error("study_guide_run_crashed", run_id=str(run.id), error=type(exc).__name__)
        run.status = AIRunStatus.FAILED
        run.error_message = "The run stopped because of an unexpected error."

    if run.status == AIRunStatus.RUNNING:
        everything_failed = attempts > 0 and run.failed_items >= attempts
        run.status = AIRunStatus.FAILED if everything_failed else AIRunStatus.SUCCEEDED
        if everything_failed:
            run.error_message = "No part of the study guide could be read by the AI."
        elif notes:
            run.error_message = "; ".join(dict.fromkeys(notes))
    run.finished_at = run.finished_at or datetime.now(UTC)
    await db.flush()
    await redis.delete(text_key(run.id))
    if after_piece:
        await after_piece()
    logger.info(
        "study_guide_run_finished",
        run_id=str(run.id),
        status=run.status.value,
        pieces=run.total_items,
        failed=run.failed_items,
    )
    return run


async def accept_proposal(
    db: AsyncSession,
    proposal: ObjectiveProposal,
    *,
    actor: User,
    module: Module,
    version: CurriculumVersion,
    text: str | None = None,
    domain: ObjectiveDomain | None = None,
    change_domain: bool = False,
) -> Objective:
    """Make the proposal a draft objective of its module (reviewers may correct the wording).

    Raises:
        ConflictError: If the proposal was decided already, or the version is read-only.
        InvalidRequestError: If the wording is blank.
    """
    if proposal.status != ProposalStatus.PENDING:
        raise ConflictError("This proposal was decided already.")
    ensure_editable(version)
    wording = (text if text is not None else proposal.text).strip()
    if not wording:
        raise InvalidRequestError("The wording cannot be empty.")
    chosen = domain if change_domain else proposal.domain
    with audit_operation(
        "curriculum.objective_create", actor_id=actor.id, reason="from a study guide proposal"
    ):
        objective = await curriculum_objectives.create_objective(
            db,
            module,
            version,
            {"text": wording, "domain": chosen, "status": ObjectiveStatus.DRAFT, "parent_ids": []},
            options=[],
            can_approve=False,
            created_by_id=actor.id,
        )
    proposal.status = ProposalStatus.ACCEPTED
    proposal.decided_by_id = actor.id
    proposal.decided_at = datetime.now(UTC)
    proposal.objective_id = objective.id
    await db.flush()
    return objective


async def reject_proposal(db: AsyncSession, proposal: ObjectiveProposal, *, actor: User) -> None:
    """Reject a pending proposal (it is kept, so the same wording is not proposed again)."""
    if proposal.status != ProposalStatus.PENDING:
        raise ConflictError("This proposal was decided already.")
    proposal.status = ProposalStatus.REJECTED
    proposal.decided_by_id = actor.id
    proposal.decided_at = datetime.now(UTC)
    await db.flush()
