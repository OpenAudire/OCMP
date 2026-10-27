"""The review queue: what waits for a reviewer, and deciding on it (ADR 040).

A link waits for a person in one of three ways:

- ``first``: a suggestion nobody has decided on (made by the AI or a migration, or by
  someone who may map but not review). Needs ``mapping.review`` at the objective's scope.
- ``second``: a first reviewer accepted it in four-eyes mode, or was unsure, or rejected it
  where rejects need a second look. Needs ``mapping.second_review``, and the second reviewer
  must be someone other than the first reviewer (and than the author of a hand-made link).
- ``recheck``: an accepted link whose objective's wording changed (ADR 032). Needs
  ``mapping.review``; confirmed with the existing "still fits" action.

Only objectives of draft versions that the user may see are listed (ADR 027, ADR 030).
What the user may review is decided per objective scope, from the permissions gathered once
per request, like the mapping workspace does.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.permissions import Permission, ScopeType
from app.models import (
    CurriculumVersion,
    Framework,
    FrameworkItem,
    Institution,
    LearningEvent,
    MappingLink,
    Module,
    Objective,
    User,
)
from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.mapping import (
    AcceptMethod,
    DepthMatch,
    MappingSource,
    MappingStatus,
    ReviewDecision,
)
from app.schemas.mapping_review import (
    FacetFramework,
    FacetModule,
    FacetVersion,
    QueueCounts,
    QueueFacets,
    QueueItemRef,
    QueueLink,
    QueueObjective,
    QueueProgress,
    QueueSort,
    QueueStage,
)
from app.services import mapping as mapping_service
from app.services.audit import audit_operation
from app.services.authorization import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    has_permission,
)
from app.services.curriculum_read import (
    CurriculumAccess,
    Permissions,
    VisibleVersion,
    curriculum_access,
    visible_version,
)
from app.services.curriculum_scopes import objective_scope
from app.services.mapping_links import ensure_objective_open
from app.services.policies import MappingPolicy, mapping_policy_for_version, parse_mapping_policy

# "Accept all" may not go below this confidence (the mockup calls under 65% "check carefully"),
# and handles at most this many links in one action, so each batch can be looked at (ADR 040).
BULK_MIN_CONFIDENCE = Decimal("0.800")
BULK_MAX_LINKS = 200
DEFAULT_PAGE = 50
MAX_PAGE = 100

_SUGGESTION_SOURCES = (MappingSource.AI, MappingSource.MIGRATED)


@dataclass(frozen=True)
class QueueRow:
    """One link the user may review, with just enough to filter, sort and count."""

    link_id: uuid.UUID
    status: MappingStatus
    needs_recheck: bool
    source: MappingSource
    confidence: Decimal | None
    created_by_id: uuid.UUID | None
    first_reviewer_id: uuid.UUID | None
    created_at: datetime
    version_id: uuid.UUID
    framework_id: uuid.UUID
    module_id: uuid.UUID | None
    module_code: str
    # The pile this link is in for the user, or None when it is not theirs to act on.
    stage: QueueStage | None


@dataclass(frozen=True)
class QueueData:
    rows: list[QueueRow]
    policy: MappingPolicy
    versions: dict[uuid.UUID, VisibleVersion]


def _own_work(
    user_id: uuid.UUID,
    first_reviewer_id: uuid.UUID | None,
    author_id: uuid.UUID | None,
    source: MappingSource,
) -> bool:
    """The user gave the first review, or wrote the hand-made link: not theirs to second."""
    return user_id == first_reviewer_id or (source == MappingSource.HUMAN and author_id == user_id)


def _held(
    visible: VisibleVersion,
    level: ObjectiveLevel,
    module_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
) -> Permissions | None:
    """The user's permissions at the objective's scope, or None if they cannot see it."""
    view = visible.view
    access = visible.access
    held = access.for_programme(visible.programme)
    if level == ObjectiveLevel.PROGRAMME:
        return held if view.full else None
    if module_id is None:
        return None
    if level == ObjectiveLevel.MODULE:
        if not view.shows_module(module_id):
            return None
    else:
        if event_id is None or not view.shows_event(module_id, event_id):
            return None
        held = held | access.at(ScopeType.LEARNING_EVENT, event_id)
    return held | access.at(ScopeType.MODULE, module_id)


async def institution_policy(db: AsyncSession) -> MappingPolicy:
    """The mapping policy of the institution (an install holds one)."""
    settings = await db.scalar(select(Institution.settings).limit(1))
    return parse_mapping_policy(settings or {})


async def load_queue(
    db: AsyncSession, user: User, *, with_decided: bool, access: CurriculumAccess | None = None
) -> QueueData:
    """Every link in a draft version that the user may see and has a review permission for.

    ``with_decided`` also loads the AI and migrated links that are already decided, which
    only the progress counts need.
    """
    access = access or await curriculum_access(db, user)
    waiting = or_(
        MappingLink.status.in_([MappingStatus.SUGGESTED, MappingStatus.NEEDS_SECOND_REVIEW]),
        and_(MappingLink.status == MappingStatus.ACCEPTED, MappingLink.needs_recheck.is_(True)),
    )
    relevant = (
        or_(
            waiting,
            and_(
                MappingLink.source.in_(_SUGGESTION_SOURCES),
                MappingLink.status.in_([MappingStatus.ACCEPTED, MappingStatus.REJECTED]),
            ),
        )
        if with_decided
        else waiting
    )
    event = aliased(LearningEvent)
    module = aliased(Module)
    result = await db.execute(
        select(
            MappingLink.id,
            MappingLink.status,
            MappingLink.needs_recheck,
            MappingLink.source,
            MappingLink.confidence,
            MappingLink.created_by_id,
            MappingLink.first_reviewer_id,
            MappingLink.created_at,
            Objective.version_id,
            Objective.level,
            event.id,
            module.id,
            module.code,
            FrameworkItem.framework_id,
        )
        .join(Objective, Objective.id == MappingLink.objective_id)
        .join(CurriculumVersion, CurriculumVersion.id == Objective.version_id)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .join(Framework, Framework.id == FrameworkItem.framework_id)
        .outerjoin(event, and_(event.id == Objective.learning_event_id, event.deleted_at.is_(None)))
        .outerjoin(
            module,
            and_(
                module.id == func.coalesce(Objective.module_id, event.module_id),
                module.deleted_at.is_(None),
            ),
        )
        .where(
            Objective.deleted_at.is_(None),
            CurriculumVersion.deleted_at.is_(None),
            CurriculumVersion.status == VersionStatus.DRAFT,
            Framework.deleted_at.is_(None),
            relevant,
        )
    )
    candidates = list(result)
    visible_by_version: dict[uuid.UUID, VisibleVersion | None] = {}
    for version_id in {row[8] for row in candidates}:
        visible_by_version[version_id] = await visible_version(db, access, version_id)

    rows: list[QueueRow] = []
    for (
        link_id,
        status,
        needs_recheck,
        source,
        confidence,
        created_by_id,
        first_reviewer_id,
        created_at,
        version_id,
        level,
        event_id,
        module_id,
        module_code,
        framework_id,
    ) in candidates:
        visible = visible_by_version.get(version_id)
        if visible is None:
            continue
        level = ObjectiveLevel(level)
        if level == ObjectiveLevel.LEARNING_EVENT and event_id is None:
            continue  # the session was deleted
        if level != ObjectiveLevel.PROGRAMME and module_id is None:
            continue  # the module was deleted
        held = _held(visible, level, module_id, event_id)
        if held is None:
            continue
        may_review = Permission.MAPPING_REVIEW in held
        may_second = Permission.MAPPING_SECOND_REVIEW in held
        if not (may_review or may_second):
            continue
        status = MappingStatus(status)
        source = MappingSource(source)
        stage: QueueStage | None = None
        if status == MappingStatus.SUGGESTED and may_review:
            stage = QueueStage.FIRST
        elif status == MappingStatus.NEEDS_SECOND_REVIEW and may_second:
            if not _own_work(user.id, first_reviewer_id, created_by_id, source):
                stage = QueueStage.SECOND
        elif status == MappingStatus.ACCEPTED and needs_recheck and may_review:
            stage = QueueStage.RECHECK
        rows.append(
            QueueRow(
                link_id=link_id,
                status=status,
                needs_recheck=needs_recheck,
                source=source,
                confidence=confidence,
                created_by_id=created_by_id,
                first_reviewer_id=first_reviewer_id,
                created_at=created_at,
                version_id=version_id,
                framework_id=framework_id,
                module_id=module_id,
                module_code=module_code or "",
                stage=stage,
            )
        )
    policy = await institution_policy(db)
    return QueueData(
        rows=rows,
        policy=policy,
        versions={k: v for k, v in visible_by_version.items() if v is not None},
    )


def counts_of(rows: list[QueueRow]) -> QueueCounts:
    tally = Counter(row.stage for row in rows if row.stage is not None)
    first, second, recheck = (
        tally[QueueStage.FIRST],
        tally[QueueStage.SECOND],
        tally[QueueStage.RECHECK],
    )
    return QueueCounts(first=first, second=second, recheck=recheck, total=first + second + recheck)


async def waiting_counts(db: AsyncSession, user: User) -> QueueCounts:
    """What waits for the user, for the sidebar."""
    return counts_of((await load_queue(db, user, with_decided=False)).rows)


@dataclass(frozen=True)
class QueueFilter:
    version_id: uuid.UUID | None = None
    framework_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    min_confidence: Decimal | None = None
    max_confidence: Decimal | None = None


def _in_scope(rows: list[QueueRow], where: QueueFilter) -> list[QueueRow]:
    return [
        row
        for row in rows
        if (where.version_id is None or row.version_id == where.version_id)
        and (where.framework_id is None or row.framework_id == where.framework_id)
        and (where.module_id is None or row.module_id == where.module_id)
    ]


def _confidence_ok(row: QueueRow, where: QueueFilter) -> bool:
    if where.min_confidence is None and where.max_confidence is None:
        return True
    if row.confidence is None:
        return False
    if where.min_confidence is not None and row.confidence < where.min_confidence:
        return False
    return where.max_confidence is None or row.confidence < where.max_confidence


def _sorted(rows: list[QueueRow], order: QueueSort) -> list[QueueRow]:
    # Links without a confidence (made by people) come last either way.
    if order == QueueSort.MODULE:
        return sorted(rows, key=lambda r: (r.module_code, r.created_at, str(r.link_id)))
    sign = -1 if order == QueueSort.CONFIDENCE_DESC else 1
    return sorted(
        rows,
        key=lambda r: (
            r.confidence is None,
            sign * (r.confidence if r.confidence is not None else Decimal(0)),
            r.created_at,
            str(r.link_id),
        ),
    )


def progress_of(rows: list[QueueRow]) -> QueueProgress:
    tally = Counter(row.status for row in rows)
    return QueueProgress(
        total=len(rows),
        accepted=tally[MappingStatus.ACCEPTED],
        rejected=tally[MappingStatus.REJECTED],
        second_review=tally[MappingStatus.NEEDS_SECOND_REVIEW],
        waiting=tally[MappingStatus.SUGGESTED],
    )


async def _facets(db: AsyncSession, data: QueueData) -> QueueFacets:
    version_ids = {row.version_id for row in data.rows}
    framework_ids = {row.framework_id for row in data.rows}
    module_ids = {row.module_id for row in data.rows if row.module_id}
    versions = [
        FacetVersion(
            id=v.version.id, programme_name=v.programme.name, academic_year=v.version.academic_year
        )
        for v in data.versions.values()
        if v.version.id in version_ids
    ]
    versions.sort(key=lambda v: (v.programme_name, -v.academic_year))
    frameworks = [
        FacetFramework(id=f.id, name=f.name, version_label=f.version_label)
        for f in await db.scalars(
            select(Framework).where(Framework.id.in_(framework_ids)).order_by(Framework.name)
        )
    ]
    modules = [
        FacetModule(id=m.id, code=m.code, name=m.name)
        for m in await db.scalars(
            select(Module).where(Module.id.in_(module_ids)).order_by(Module.code)
        )
    ]
    return QueueFacets(versions=versions, frameworks=frameworks, modules=modules)


async def _details(db: AsyncSession, data: QueueData, page: list[QueueRow]) -> list[QueueLink]:
    """The full cards for one page of the queue."""
    if not page:
        return []
    parent = aliased(FrameworkItem)
    module = aliased(Module)
    event = aliased(LearningEvent)
    result = await db.execute(
        select(MappingLink, Objective, FrameworkItem, Framework, parent, module, event)
        .join(Objective, Objective.id == MappingLink.objective_id)
        .join(FrameworkItem, FrameworkItem.id == MappingLink.framework_item_id)
        .join(Framework, Framework.id == FrameworkItem.framework_id)
        .outerjoin(parent, parent.id == FrameworkItem.parent_id)
        .outerjoin(event, event.id == Objective.learning_event_id)
        .outerjoin(module, module.id == func.coalesce(Objective.module_id, event.module_id))
        .where(MappingLink.id.in_([row.link_id for row in page]))
    )
    found = {row[0].id: row for row in result}
    cards: list[QueueLink] = []
    for row in page:
        link, objective, item, framework, group, mod, ev = found[row.link_id]
        assert row.stage is not None
        visible = data.versions[row.version_id]
        cards.append(
            QueueLink(
                id=link.id,
                stage=row.stage,
                status=link.status,
                source=link.source,
                confidence=float(link.confidence) if link.confidence is not None else None,
                coverage=link.coverage,
                depth_match=link.depth_match,
                rationale=link.rationale,
                evidence_quote=link.evidence_quote,
                needs_recheck=link.needs_recheck,
                needs_discussion=link.needs_discussion,
                first_decision=(link.first_decision if row.stage == QueueStage.SECOND else None),
                version_id=row.version_id,
                academic_year=visible.version.academic_year,
                objective=QueueObjective(
                    id=objective.id,
                    text=objective.text,
                    level=objective.level,
                    module_code=mod.code if mod else None,
                    module_name=mod.name if mod else None,
                    learning_event_title=ev.title if ev else None,
                ),
                item=QueueItemRef(
                    id=item.id,
                    code=item.code,
                    title=item.title,
                    group=f"{group.code} {group.title}" if group else None,
                    framework_id=framework.id,
                    framework_name=framework.name,
                    framework_version_label=framework.version_label,
                ),
            )
        )
    return cards


@dataclass(frozen=True)
class QueuePage:
    stage: QueueStage
    total: int
    offset: int
    limit: int
    items: list[QueueLink]
    progress: QueueProgress
    counts: QueueCounts
    facets: QueueFacets
    four_eyes: bool


async def review_queue(
    db: AsyncSession,
    user: User,
    *,
    stage: QueueStage,
    where: QueueFilter,
    order: QueueSort,
    offset: int,
    limit: int,
) -> QueuePage:
    """One page of the user's queue, with progress, counts per stage and filter choices."""
    data = await load_queue(db, user, with_decided=True)
    in_scope = _in_scope(data.rows, where)
    listed = _sorted([r for r in in_scope if r.stage == stage and _confidence_ok(r, where)], order)
    page = listed[offset : offset + limit]
    return QueuePage(
        stage=stage,
        total=len(listed),
        offset=offset,
        limit=limit,
        items=await _details(db, data, page),
        # Progress covers the suggestions of the scope, whatever stage or confidence is shown.
        progress=progress_of(in_scope),
        counts=counts_of(in_scope),
        facets=await _facets(db, data),
        four_eyes=data.policy.four_eyes,
    )


