"""Schemas for the review queue (ADR 040). No reviewer or author names are returned."""

import uuid
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.curriculum import ObjectiveLevel
from app.models.mapping import DepthMatch, MappingSource, MappingStatus, ReviewDecision


class QueueStage(StrEnum):
    """Which pile of work a link belongs to for the person looking at the queue."""

    FIRST = "first"  # a suggestion nobody has decided on yet
    SECOND = "second"  # waiting for a second reviewer
    RECHECK = "recheck"  # accepted, but the objective's wording changed since


class QueueSort(StrEnum):
    CONFIDENCE_DESC = "confidence_desc"
    CONFIDENCE_ASC = "confidence_asc"
    MODULE = "module"


class QueueObjective(BaseModel):
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    module_code: str | None
    module_name: str | None
    learning_event_title: str | None


class QueueItemRef(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    # The framework item above it, as "code title"; None for a top-level item.
    group: str | None
    framework_id: uuid.UUID
    framework_name: str
    framework_version_label: str


class QueueLink(BaseModel):
    id: uuid.UUID
    stage: QueueStage
    status: MappingStatus
    source: MappingSource
    confidence: float | None
    coverage: int | None
    depth_match: DepthMatch | None
    rationale: str
    evidence_quote: str
    needs_recheck: bool
    needs_discussion: bool
    # What the first reviewer decided (second stage only); never who.
    first_decision: ReviewDecision | None
    version_id: uuid.UUID
    academic_year: int
    objective: QueueObjective
    item: QueueItemRef


class QueueProgress(BaseModel):
    """Suggestions in the chosen scope (version, framework, module) that the user may review."""

    total: int
    accepted: int
    rejected: int
    second_review: int
    waiting: int


class QueueCounts(BaseModel):
    """What waits for this user, per stage (the sidebar shows the total)."""

    first: int
    second: int
    recheck: int
    total: int


class FacetVersion(BaseModel):
    id: uuid.UUID
    programme_name: str
    academic_year: int


class FacetFramework(BaseModel):
    id: uuid.UUID
    name: str
    version_label: str


class FacetModule(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class QueueFacets(BaseModel):
    versions: list[FacetVersion]
    frameworks: list[FacetFramework]
    modules: list[FacetModule]


class ReviewQueue(BaseModel):
    stage: QueueStage
    total: int
    offset: int
    limit: int
    items: list[QueueLink]
    progress: QueueProgress
    counts: QueueCounts
    facets: QueueFacets
    # The institution's four-eyes mode: an accept waits for a second, different reviewer.
    four_eyes: bool
    # The lowest confidence "accept all" may use, and the most links one action handles.
    bulk_min_confidence: float
    bulk_max_links: int


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    # The status the person saw. A link that moved on meanwhile is refused (409), so a
    # first review can never become a second review by accident.
    expected_status: MappingStatus
    # Corrections made while accepting (edit and accept).
    coverage: int | None = Field(default=None, ge=0, le=5)
    depth_match: DepthMatch | None = None


class ReviewResult(BaseModel):
    id: uuid.UUID
    status: MappingStatus
    needs_discussion: bool


class BulkAcceptRequest(BaseModel):
    min_confidence: Decimal = Field(ge=0, le=1, decimal_places=3)
    version_id: uuid.UUID | None = None
    framework_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    # Count what would happen without changing anything.
    dry_run: bool = False


class BulkAcceptResult(BaseModel):
    # Suggestions that meet the rules; at most `bulk_max_links` are handled in one go.
    eligible: int
    processed: int
    remaining: int
    # What the processed links became: accepted, or (four-eyes mode) waiting for a second reviewer.
    status_after: MappingStatus
    dry_run: bool
