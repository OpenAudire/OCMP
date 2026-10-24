"""User account model.

Authentication fields (password hash, OIDC subject) and role assignments are
added in their own slices; this is the identity row everything else refers to.
"""

from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CoreModel, SoftDeleteMixin


class User(SoftDeleteMixin, CoreModel):
    """A person who can sign in to OCMP."""

    __tablename__ = "users"
    __table_args__ = (
        # Email addresses are unique regardless of case.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        return f"<User {self.id}>"