# --- Deciding -----------------------------------------------------------------------


def _operation(decision: ReviewDecision, status: MappingStatus, edited: bool) -> str:
    if decision == ReviewDecision.REJECT:
        return "mapping.review_reject"
    if decision == ReviewDecision.SECOND_REVIEW:
        return "mapping.review_send_second"
    stage = "second" if status == MappingStatus.NEEDS_SECOND_REVIEW else "first"
    return f"mapping.review_{stage}_accept_edited" if edited else f"mapping.review_{stage}_accept"


async def review(
    db: AsyncSession,
    actor: User,
    link: MappingLink,
    decision: ReviewDecision,
    *,
    expected_status: MappingStatus,
    coverage: int | None = None,
    depth_match: DepthMatch | None = None,
) -> MappingLink:
    """Accept, reject or send on one link, optionally correcting coverage and depth.

    The permission follows the stage: ``mapping.review`` for a first review and
    ``mapping.second_review`` for a second one, both at the objective's scope. Four-eyes
    rules are in :func:`app.services.mapping.review_link`.

    Raises:
        AuthorizationError: Without the permission for this stage.
        ConflictError: If the link is no longer in the status the person saw, is already
            decided, is in a version that is not a draft, or the second reviewer is the
            first reviewer.
        InvalidRequestError: For corrections with anything but an accept, or an accept
            without a coverage and a depth.
    """
    objective = await db.get(Objective, link.objective_id)
    assert objective is not None
    await ensure_objective_open(db, objective)
    if link.status != expected_status:
        raise ConflictError("This link changed while you were looking at it. Reload the queue.")
    if link.status == MappingStatus.SUGGESTED:
        needed = Permission.MAPPING_REVIEW
    elif link.status == MappingStatus.NEEDS_SECOND_REVIEW:
        needed = Permission.MAPPING_SECOND_REVIEW
    else:
        raise ConflictError("This link has already been decided.")
    if not await has_permission(db, actor, needed, await objective_scope(db, objective)):
        raise AuthorizationError("You may not review this link.")
    if decision != ReviewDecision.ACCEPT and (coverage is not None or depth_match is not None):
        raise InvalidRequestError("Coverage and depth can only be changed when accepting.")
    if decision == ReviewDecision.ACCEPT and (
        (coverage if coverage is not None else link.coverage) is None
        or (depth_match if depth_match is not None else link.depth_match) is None
    ):
        raise InvalidRequestError("Choose a coverage and a depth before accepting.")

    edited = (coverage is not None and coverage != link.coverage) or (
        depth_match is not None and depth_match != link.depth_match
    )
    policy = await mapping_policy_for_version(db, objective.version_id)
    with audit_operation(_operation(decision, link.status, edited), actor_id=actor.id):
        await mapping_service.review_link(
            db,
            link,
            actor,
            decision,
            policy=policy,
            coverage=coverage,
            depth_match=depth_match,
            method=AcceptMethod.INDIVIDUAL,
        )
    return link


