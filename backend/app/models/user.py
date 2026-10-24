"""User account model.

OIDC identity fields and role assignments are added in their own slices.
"""

from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel, SoftDeleteMixin


class User(Audited, SoftDeleteMixin, CoreModel):
    """A person who can sign in to OCMP."""

    # Personal data stays out of the audit log; changes are recorded by field only.
    __audit_exclude__ = frozenset({"email", "display_name", "password_hash"})
    __audit_ignore__ = frozenset({"last_login_at"})

    __tablename__ = "users"
    __table_args__ = (
        # Email addresses are unique regardless of case.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Argon2id encoded hash; NULL for users who only sign in through SSO.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def has_password(self) -> bool:
        """Whether the user can sign in with a local password."""
        return self.password_hash is not None

    def __repr__(self) -> str:
        return f"<User {self.id}>"
