"""The audit log: an append-only record of changes (and personal-data views).

Rows are written by ``app.services.audit`` and cannot be changed or deleted
(database triggers), except that a deleted user's ``actor_id`` is cleared and
the retention purge may delete entries older than the retention period.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"  # commands, background jobs, migrations


class AuditLog(Base):
    """One audited event."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        CheckConstraint("length(action) > 0", name="action_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Strictly increasing: the order events happened in, even within one transaction.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    # Wall-clock time of the event (not the transaction start).
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp(), index=True)
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"))
    # NULL for system actions, or after the acting user's account was deleted.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    # Table name of the entity, e.g. "mapping_links".
    entity_type: Mapped[str] = mapped_column(String(64))
    # NULL for events about a set of rows (e.g. viewing a list of users).
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # create, update, delete, soft_delete, restore, view
    action: Mapped[str] = mapped_column(String(32), index=True)
    # Changed fields only for updates; the full row for creates and deletes.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    # Operation name and details, e.g. {"operation": "mapping.reopen", "reason": "..."}.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
