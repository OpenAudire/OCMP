"""Mapping links and their review workflow.

Lifecycle of a link:

- AI suggestions and migrated links start as ``suggested``.
- A person reviewing a suggestion accepts it, rejects it, or sends it to a
  second reviewer. With the institution's four-eyes policy an accept also goes
  to a second reviewer, so a link only counts once two different people agreed.
  A first-stage reject is final unless the policy requires second review for
  rejects too.
- The second reviewer accepts or rejects. If that overturns the first
  reviewer's decision, the link is flagged for discussion.
- A rejected link can be reopened (returning it to ``suggested``) by someone
  allowed to review mappings for that objective.
- Links created by hand count as reviewed by their author (and need a second
  reviewer under four-eyes); imported links arrive accepted.

Policies come from ``mapping_policy_for`` (institution settings); callers pass
them in so a batch of reviews uses one consistent policy.
"""

import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models import AIRun, Framework, FrameworkItem, MappingLink, Objective, User
from app.models.mapping import (
    AcceptMethod,
    DepthMatch,
    MappingSource,
    MappingStatus,
    ReviewDecision,
)
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    has_permission,
)
from app.services.curriculum_scopes import objective_scope
from app.services.policies import MappingPolicy

DEFAULT_POLICY = MappingPolicy()


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _check_scores(coverage: int | None, confidence: Decimal | float | None) -> None:
    if coverage is not None and not 0 <= coverage <= 5:
        raise InvalidRequestError("Coverage must be between 0 and 5.")
    if confidence is not None and not 0 <= confidence <= 1:
        raise InvalidRequestError("Confidence must be between 0 and 1.")


async def create_link(
    db: AsyncSession,
    objective: Objective,
    item: FrameworkItem,
    *,
    source: MappingSource,
    creator: User | None = None,
    coverage: int | None = None,
    depth_match: DepthMatch | None = None,
    rationale: str = "",
    evidence_quote: str = "",
    confidence: Decimal | float | None = None,
    ai_run: AIRun | None = None,
    migrated_from: MappingLink | None = None,
    policy: MappingPolicy = DEFAULT_POLICY,
) -> MappingLink:
    """Record that an objective addresses a framework item.

    Raises:
        InvalidRequestError: For a deleted objective or framework, out-of-range
            scores, an AI link without its run or with a quote not taken from the
            objective, or a human link without its author.
        ConflictError: If the objective is already linked to the item.
    """
    if objective.is_deleted:
        raise InvalidRequestError("Cannot map a deleted objective.")
    framework = await db.get(Framework, item.framework_id)
    if framework is None or framework.is_deleted:
        raise InvalidRequestError("The framework has been deleted.")
    _check_scores(coverage, confidence)
    if source == MappingSource.AI:
        if ai_run is None:
            raise InvalidRequestError("AI suggestions must record their AI run.")
        if evidence_quote and _normalise(evidence_quote) not in _normalise(objective.text):
            raise InvalidRequestError("The evidence quote must be words from the objective.")
    if source == MappingSource.HUMAN and creator is None:
        raise InvalidRequestError("Links made by hand need their author.")
    if source == MappingSource.MIGRATED and migrated_from is None:
        raise InvalidRequestError("Migrated links must record the link they replace.")

    exists = await db.scalar(
        select(MappingLink.id).where(
            MappingLink.objective_id == objective.id, MappingLink.framework_item_id == item.id
        )
    )
    if exists:
        raise ConflictError("This objective is already linked to this item.")

    link = MappingLink(
        objective_id=objective.id,
        framework_item_id=item.id,
        source=source,
        coverage=coverage,
        depth_match=depth_match,
        rationale=rationale,
        evidence_quote=evidence_quote,
        confidence=Decimal(str(confidence)) if confidence is not None else None,
        ai_run_id=ai_run.id if ai_run else None,
        migrated_from_id=migrated_from.id if migrated_from else None,
        created_by_id=creator.id if creator else None,
    )
    now = datetime.now(UTC)
    if source == MappingSource.HUMAN:
        assert creator is not None
        link.first_reviewer_id = creator.id
        link.first_reviewed_at = now
        link.first_decision = ReviewDecision.ACCEPT
        if policy.four_eyes:
            link.status = MappingStatus.NEEDS_SECOND_REVIEW
        else:
            link.status = MappingStatus.ACCEPTED
            link.accept_method = AcceptMethod.INDIVIDUAL
    elif source == MappingSource.IMPORT:
        link.status = MappingStatus.ACCEPTED
        link.accept_method = AcceptMethod.IMPORTED
    else:
        link.status = MappingStatus.SUGGESTED
    db.add(link)
    await db.flush()
    return link


def _accept(link: MappingLink, method: AcceptMethod) -> None:
    link.status = MappingStatus.ACCEPTED
    link.accept_method = method


def _first_stage_status(decision: ReviewDecision, policy: MappingPolicy) -> MappingStatus | None:
    """Status after a first review; None means accepted."""
    if decision == ReviewDecision.SECOND_REVIEW:
        return MappingStatus.NEEDS_SECOND_REVIEW
    if decision == ReviewDecision.REJECT:
        if policy.second_review_for_rejects:
            return MappingStatus.NEEDS_SECOND_REVIEW
        return MappingStatus.REJECTED
    return MappingStatus.NEEDS_SECOND_REVIEW if policy.four_eyes else None


