"""The review queue: what waits for a reviewer, and accepting, rejecting and sending on (ADR 040).

The queue lists only links the user may review, in draft versions they may see, so it
reveals nothing the curriculum screens do not (ADR 027). Deciding on a link needs
``mapping.review`` for a first review and ``mapping.second_review`` for a second one, at the
objective's scope; a link the user cannot see is 404, one they can see but not decide on is 403.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser
from app.api.v1.curriculum_edit import not_found
from app.api.v1.curriculum_objectives import objective_scope_for
from app.core.database import DbSession
from app.core.permissions import Permission
from app.models import MappingLink, User
from app.models.mapping import MappingStatus
from app.schemas.mapping_review import (
    BulkAcceptRequest,
    BulkAcceptResult,
    QueueCounts,
    QueueSort,
    QueueStage,
    ReviewQueue,
    ReviewRequest,
    ReviewResult,
)
from app.services import mapping_review
from app.services.authorization import has_permission
from app.services.mapping_review import BULK_MAX_LINKS, BULK_MIN_CONFIDENCE, QueueFilter

router = APIRouter(tags=["mapping"])


@router.get("/mapping/review-queue", response_model=ReviewQueue)
async def get_review_queue(
    user: CurrentUser,
    db: DbSession,
    stage: QueueStage = QueueStage.FIRST,
    version_id: uuid.UUID | None = None,
    framework_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None,
    min_confidence: Annotated[Decimal | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[Decimal | None, Query(ge=0, le=1)] = None,
    sort: QueueSort = QueueSort.CONFIDENCE_DESC,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=mapping_review.MAX_PAGE)] = mapping_review.DEFAULT_PAGE,
) -> ReviewQueue:
    """One page of the links waiting for this user, with progress and the filter choices."""
    page = await mapping_review.review_queue(
        db,
        user,
        stage=stage,
        where=QueueFilter(version_id, framework_id, module_id, min_confidence, max_confidence),
        order=sort,
        offset=offset,
        limit=limit,
    )
    return ReviewQueue(
        stage=page.stage,
        total=page.total,
        offset=page.offset,
        limit=page.limit,
        items=page.items,
        progress=page.progress,
        counts=page.counts,
        facets=page.facets,
        four_eyes=page.four_eyes,
        bulk_min_confidence=float(BULK_MIN_CONFIDENCE),
        bulk_max_links=BULK_MAX_LINKS,
    )


@router.get("/mapping/review-queue/count", response_model=QueueCounts)
async def get_review_count(user: CurrentUser, db: DbSession) -> QueueCounts:
    """How many links wait for this user, for the sidebar."""
    return await mapping_review.waiting_counts(db, user)


@router.post("/mapping/review-queue/bulk-accept", response_model=BulkAcceptResult)
async def bulk_accept(
    body: BulkAcceptRequest, user: CurrentUser, db: DbSession
) -> BulkAcceptResult:
    """Accept the confident suggestions the user may review (or count them with ``dry_run``).

    Only first-stage suggestions at or above the chosen confidence (never below the minimum
    in the queue response) are handled, at most one batch at a time. In four-eyes mode each
    still waits for a different second reviewer."""
    outcome = await mapping_review.bulk_accept(
        db,
        user,
        min_confidence=body.min_confidence,
        where=QueueFilter(body.version_id, body.framework_id, body.module_id),
        dry_run=body.dry_run,
    )
    return BulkAcceptResult(
        eligible=outcome.eligible,
        processed=outcome.processed,
        remaining=outcome.eligible - outcome.processed,
        status_after=outcome.status_after,
        dry_run=body.dry_run,
    )


async def review_actor(
    link_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession
) -> User:
    """The signed-in user, who must hold the permission for the link's stage at its scope.

    Like ``require_permission``, but the permission depends on the stage: ``mapping.review``
    for a first review, ``mapping.second_review`` for a second one. A link the user cannot
    see (or a rejected or missing one) is 404.
    """
    link = await db.get(MappingLink, link_id)
    if link is None or link.status == MappingStatus.REJECTED:
        raise not_found("Link")
    scope = await objective_scope_for(request, db, user, link.objective_id)
    needed = (
        Permission.MAPPING_SECOND_REVIEW
        if link.status == MappingStatus.NEEDS_SECOND_REVIEW
        else Permission.MAPPING_REVIEW
    )
    if not await has_permission(db, user, needed, scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to do this."
        )
    return user


@router.post("/mapping-links/{link_id}/review", response_model=ReviewResult)
async def review_link(
    link_id: uuid.UUID,
    body: ReviewRequest,
    actor: Annotated[User, Depends(review_actor)],
    db: DbSession,
) -> ReviewResult:
    """Accept (optionally correcting coverage and depth), reject, or send to a second review.

    ``expected_status`` must be the status the person saw, so a link that moved on is a 409."""
    link = await db.get(MappingLink, link_id)
    assert link is not None
    await mapping_review.review(
        db,
        actor,
        link,
        body.decision,
        expected_status=body.expected_status,
        coverage=body.coverage,
        depth_match=body.depth_match,
    )
    return ReviewResult(id=link.id, status=link.status, needs_discussion=link.needs_discussion)
