"""Institution policies stored in ``institutions.settings``.

Settings are JSON so administrators can change them without migrations; this
module gives each group of settings a typed, validated shape with defaults.
"""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, Faculty, Institution, Objective, Programme
from app.services.authorization import InvalidRequestError


class MappingPolicy(BaseModel):
    """How mapping decisions are reviewed (``settings["mapping"]``)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # Accepted links need a second, different reviewer before they count.
    four_eyes: bool = False
    # Rejections also need a second reviewer (by default a first reject is final).
    second_review_for_rejects: bool = False
    # "Accept all" never goes below this confidence (percent) and handles at most this many
    # links in one action (ADR 040). The limits are the allowed range for admins to choose from.
    bulk_accept_min_percent: Annotated[int, Field(ge=50, le=100)] = 80
    bulk_accept_max_links: Annotated[int, Field(ge=1, le=1000)] = 200
    # AI mapping runs (ADR 045): a suggestion covering less than this (0 to 5 scale) is dropped,
    # and when a more specific item (a child) is suggested its parent is not. Reviewers can
    # still link a parent by hand. 1.19 measures the best minimum coverage.
    ai_min_coverage: Annotated[int, Field(ge=1, le=5)] = 1
    ai_prefer_specific_item: bool = True


class CreditPolicy(BaseModel):
    """Credits and notional hours checks (``settings["credits"]``); advice only (brief, 9)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # One credit stands for this many notional hours.
    hours_per_credit: Annotated[int, Field(ge=1, le=100)] = 10
    # A module's planned hours may differ from credits x hours per credit by this much.
    tolerance_percent: Annotated[int, Field(ge=0, le=100)] = 10
    # Typical credits of an academic year (phases of kind "year").
    credits_per_year: Annotated[int, Field(ge=1, le=10_000)] = 120
    # Credits wanted at the programme's NQF exit level; null = not checked.
    min_exit_level_credits: Annotated[int, Field(ge=0, le=10_000)] | None = None


class CoveragePolicy(BaseModel):
    """How coverage is worked out in the reports (``settings["coverage"]``, ADR 050)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # Multiple match: an item is covered when it has at least this many accepted links.
    multiple_match_n: Annotated[int, Field(ge=1, le=20)] = 3
    # Subordinate match: the gap report lists the groups under this share of items covered.
    subordinate_min_percent: Annotated[int, Field(ge=1, le=100)] = 50
    # Weighted coverage: the gap report lists the items under this share of full coverage.
    weighted_low_percent: Annotated[int, Field(ge=1, le=100)] = 40
    # The report on items taught in many sessions (ADR 053): an item is listed from at least
    # this many sessions ...
    repeat_min_sessions: Annotated[int, Field(ge=2, le=100)] = 4
    # ... and, once five or more items are taught, from the average plus this many standard
    # deviations of the sessions per item.
    repeat_spread: Annotated[float, Field(ge=0, le=5)] = 1.5


class ExplorerPolicy(BaseModel):
    """What the student explorer may show (``settings["explorer"]``, ADR 061)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # Show "where this year builds each competency": the modules and sessions of a published
    # version linked (accepted links only) to the groups of a framework. Off until the
    # institution decides to show students its mapping.
    show_competency_view: bool = False


# Pairs below this similarity are never stored (ADR 044), so it is also the lowest threshold
# an admin can choose. Set from the measurements recorded in the ADR.
NEAR_DUPLICATE_FLOOR_PERCENT = 85
NEAR_DUPLICATE_DEFAULT_PERCENT = 95


