"""Making, changing and removing mapping links by hand (ADR 039).

The review workflow of links already made (accept, reject, second review) is in
``mapping``; this module is what the mapping workspace uses. Rules:

- Only objectives of draft versions can be mapped or re-mapped (ADR 030).
- A person who may review mappings (``mapping.review``) at the objective's scope has their
  own link accepted at once, or sent to a second reviewer when the institution uses
  four-eyes mode. Anyone else with ``mapping.edit`` makes a suggestion that a reviewer
  decides on later (Slice 1.13).
- Changing coverage, depth or the reason of a link is a new claim. By a reviewer it is
  accepted again (or goes to a second reviewer under four-eyes mode); by anyone else the
  link goes back to ``suggested``. The "wording changed" flag is cleared only by
  confirming the link (``mapping.confirm_recheck``), never by an edit.
- Adding a link for a pair whose earlier link was rejected reopens that row.
- Removing a link made by a person or imported deletes it; a link the AI suggested or a
  migration made is rejected instead, so it stays as an example (ADR 016).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, Framework, FrameworkItem, MappingLink, Objective, User
from app.models.mapping import (
    AcceptMethod,
    DepthMatch,
    MappingSource,
    MappingStatus,
    ReviewDecision,
)
from app.services.authorization import AuthorizationError, ConflictError, InvalidRequestError
from app.services.curriculum_edit import ensure_editable
from app.services.policies import MappingPolicy

COVERAGE_MIN = 0
COVERAGE_MAX = 5
RATIONALE_MAX = 1000


def _checked(coverage: int, rationale: str) -> str:
    if not COVERAGE_MIN <= coverage <= COVERAGE_MAX:
        raise InvalidRequestError("Coverage must be between 0 and 5.")
    text = rationale.strip()
    if len(text) > RATIONALE_MAX:
        raise InvalidRequestError(f"The reason can be at most {RATIONALE_MAX} characters.")
    return text


async def ensure_objective_open(db: AsyncSession, objective: Objective) -> None:
    if objective.is_deleted:
        raise InvalidRequestError("Cannot map a deleted objective.")
    version = await db.get(CurriculumVersion, objective.version_id)
    assert version is not None
    ensure_editable(version)


def _decide_as_reviewer(link: MappingLink, reviewer: User, policy: MappingPolicy) -> None:
    """The author may review: their link counts as their own first review."""
    link.first_reviewer_id = reviewer.id
    link.first_reviewed_at = datetime.now(UTC)
    link.first_decision = ReviewDecision.ACCEPT
    link.second_reviewer_id = None
    link.second_reviewed_at = None
    link.needs_discussion = False
    if policy.four_eyes:
        link.status = MappingStatus.NEEDS_SECOND_REVIEW
        link.accept_method = None
    else:
        link.status = MappingStatus.ACCEPTED
        link.accept_method = AcceptMethod.INDIVIDUAL


def _suggest(link: MappingLink) -> None:
    """Back to a suggestion nobody has decided on yet."""
    link.status = MappingStatus.SUGGESTED
    link.accept_method = None
    link.first_reviewer_id = link.second_reviewer_id = None
    link.first_reviewed_at = link.second_reviewed_at = None
    link.first_decision = None
    link.needs_discussion = False


async def add_link(
    db: AsyncSession,
    objective: Objective,
    item: FrameworkItem,
    author: User,
    *,
    can_review: bool,
    policy: MappingPolicy,
    coverage: int,
    depth_match: DepthMatch,
    rationale: str = "",
) -> MappingLink:
    """Link an objective to a framework item by hand.

    Raises:
        InvalidRequestError: For a deleted objective or framework, or values out of range.
        ConflictError: For a published or archived version, or if the pair is linked already.
    """
    reason = _checked(coverage, rationale)
    await ensure_objective_open(db, objective)
    framework = await db.get(Framework, item.framework_id)
    if framework is None or framework.is_deleted:
        raise InvalidRequestError("The framework has been deleted.")

    link = await db.scalar(
        select(MappingLink).where(
            MappingLink.objective_id == objective.id, MappingLink.framework_item_id == item.id
        )
    )
    if link is not None and link.status != MappingStatus.REJECTED:
        raise ConflictError("This objective is already linked to this item.")
    if link is None:
        link = MappingLink(
            objective_id=objective.id,
            framework_item_id=item.id,
            source=MappingSource.HUMAN,
            created_by_id=author.id,
        )
        db.add(link)
    else:
        # A rejected row is reopened as this person's own claim; the AI's words go.
        link.source = MappingSource.HUMAN
        link.confidence = None
        link.evidence_quote = ""
        link.needs_recheck = False
    link.coverage = coverage
    link.depth_match = depth_match
    link.rationale = reason
    if can_review:
        _decide_as_reviewer(link, author, policy)
    else:
        _suggest(link)
    await db.flush()
    return link


@dataclass(frozen=True)
class LinkChange:
    coverage: int
    depth_match: DepthMatch
    rationale: str


async def update_link(
    db: AsyncSession,
    link: MappingLink,
    editor: User,
    change: LinkChange,
    *,
    can_review: bool,
    policy: MappingPolicy,
) -> MappingLink:
    """Change a link's coverage, depth and reason. See the module notes for its status.

    Raises:
        InvalidRequestError: For values out of range.
        ConflictError: For a published or archived version, or a rejected link.
    """
    reason = _checked(change.coverage, change.rationale)
    objective = await db.get(Objective, link.objective_id)
    assert objective is not None
    await ensure_objective_open(db, objective)
    if link.status == MappingStatus.REJECTED:
        raise ConflictError("A rejected link cannot be changed. Add the link again instead.")
    if (link.coverage, link.depth_match, link.rationale) == (
        change.coverage,
        change.depth_match,
        reason,
    ):
        return link
    link.coverage = change.coverage
    link.depth_match = change.depth_match
    link.rationale = reason
    if can_review:
        _decide_as_reviewer(link, editor, policy)
    else:
        _suggest(link)
    await db.flush()
    return link


async def remove_link(db: AsyncSession, link: MappingLink, *, can_review: bool) -> bool:
    """Remove a link. Returns True if the row was deleted, False if it was rejected.

    Raises:
        AuthorizationError: For a link the AI or a migration made, without ``mapping.review``.
        ConflictError: For a published or archived version, or a link that is already rejected.
    """
    objective = await db.get(Objective, link.objective_id)
    assert objective is not None
    await ensure_objective_open(db, objective)
    if link.status == MappingStatus.REJECTED:
        raise ConflictError("This link is already rejected.")
    if link.source in (MappingSource.AI, MappingSource.MIGRATED):
        if not can_review:
            raise AuthorizationError("Only a reviewer may reject a suggestion of the system.")
        link.status = MappingStatus.REJECTED
        link.accept_method = None
        link.needs_recheck = False
        await db.flush()
        return False
    await db.delete(link)
    await db.flush()
    return True
