"""Objectives proposed from a study guide, waiting for a person to accept or reject them
(Slice 1.18, ADR 047).

A proposal is derived data, like an embedding: it is not an objective and counts nowhere until a
person accepts it, which creates an ordinary draft objective through the objective service (that
is audited). The study guide itself is never stored; only the short quote that shows where in the
guide the wording came from.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CoreModel, str_enum
from app.models.curriculum import ObjectiveDomain


class ProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ObjectiveProposal(CoreModel):
    """One objective an AI run found in a study guide."""

    __tablename__ = "objective_proposals"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), index=True
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    domain: Mapped[ObjectiveDomain | None] = mapped_column(
        str_enum(ObjectiveDomain, "proposal_domain"), default=None
    )
    # Words of the study guide that the wording is based on (checked against the guide's text).
    source_quote: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[ProposalStatus] = mapped_column(
        str_enum(ProposalStatus, "proposal_status"),
        default=ProposalStatus.PENDING,
        server_default=ProposalStatus.PENDING.value,
        index=True,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # The draft objective that accepting it made (empty if that objective was deleted).
    objective_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), default=None
    )
