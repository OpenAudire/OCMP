"""Curriculum structure: programme > version > phase > module > learning event, and objectives.

Programme-level outcomes belong to a curriculum version (not the programme),
so they are versioned and copied forward with the rest of the curriculum.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
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
from app.models.institution import Faculty


class ProgrammeStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PHASING_OUT = "phasing_out"
    DISCONTINUED = "discontinued"


class AccreditationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    IN_PROGRESS = "in_progress"
    ACCREDITED = "accredited"
    CONDITIONAL = "conditional"
    WITHDRAWN = "withdrawn"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PhaseKind(StrEnum):
    YEAR = "year"
    PHASE = "phase"
    BLOCK = "block"
    LONGITUDINAL_THREAD = "longitudinal_thread"


class ObjectiveLevel(StrEnum):
    PROGRAMME = "programme"
    MODULE = "module"
    LEARNING_EVENT = "learning_event"


# Higher rank = broader. Links always point from a narrower to a broader objective.
OBJECTIVE_LEVEL_RANK = {
    ObjectiveLevel.LEARNING_EVENT: 0,
    ObjectiveLevel.MODULE: 1,
    ObjectiveLevel.PROGRAMME: 2,
}


class ObjectiveDomain(StrEnum):
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    ATTITUDE = "attitude"


class ObjectiveStatus(StrEnum):
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    RETIRED = "retired"


class QualificationType(Audited, CoreModel):
    """HEQSF qualification type: an editable configuration table, seeded with defaults."""

    __tablename__ = "qualification_types"
    __table_args__ = (
        CheckConstraint("nqf_exit_level BETWEEN 1 AND 10", name="nqf_exit_level_range"),
        CheckConstraint("min_total_credits >= 0", name="min_total_credits_positive"),
        CheckConstraint(
            "min_exit_level_credits IS NULL OR min_exit_level_credits >= 0",
            name="min_exit_level_credits_positive",
        ),
    )

    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    nqf_exit_level: Mapped[int] = mapped_column(Integer)
    min_total_credits: Mapped[int] = mapped_column(Integer)
    # Credits wanted at the type's own NQF exit level; null = no such rule (ADR 035).
    min_exit_level_credits: Mapped[int | None] = mapped_column(Integer, default=None)
    # Where the values come from; seeded rows say they must be verified.
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Programme(Audited, SoftDeleteMixin, CoreModel):
    """A qualification offered by a faculty."""

    __tablename__ = "programmes"
    __table_args__ = (
        live_unique("uq_programmes_faculty_code_live", "faculty_id", "code"),
        CheckConstraint("nqf_exit_level BETWEEN 1 AND 10", name="nqf_exit_level_range"),
        CheckConstraint("total_credits IS NULL OR total_credits >= 0", name="credits_positive"),
        CheckConstraint(
            "minimum_duration_years IS NULL OR minimum_duration_years > 0",
            name="duration_positive",
        ),
    )

    faculty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("faculties.id", ondelete="RESTRICT"), index=True
    )
    qualification_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("qualification_types.id", ondelete="RESTRICT"), default=None, index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    nqf_exit_level: Mapped[int | None] = mapped_column(Integer, default=None)
    saqa_id: Mapped[str | None] = mapped_column(String(32), default=None)
    total_credits: Mapped[int | None] = mapped_column(Integer, default=None)
    minimum_duration_years: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), default=None)
    status: Mapped[ProgrammeStatus] = mapped_column(
        str_enum(ProgrammeStatus, "programme_status"),
        default=ProgrammeStatus.PLANNED,
        server_default=ProgrammeStatus.PLANNED.value,
    )

    # Council on Higher Education
    che_accreditation_status: Mapped[AccreditationStatus] = mapped_column(
        str_enum(AccreditationStatus, "che_accreditation_status"),
        default=AccreditationStatus.NOT_APPLICABLE,
        server_default=AccreditationStatus.NOT_APPLICABLE.value,
    )
    che_accredited_from: Mapped[date | None] = mapped_column(default=None)
    che_accredited_until: Mapped[date | None] = mapped_column(default=None)
    # Professional council (e.g. HPCSA, SANC, SAPC)
    council_name: Mapped[str | None] = mapped_column(String(128), default=None)
    council_accreditation_status: Mapped[AccreditationStatus] = mapped_column(
        str_enum(AccreditationStatus, "council_accreditation_status"),
        default=AccreditationStatus.NOT_APPLICABLE,
        server_default=AccreditationStatus.NOT_APPLICABLE.value,
    )
    council_accredited_from: Mapped[date | None] = mapped_column(default=None)
    council_accredited_until: Mapped[date | None] = mapped_column(default=None)

    faculty: Mapped[Faculty] = relationship(lazy="raise")
    qualification_type: Mapped[QualificationType | None] = relationship(lazy="raise")
    versions: Mapped[list["CurriculumVersion"]] = relationship(
        back_populates="programme", lazy="raise", order_by="CurriculumVersion.academic_year"
    )


class CurriculumVersion(Audited, SoftDeleteMixin, CoreModel):
    """The curriculum of a programme for one academic year."""

    __tablename__ = "curriculum_versions"
    __table_args__ = (
        live_unique(
            "uq_curriculum_versions_programme_year_live",
            "programme_id",
            "academic_year",
        ),
        CheckConstraint("academic_year BETWEEN 1900 AND 2200", name="academic_year_range"),
    )

    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programmes.id", ondelete="RESTRICT"), index=True
    )
    academic_year: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(
        str_enum(VersionStatus, "version_status"),
        default=VersionStatus.DRAFT,
        server_default=VersionStatus.DRAFT.value,
    )
    # The version this one was copied from ("copy academic year forward").
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(default=None)

    programme: Mapped[Programme] = relationship(back_populates="versions", lazy="raise")
    phases: Mapped[list["Phase"]] = relationship(
        back_populates="version", lazy="raise", order_by="Phase.position"
    )
    modules: Mapped[list["Module"]] = relationship(
        back_populates="version", lazy="raise", order_by="Module.position"
    )


class Phase(Audited, SoftDeleteMixin, CoreModel):
    """A year, phase, block or longitudinal thread within a version."""

    __tablename__ = "phases"
    __table_args__ = (
        # Target of the composite FK that keeps a module's phase in the same version.
        UniqueConstraint("id", "version_id"),
        live_unique("uq_phases_version_external_id_live", "version_id", "external_id"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    kind: Mapped[PhaseKind] = mapped_column(
        str_enum(PhaseKind, "phase_kind"),
        default=PhaseKind.YEAR,
        server_default=PhaseKind.YEAR.value,
    )
    # The item's id in the institution's own system or spreadsheet (Slice 1.25, ADR 054): an Excel
    # import updates the item with this id instead of making a second one. Copied forward.
    external_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    # Copy forward: the item of the earlier version this one continues (version diff).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phases.id", ondelete="SET NULL"), default=None, index=True
    )

    version: Mapped[CurriculumVersion] = relationship(back_populates="phases", lazy="raise")


class Module(Audited, SoftDeleteMixin, CoreModel):
    """A module (course) in a version, optionally within a phase.

    Longitudinal modules span phases and have no phase. Coordinators are users
    holding the module coordinator role at this module's scope.
    """

    __tablename__ = "modules"
    __table_args__ = (
        live_unique("uq_modules_version_code_live", "version_id", "code"),
        live_unique("uq_modules_version_external_id_live", "version_id", "external_id"),
        # The phase, if any, must belong to the same version.
        ForeignKeyConstraint(
            ["phase_id", "version_id"],
            ["phases.id", "phases.version_id"],
            name="fk_modules_phase_same_version",
        ),
        CheckConstraint("credits IS NULL OR credits >= 0", name="credits_positive"),
        CheckConstraint("nqf_level IS NULL OR nqf_level BETWEEN 1 AND 10", name="nqf_level_range"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    credits: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), default=None)
    nqf_level: Mapped[int | None] = mapped_column(Integer, default=None)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    external_lms_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    # The item's id in the institution's own system or spreadsheet (Slice 1.25, ADR 054): an Excel
    # import updates the item with this id instead of making a second one. Copied forward.
    external_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Copy forward: the item of the earlier version this one continues (version diff).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="SET NULL"), default=None, index=True
    )

    version: Mapped[CurriculumVersion] = relationship(back_populates="modules", lazy="raise")
    phase: Mapped[Phase | None] = relationship(
        foreign_keys=[phase_id],
        primaryjoin="Module.phase_id == Phase.id",
        lazy="raise",
        viewonly=True,
    )
    learning_events: Mapped[list["LearningEvent"]] = relationship(
        back_populates="module", lazy="raise", order_by="LearningEvent.position"
    )


class LearningEvent(Audited, SoftDeleteMixin, CoreModel):
    """A session within a module (lecture, PBL tutorial, practical, placement...)."""

    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint("contact_minutes >= 0", name="contact_minutes_positive"),
        CheckConstraint("self_study_minutes >= 0", name="self_study_minutes_positive"),
        CheckConstraint("week IS NULL OR week >= 0", name="week_positive"),
    )

    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    # Teaching format: a value from a teaching-method tag list (lecture, PBL, practical...).
    format_value_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tag_values.id", ondelete="SET NULL"), default=None, index=True
    )
    contact_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    self_study_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    week: Mapped[int | None] = mapped_column(Integer, default=None)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    external_lms_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    # The item's id in the institution's own system or spreadsheet (Slice 1.25, ADR 054): an Excel
    # import updates the item with this id instead of making a second one. Copied forward.
    external_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    # Copy forward: the item of the earlier version this one continues (version diff).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_events.id", ondelete="SET NULL"), default=None, index=True
    )

    module: Mapped[Module] = relationship(back_populates="learning_events", lazy="raise")


class Objective(Audited, SoftDeleteMixin, CoreModel):
    """A learning objective or outcome at programme, module or learning event level.

    ``version_id`` is always set (also for module and event objectives) so a
    whole version's objectives can be queried and copied directly. The owner
    column must match the level.
    """

    __tablename__ = "objectives"
    __table_args__ = (
        CheckConstraint(
            "(level = 'programme' AND module_id IS NULL AND learning_event_id IS NULL)"
            " OR (level = 'module' AND module_id IS NOT NULL AND learning_event_id IS NULL)"
            " OR (level = 'learning_event' AND module_id IS NULL"
            " AND learning_event_id IS NOT NULL)",
            name="owner_matches_level",
        ),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
        live_unique("uq_objectives_version_external_id_live", "version_id", "external_id"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[ObjectiveLevel] = mapped_column(str_enum(ObjectiveLevel, "objective_level"))
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), default=None, index=True
    )
    learning_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_events.id", ondelete="CASCADE"), default=None, index=True
    )
    text: Mapped[str] = mapped_column(Text)
    # When the wording last changed (null: not since it was made). A rejected AI suggestion is
    # asked about again only if the wording changed after the rejection (ADR 045).
    text_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    domain: Mapped[ObjectiveDomain | None] = mapped_column(
        str_enum(ObjectiveDomain, "objective_domain"), default=None
    )
    taxonomy_level_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("taxonomy_levels.id", ondelete="SET NULL"), default=None, index=True
    )
    # Filled by the objective quality checker (phase 1).
    detected_verb: Mapped[str | None] = mapped_column(String(64), default=None)
    quality_flags: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )
    status: Mapped[ObjectiveStatus] = mapped_column(
        str_enum(ObjectiveStatus, "objective_status"),
        default=ObjectiveStatus.DRAFT,
        server_default=ObjectiveStatus.DRAFT.value,
    )
    # The item's id in the institution's own system or spreadsheet (Slice 1.25, ADR 054): an Excel
    # import updates the item with this id instead of making a second one. Copied forward.
    external_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Copy forward: the item of the earlier version this one continues (version diff).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), default=None, index=True
    )

    parent_links: Mapped[list["ObjectiveLink"]] = relationship(
        foreign_keys="ObjectiveLink.child_id", back_populates="child", lazy="raise"
    )


class ObjectiveLink(Audited, CoreModel):
    """An upward link: a narrower objective contributes to a broader one."""

    __tablename__ = "objective_links"
    __table_args__ = (
        UniqueConstraint("child_id", "parent_id"),
        CheckConstraint("child_id <> parent_id", name="not_self"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )

    child: Mapped[Objective] = relationship(
        foreign_keys=[child_id], back_populates="parent_links", lazy="raise"
    )
    parent: Mapped[Objective] = relationship(foreign_keys=[parent_id], lazy="raise")


# Statuses anyone who may edit an objective can set; the others need `objectives.approve`
# (ADR 032).
EDITOR_OBJECTIVE_STATUSES = frozenset({ObjectiveStatus.DRAFT, ObjectiveStatus.READY_FOR_REVIEW})
