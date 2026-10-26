"""Minimal assessments: an assessment of a module, its items, and the objectives they cover.

Phase 1 keeps this small (assessment blueprints come in phase 3): an assessment has a
name, a method (a value of an assessment-method tag list), a weight, a timing and the
learner time it takes; its items carry marks and link to the objectives they assess.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel, SoftDeleteMixin


class Assessment(Audited, SoftDeleteMixin, CoreModel):
    """An assessment (test, exam, portfolio...) of a module."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("weight IS NULL OR weight BETWEEN 0 AND 100", name="weight_range"),
        CheckConstraint("time_minutes >= 0", name="time_minutes_positive"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
    )

    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    # The assessment method: a value from an assessment-method tag list.
    method_value_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tag_values.id", ondelete="SET NULL"), default=None, index=True
    )
    # Percentage of the module mark.
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), default=None)
    # When it takes place, in words ("Week 6", "End of semester").
    timing: Mapped[str] = mapped_column(String(128), default="", server_default="")
    # Learner time spent in the assessment itself; counts towards notional hours.
    time_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Copy forward: the item of the earlier version this one continues (version diff).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"), default=None, index=True
    )


class AssessmentItem(Audited, SoftDeleteMixin, CoreModel):
    """A question, station or task of an assessment."""

    __tablename__ = "assessment_items"
    __table_args__ = (
        CheckConstraint("marks IS NULL OR marks >= 0", name="marks_positive"),
        CheckConstraint("length(btrim(label)) > 0", name="label_not_blank"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255))
    marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_items.id", ondelete="SET NULL"), default=None, index=True
    )


class AssessmentItemObjective(Audited, CoreModel):
    """An assessment item assesses an objective of its module or of one of its sessions."""

    __tablename__ = "assessment_item_objectives"
    __table_args__ = (UniqueConstraint("item_id", "objective_id"),)

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_items.id", ondelete="CASCADE"), index=True
    )
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )
