"""Personal API tokens (Slice 1.30, ADR 060)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel


class ApiToken(Audited, CoreModel):
    """A token a person makes to call the API as themselves, with a limited scope.

    Only a hash of the token is stored: the token is shown once, when it is made. The person's own
    permissions still decide what a request can do; a token can only narrow them (``read`` allows
    only reads). Making and revoking a token is audited; using it is not (``last_used_at`` is not
    recorded).
    """

    __tablename__ = "api_tokens"
    __audit_exclude__ = frozenset({"token_hash"})
    __audit_ignore__ = frozenset({"last_used_at"})

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    # The first characters, so a person can tell their tokens apart (never enough to use one).
    token_prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # "read" (safe methods only) and/or "write".
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