@dataclass(frozen=True)
class BulkOutcome:
    eligible: int
    processed: int
    status_after: MappingStatus


async def bulk_accept(
    db: AsyncSession,
    actor: User,
    *,
    min_confidence: Decimal,
    where: QueueFilter,
    dry_run: bool,
) -> BulkOutcome:
    """Accept the high-confidence suggestions the actor may review, in one action.

    Safety rules (ADR 040): the confidence must be at least ``BULK_MIN_CONFIDENCE``; only
    first-stage suggestions with a confidence, a coverage and a depth are touched, never a
    second review and never a re-check; the actor's own links are skipped; at most
    ``BULK_MAX_LINKS`` are handled at once, the most confident first; and in four-eyes mode
    the accept is a first review, so each link still waits for a different second reviewer.

    Raises:
        InvalidRequestError: If the threshold is below the allowed minimum.
    """
    if min_confidence < BULK_MIN_CONFIDENCE:
        raise InvalidRequestError(
            f"Accept all works from {int(BULK_MIN_CONFIDENCE * 100)}% confidence upwards."
        )
    data = await load_queue(db, actor, with_decided=False)
    eligible = _sorted(
        [
            row
            for row in _in_scope(data.rows, where)
            if row.stage == QueueStage.FIRST
            and row.source != MappingSource.HUMAN
            and row.confidence is not None
            and row.confidence >= min_confidence
            and row.created_by_id != actor.id
        ],
        QueueSort.CONFIDENCE_DESC,
    )
    status_after = (
        MappingStatus.NEEDS_SECOND_REVIEW if data.policy.four_eyes else MappingStatus.ACCEPTED
    )
    batch = eligible[:BULK_MAX_LINKS]
    if dry_run or not batch:
        return BulkOutcome(len(eligible), 0 if dry_run else len(batch), status_after)

    links = {
        link.id: link
        for link in await db.scalars(
            select(MappingLink).where(MappingLink.id.in_([row.link_id for row in batch]))
        )
    }
    processed = 0
    with audit_operation(
        "mapping.review_bulk_accept",
        actor_id=actor.id,
        reason=f"{len(batch)} suggestions at {int(min_confidence * 100)}% confidence and above",
    ):
        for row in batch:
            link = links[row.link_id]
            if (
                link.status != MappingStatus.SUGGESTED
                or link.coverage is None
                or link.depth_match is None
            ):
                continue
            await mapping_service.review_link(
                db,
                link,
                actor,
                ReviewDecision.ACCEPT,
                policy=data.policy,
                method=AcceptMethod.BULK,
            )
            processed += 1
    return BulkOutcome(len(eligible), processed, status_after)