async def review_link(
    db: AsyncSession,
    link: MappingLink,
    reviewer: User,
    decision: ReviewDecision,
    *,
    policy: MappingPolicy = DEFAULT_POLICY,
    coverage: int | None = None,
    depth_match: DepthMatch | None = None,
    method: AcceptMethod = AcceptMethod.INDIVIDUAL,
) -> MappingLink:
    """Record a reviewer's decision, optionally correcting coverage and depth.

    Raises:
        InvalidRequestError: For out-of-range coverage, or asking for a second
            review at the second stage.
        ConflictError: If the link is already decided, or the second reviewer is
            the first reviewer.
    """
    _check_scores(coverage, None)
    now = datetime.now(UTC)

    if link.status == MappingStatus.SUGGESTED:
        link.first_reviewer_id = reviewer.id
        link.first_reviewed_at = now
        link.first_decision = decision
        status = _first_stage_status(decision, policy)
        if status is None:
            _accept(link, method)
        else:
            link.status = status
    elif link.status == MappingStatus.NEEDS_SECOND_REVIEW:
        # The author of a hand-made link counts as its first reviewer (ADR 016), also when
        # the suggestion was first reviewed by someone else.
        if reviewer.id == link.first_reviewer_id or (
            link.source == MappingSource.HUMAN and reviewer.id == link.created_by_id
        ):
            raise ConflictError("The second review must be done by someone else.")
        if decision == ReviewDecision.SECOND_REVIEW:
            raise InvalidRequestError("This is already the second review.")
        link.second_reviewer_id = reviewer.id
        link.second_reviewed_at = now
        if decision == ReviewDecision.ACCEPT:
            _accept(link, method)
        else:
            link.status = MappingStatus.REJECTED
        link.needs_discussion = (
            link.first_decision in (ReviewDecision.ACCEPT, ReviewDecision.REJECT)
            and link.first_decision != decision
        )
    else:
        raise ConflictError("This link has already been decided.")

    if coverage is not None:
        link.coverage = coverage
    if depth_match is not None:
        link.depth_match = depth_match
    await db.flush()
    return link


async def reopen_link(
    db: AsyncSession, actor: User, link: MappingLink, *, reason: str | None = None
) -> MappingLink:
    """Return a rejected link to ``suggested`` so it can be reviewed again.

    Recorded in the audit log as a ``mapping.reopen`` operation by ``actor``,
    with the reason given.

    Raises:
        AuthorizationError: If the actor may not review mappings for this objective.
        ConflictError: If the link is not rejected.
    """
    objective = await db.get(Objective, link.objective_id)
    assert objective is not None
    scope = await objective_scope(db, objective)
    if not await has_permission(db, actor, Permission.MAPPING_REVIEW, scope):
        raise AuthorizationError("You may not review mappings for this objective.")
    if link.status != MappingStatus.REJECTED:
        raise ConflictError("Only rejected links can be reopened.")

    with audit_operation("mapping.reopen", actor_id=actor.id, reason=reason):
        link.status = MappingStatus.SUGGESTED
        link.accept_method = None
        link.needs_discussion = False
        link.needs_recheck = False
        link.first_reviewer_id = link.second_reviewer_id = None
        link.first_reviewed_at = link.second_reviewed_at = None
        link.first_decision = None
        await db.flush()
    return link


async def confirm_recheck(
    db: AsyncSession, actor: User, link: MappingLink, *, reason: str | None = None
) -> MappingLink:
    """Confirm that an accepted link still fits after its objective's text changed.

    The link stays accepted and its reviewers are unchanged; only the "needs re-check"
    flag is cleared. Recorded in the audit log as ``mapping.recheck_confirm``.

    Raises:
        AuthorizationError: If the actor may not review mappings for this objective.
        ConflictError: If the link is not accepted or does not need a re-check.
    """
    objective = await db.get(Objective, link.objective_id)
    assert objective is not None
    scope = await objective_scope(db, objective)
    if not await has_permission(db, actor, Permission.MAPPING_REVIEW, scope):
        raise AuthorizationError("You may not review mappings for this objective.")
    if link.status != MappingStatus.ACCEPTED or not link.needs_recheck:
        raise ConflictError("This link does not need a re-check.")
    with audit_operation("mapping.recheck_confirm", actor_id=actor.id, reason=reason):
        link.needs_recheck = False
        await db.flush()
    return link


async def flag_for_recheck(db: AsyncSession, objective: Objective) -> int:
    """Mark the accepted links of an objective whose text changed as needing a re-check.

    Returns how many links were flagged. The links stay accepted.
    """
    links = await db.scalars(
        select(MappingLink).where(
            MappingLink.objective_id == objective.id,
            MappingLink.status == MappingStatus.ACCEPTED,
            MappingLink.needs_recheck.is_(False),
        )
    )
    flagged = 0
    for link in links:
        link.needs_recheck = True
        flagged += 1
    await db.flush()
    return flagged


async def bulk_accept(
    db: AsyncSession,
    reviewer: User,
    links: Iterable[MappingLink],
    *,
    min_confidence: Decimal | float,
    policy: MappingPolicy = DEFAULT_POLICY,
) -> list[MappingLink]:
    """Accept every suggestion at or above a confidence threshold, as one person.

    Links below the threshold, without a confidence, or not ``suggested`` are left alone.
    """
    _check_scores(None, min_confidence)
    threshold = Decimal(str(min_confidence))
    accepted = []
    for link in links:
        if (
            link.status == MappingStatus.SUGGESTED
            and link.confidence is not None
            and link.confidence >= threshold
        ):
            await review_link(
                db,
                link,
                reviewer,
                ReviewDecision.ACCEPT,
                policy=policy,
                method=AcceptMethod.BULK,
            )
            accepted.append(link)
    return accepted


async def links_for_objective(db: AsyncSession, objective_id: uuid.UUID) -> list[MappingLink]:
    """All mapping links of an objective."""
    result = await db.execute(
        select(MappingLink)
        .where(MappingLink.objective_id == objective_id)
        .order_by(MappingLink.created_at)
    )
    return list(result.scalars())
