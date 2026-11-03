"""Mappings between objectives and framework items, AI runs, and review assignments."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Audited, CoreModel, SoftDeleteMixin, live_unique, str_enum


class AIRunType(StrEnum):
    MAPPING = "mapping"
    EXTRACTION = "extraction"
    REWRITE = "rewrite"
    MIGRATION = "migration"
    QA = "qa"
    CLASSIFICATION = "classification"
    CONNECTION_TEST = "connection_test"  # the admin's "test connection" button (ADR 042)


class AIRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"


class DepthMatch(StrEnum):
    """How the objective's Bloom/Miller level compares with the level the item expects.

    ``not_applicable`` is for items with no stated or implied depth (keywords, topic lists);
    it carries no penalty (ADR 039). The brief listed the first three values.
    """

    BELOW = "below"
    MATCHES = "matches"
    ABOVE = "above"
    NOT_APPLICABLE = "not_applicable"


class MappingSource(StrEnum):
    AI = "ai"
    HUMAN = "human"
    IMPORT = "import"
    MIGRATED = "migrated"


class MappingStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_SECOND_REVIEW = "needs_second_review"


class AcceptMethod(StrEnum):
    INDIVIDUAL = "individual"  # a person reviewed this link
    BULK = "bulk"  # a person accepted it in a bulk action above a confidence threshold
    AUTOMATIC = "automatic"  # accepted by an admin-enabled threshold, no person (AI-accepted)
    IMPORTED = "imported"  # decided by people in another tool, then imported


class ReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    SECOND_REVIEW = "second_review"  # unsure: ask a second reviewer


class ReviewStage(StrEnum):
    FIRST = "first"
    SECOND = "second"


class AssignmentStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class AIRun(CoreModel):
    """One AI job (e.g. map these modules to that framework), with its cost.

    Inputs are built only from curriculum entities; personal data is never sent
    (see the privacy guard). Runs are never deleted (a database trigger refuses
    it), so every AI-made link stays traceable to the run that produced it.
    """

    __tablename__ = "ai_runs"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="token_counts_positive"),
        CheckConstraint("estimated_cost >= 0", name="cost_positive"),
        CheckConstraint(
            "total_items >= 0 AND done_items >= 0 AND failed_items >= 0 AND links_created >= 0",
            name="progress_positive",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finished_after_started",
        ),
    )

    type: Mapped[AIRunType] = mapped_column(str_enum(AIRunType, "ai_run_type"), index=True)
    status: Mapped[AIRunStatus] = mapped_column(
        str_enum(AIRunStatus, "ai_run_status"),
        default=AIRunStatus.QUEUED,
        server_default=AIRunStatus.QUEUED.value,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    # Temperature, top-k shortlist size, etc.
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    # What the run covered, e.g. {"module_ids": [...], "framework_id": "..."}.
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Estimated cost in US dollars.
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal(0), server_default="0"
    )
    # Progress of a mapping run (Slice 1.16): objectives to do, finished, failed, and the
    # suggestions made. Zero for runs that are not made of items.
    total_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_items: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    links_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    calls: Mapped[list["AIRunCall"]] = relationship(back_populates="run", lazy="raise")


class AIRunCall(CoreModel):
    """One request to the AI provider within a run: prompt and response, kept for audit.

    Never deleted. Retention clears the prompt and response text
    (``content_purged_at``) and keeps the rest: tokens, timing, validity.
    """

    __tablename__ = "ai_run_calls"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="token_counts_positive"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_positive"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), index=True
    )
    # The messages sent (after the privacy guard) and the raw response text;
    # emptied by retention.
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response: Mapped[str | None] = mapped_column(Text, default=None)
    content_purged_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # Whether the response passed schema validation (one retry is allowed).
    valid: Mapped[bool | None] = mapped_column(Boolean, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    run: Mapped[AIRun] = relationship(back_populates="calls", lazy="raise")


class MappingLink(Audited, SoftDeleteMixin, CoreModel):
    """A claim that an objective addresses a framework item, and how well.

    One row per live (objective, framework item): its status changes as people review
    it, and rejected rows are kept as examples for later AI runs.

    A link is soft-deleted with its objective, with the same ``deleted_at`` (ADR 043); a link
    a person removes is deleted for good. Reads go through ``app.services.mapping_live``.
    """

    __tablename__ = "mapping_links"
    __table_args__ = (
        live_unique("uq_mapping_links_objective_item_live", "objective_id", "framework_item_id"),
        CheckConstraint("coverage IS NULL OR coverage BETWEEN 0 AND 5", name="coverage_range"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        CheckConstraint(
            "second_reviewer_id IS NULL OR first_reviewer_id IS NULL"
            " OR second_reviewer_id <> first_reviewer_id",
            name="four_eyes",
        ),
        CheckConstraint(
            "(status = 'accepted') = (accept_method IS NOT NULL)", name="accept_method_iff_accepted"
        ),
        CheckConstraint("source <> 'ai' OR ai_run_id IS NOT NULL", name="ai_links_have_run"),
    )

    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )
    framework_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), index=True
    )
    # 0 (none) to 5 (fully covered); unknown for some imports until reviewed.
    coverage: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    depth_match: Mapped[DepthMatch | None] = mapped_column(
        str_enum(DepthMatch, "depth_match"), default=None
    )
    rationale: Mapped[str] = mapped_column(Text, default="", server_default="")
    evidence_quote: Mapped[str] = mapped_column(Text, default="", server_default="")
    source: Mapped[MappingSource] = mapped_column(str_enum(MappingSource, "mapping_source"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), default=None)
    status: Mapped[MappingStatus] = mapped_column(
        str_enum(MappingStatus, "mapping_status"),
        default=MappingStatus.SUGGESTED,
        server_default=MappingStatus.SUGGESTED.value,
        index=True,
    )
    accept_method: Mapped[AcceptMethod | None] = mapped_column(
        str_enum(AcceptMethod, "accept_method"), default=None
    )
    # Second reviewer overturned the first decision: discuss before relying on it.
    needs_discussion: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # The objective's text changed after this link was reviewed: still accepted, but a
    # person should confirm it still fits (ADR 032). Reports must show it.
    needs_recheck: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    first_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    first_reviewed_at: Mapped[datetime | None] = mapped_column(default=None)
    first_decision: Mapped[ReviewDecision | None] = mapped_column(
        str_enum(ReviewDecision, "review_decision"), default=None
    )
    second_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    second_reviewed_at: Mapped[datetime | None] = mapped_column(default=None)
    # Required for AI links; runs cannot be deleted, so the link stays traceable.
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), default=None, index=True
    )
    # For links moved to a new framework version: the link they replace.
    migrated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mapping_links.id", ondelete="SET NULL"), default=None, index=True
    )


class ReviewAssignment(Audited, CoreModel):
    """Mapping review work given to a person: a version (or one module) against a framework."""

    __tablename__ = "review_assignments"
    __table_args__ = (
        UniqueConstraint(
            "reviewer_id",
            "version_id",
            "module_id",
            "framework_id",
            "stage",
            postgresql_nulls_not_distinct=True,
            name="uq_review_assignments_work",
        ),
    )

    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    # None means every module (and the programme outcomes) of the version.
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), default=None, index=True
    )
    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frameworks.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[ReviewStage] = mapped_column(
        str_enum(ReviewStage, "review_stage"),
        default=ReviewStage.FIRST,
        server_default=ReviewStage.FIRST.value,
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        str_enum(AssignmentStatus, "assignment_status"),
        default=AssignmentStatus.OPEN,
        server_default=AssignmentStatus.OPEN.value,
    )
    due_date: Mapped[date | None] = mapped_column(default=None)
