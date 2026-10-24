"""External identities (SSO) linked to user accounts."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import CoreModel
from app.models.user import User


class UserIdentity(CoreModel):
    """A sign-in identity at an external provider (OIDC now, SAML later).

    A person is identified by the provider's issuer and its stable subject
    identifier, never by email address: providers do not guarantee email
    addresses are verified or unchanging.
    """

    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # "oidc" now; "saml" in phase 2.
    protocol: Mapped[str] = mapped_column(String(16))
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="raise")

    def __repr__(self) -> str:
        return f"<UserIdentity {self.protocol} {self.id}>"