class QualityPolicy(BaseModel):
    """Wording checks that depend on the institution (``settings["quality"]``); advice only."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # Two objectives of one version and level at least this similar (percent, by meaning)
    # are reported as near-duplicates (ADR 044).
    near_duplicate_min_percent: Annotated[int, Field(ge=NEAR_DUPLICATE_FLOOR_PERCENT, le=100)] = (
        NEAR_DUPLICATE_DEFAULT_PERCENT
    )


def parse_quality_policy(settings: dict[str, object]) -> QualityPolicy:
    """Read the quality policy from an institution's settings.

    Raises:
        InvalidRequestError: If the stored settings have the wrong shape.
    """
    try:
        return QualityPolicy.model_validate(settings.get("quality") or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid quality settings: {exc}") from exc


async def quality_policy_for_version(db: AsyncSession, version_id: uuid.UUID) -> QualityPolicy:
    """The quality policy of the institution a curriculum version belongs to."""
    settings = await db.scalar(
        select(Institution.settings)
        .join(Faculty, Faculty.institution_id == Institution.id)
        .join(Programme, Programme.faculty_id == Faculty.id)
        .join(CurriculumVersion, CurriculumVersion.programme_id == Programme.id)
        .where(CurriculumVersion.id == version_id)
    )
    return parse_quality_policy(settings or {})


def parse_mapping_policy(settings: dict[str, object]) -> MappingPolicy:
    """Read the mapping policy from an institution's settings.

    Raises:
        InvalidRequestError: If the stored settings have the wrong shape.
    """
    try:
        return MappingPolicy.model_validate(settings.get("mapping") or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid mapping settings: {exc}") from exc


async def mapping_policy_for_version(db: AsyncSession, version_id: uuid.UUID) -> MappingPolicy:
    """The mapping policy of the institution a curriculum version belongs to."""
    settings = await db.scalar(
        select(Institution.settings)
        .join(Faculty, Faculty.institution_id == Institution.id)
        .join(Programme, Programme.faculty_id == Faculty.id)
        .join(CurriculumVersion, CurriculumVersion.programme_id == Programme.id)
        .where(CurriculumVersion.id == version_id)
    )
    return parse_mapping_policy(settings or {})


async def mapping_policy_for(db: AsyncSession, objective: Objective) -> MappingPolicy:
    """The mapping policy of the institution an objective belongs to."""
    return await mapping_policy_for_version(db, objective.version_id)


def parse_explorer_policy(settings: dict[str, object]) -> ExplorerPolicy:
    """Read the explorer policy from an institution's settings.

    Raises:
        InvalidRequestError: If the stored settings have the wrong shape.
    """
    try:
        return ExplorerPolicy.model_validate(settings.get("explorer") or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid explorer settings: {exc}") from exc


async def explorer_policy_for_version(db: AsyncSession, version_id: uuid.UUID) -> ExplorerPolicy:
    """The explorer policy of the institution a curriculum version belongs to."""
    settings = await db.scalar(
        select(Institution.settings)
        .join(Faculty, Faculty.institution_id == Institution.id)
        .join(Programme, Programme.faculty_id == Faculty.id)
        .join(CurriculumVersion, CurriculumVersion.programme_id == Programme.id)
        .where(CurriculumVersion.id == version_id)
    )
    return parse_explorer_policy(settings or {})


def parse_coverage_policy(settings: dict[str, object]) -> CoveragePolicy:
    """Read the coverage policy from an institution's settings.

    Raises:
        InvalidRequestError: If the stored settings have the wrong shape.
    """
    try:
        return CoveragePolicy.model_validate(settings.get("coverage") or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid coverage settings: {exc}") from exc


async def coverage_policy_for_version(db: AsyncSession, version_id: uuid.UUID) -> CoveragePolicy:
    """The coverage policy of the institution a curriculum version belongs to."""
    settings = await db.scalar(
        select(Institution.settings)
        .join(Faculty, Faculty.institution_id == Institution.id)
        .join(Programme, Programme.faculty_id == Faculty.id)
        .join(CurriculumVersion, CurriculumVersion.programme_id == Programme.id)
        .where(CurriculumVersion.id == version_id)
    )
    return parse_coverage_policy(settings or {})
