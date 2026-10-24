"""Organisational models: institution, faculty and department."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import CoreModel, SoftDeleteMixin


class Institution(SoftDeleteMixin, CoreModel):
    """A university or college running this OCMP instance."""

    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(255))
    short_code: Mapped[str] = mapped_column(String(32), unique=True)
    # ISO 3166-1 alpha-2 country code.
    country: Mapped[str] = mapped_column(String(2), default="ZA", server_default="ZA")
    # Terminology overrides, enabled profiles, default taxonomy, etc.
    settings: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )

    faculties: Mapped[list["Faculty"]] = relationship(
        back_populates="institution", lazy="raise", order_by="Faculty.name"
    )

    def __repr__(self) -> str:
        return f"<Institution {self.short_code}>"


class Faculty(SoftDeleteMixin, CoreModel):
    """A faculty (or school/college) within an institution."""

    __tablename__ = "faculties"
    __table_args__ = (UniqueConstraint("institution_id", "code"),)

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))

    institution: Mapped[Institution] = relationship(back_populates="faculties", lazy="raise")
    departments: Mapped[list["Department"]] = relationship(
        back_populates="faculty", lazy="raise", order_by="Department.name"
    )

    def __repr__(self) -> str:
        return f"<Faculty {self.code}>"


class Department(SoftDeleteMixin, CoreModel):
    """A department within a faculty."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("faculty_id", "code"),)

    faculty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("faculties.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))

    faculty: Mapped[Faculty] = relationship(back_populates="departments", lazy="raise")

    def __repr__(self) -> str:
        return f"<Department {self.code}>"
