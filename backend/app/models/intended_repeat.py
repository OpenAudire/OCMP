"""Framework items a programme teaches in many sessions on purpose (Slice 1.24a, ADR 053).

A spiral curriculum returns to the same competency again and again. A coordinator marks the item
as an *intentional repeat*; the report on items taught in many sessions then leaves it out. The
mark belongs to the programme (all its versions) and is audited; removing it is a soft delete.
"""

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel, SoftDeleteMixin, live_unique


class IntendedRepeat(Audited, SoftDeleteMixin, CoreModel):
    """A programme's decision that a framework item is taught repeatedly on purpose."""

    __tablename__ = "intended_repeats"
    __table_args__ = (
        live_unique("uq_intended_repeats_item_live", "programme_id", "framework_item_id"),
    )

    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programmes.id", ondelete="CASCADE"), index=True
    )
    framework_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), index=True
    )
    # Why (for example "spiral curriculum: revisited each year at a higher level").
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
