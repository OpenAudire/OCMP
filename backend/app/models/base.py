"""Declarative base and shared column mixins for all models."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, Enum, ForeignKey, Index, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names so Alembic migrations are stable across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
    }


class UUIDPrimaryKeyMixin:
    """UUID primary key, generated in Python and by the database as a fallback."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """`created_at` and `updated_at` columns maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CreatedByMixin:
    """`created_by_id` referencing the user who created the row.

    Nullable because system processes (migrations, imports, the setup wizard)
    create rows without an acting user, and set to NULL if that user is removed.
    """

    @declared_attr
    def created_by_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class SoftDeleteMixin:
    """`deleted_at` marker for rows whose history must be kept."""

    deleted_at: Mapped[datetime | None] = mapped_column(default=None, index=True)

    @property
    def is_deleted(self) -> bool:
        """Whether the row has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark the row as deleted without removing it."""
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        """Clear the soft-delete marker."""
        self.deleted_at = None


class CoreModel(UUIDPrimaryKeyMixin, TimestampMixin, CreatedByMixin, Base):
    """Abstract base with the columns every OCMP table carries."""

    __abstract__ = True

    # Fetch server-generated values (timestamps) with RETURNING after INSERT/UPDATE,
    # so reading them never triggers implicit lazy IO under asyncio.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (typed by SQLAlchemy)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """A VARCHAR column with a CHECK constraint (no native Postgres enum to migrate)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def live_unique(name: str, *columns: str) -> Index:
    """Unique among rows that are not soft-deleted."""
    return Index(name, *columns, unique=True, postgresql_where=text("deleted_at IS NULL"))
