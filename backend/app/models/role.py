"""Roles and scoped role assignments."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import CoreModel
from app.models.user import User

SCOPE_TYPES_SQL = "'instance', 'faculty', 'programme', 'module', 'learning_event'"


class Role(CoreModel):
    """A named set of permissions. System roles are synced from code."""

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )
    # Scope types this role may be assigned at.
    scope_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    # Assignments must have an end date (e.g. external reviewers).
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    def __repr__(self) -> str:
        return f"<Role {self.key}>"


class RoleAssignment(CoreModel):
    """A user holding a role at a scope (the whole instance, or one faculty, programme...).

    ``scope_id`` refers to a row of the table named by ``scope_type``; it has no
    foreign key because the target table varies. The service validates it.
    """

    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "role_id", "scope_type", "scope_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint(f"scope_type IN ({SCOPE_TYPES_SQL})", name="scope_type_valid"),
        CheckConstraint(
            "(scope_type = 'instance') = (scope_id IS NULL)", name="scope_id_matches_type"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="raise")
    role: Mapped[Role] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"<RoleAssignment {self.id}>"
