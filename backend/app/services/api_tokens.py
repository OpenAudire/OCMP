"""Personal API tokens (Slice 1.30, ADR 060).

A person makes a token to call the API as themselves from a script. It is shown once; only its
hash is stored. It carries the person's own permissions, narrowed by its scope (``read`` allows
only reads), and it expires. A deactivated or deleted account's tokens stop working at once and
are revoked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.models import ApiToken, User
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.users import get_active_user

PREFIX = "ocmp_"
SCOPES = ("read", "write")
DEFAULT_DAYS = 90
MAX_DAYS = 365
MAX_ACTIVE = 20
# Using a token writes ``last_used_at`` at most this often.
TOUCH_EVERY = timedelta(minutes=5)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_active(token: ApiToken, now: datetime | None = None) -> bool:
    return token.revoked_at is None and token.expires_at > (now or datetime.now(UTC))


def allows(token: ApiToken, method: str) -> bool:
    """Whether the token's scope allows this HTTP method."""
    return "write" in token.scopes or method.upper() in SAFE_METHODS


def looks_like_token(value: str) -> bool:
    return value.startswith(PREFIX)


async def create_token(
    db: AsyncSession,
    user: User,
    *,
    name: str,
    scopes: list[str],
    days: int = DEFAULT_DAYS,
) -> tuple[ApiToken, str]:
    """Make a token for ``user``. Returns the stored row and the token itself, which is shown once.

    Raises:
        InvalidRequestError: If the name is blank, a scope is unknown or the lifetime is out of
            range.
        ConflictError: If the person already has the most active tokens allowed.
    """
    name = " ".join(name.split())
    if not name:
        raise InvalidRequestError("A token needs a name.")
    chosen = sorted(set(scopes))
    if not chosen or any(s not in SCOPES for s in chosen):
        raise InvalidRequestError("Choose read, write or both.")
    if not 1 <= days <= MAX_DAYS:
        raise InvalidRequestError(f"A token lasts from 1 to {MAX_DAYS} days.")
    now = datetime.now(UTC)
    active = [t for t in await list_tokens(db, user.id) if is_active(t, now)]
    if len(active) >= MAX_ACTIVE:
        raise ConflictError(f"You already have {MAX_ACTIVE} active tokens; revoke one first.")
    plain = PREFIX + generate_token()
    token = ApiToken(
        user_id=user.id,
        name=name[:100],
        token_prefix=plain[:12],
        token_hash=hash_token(plain),
        scopes=chosen,
        expires_at=now + timedelta(days=days),
        created_by_id=user.id,
    )
    db.add(token)
    await db.flush()
    return token, plain


async def list_tokens(db: AsyncSession, user_id: uuid.UUID) -> list[ApiToken]:
    """A person's tokens, newest first (revoked and expired ones included, so they can be seen)."""
    return list(
        await db.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == user_id)
            .order_by(ApiToken.created_at.desc())
            .limit(200)
        )
    )


async def get_token(db: AsyncSession, token_id: uuid.UUID) -> ApiToken | None:
    return await db.get(ApiToken, token_id)


async def revoke(db: AsyncSession, token: ApiToken) -> None:
    """Revoke a token (idempotent)."""
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await db.flush()


async def revoke_all(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every active token of a person (a deactivated or deleted account)."""
    count = 0
    for token in await list_tokens(db, user_id):
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            count += 1
    await db.flush()
    return count


async def authenticate(db: AsyncSession, plain: str) -> tuple[User, ApiToken] | None:
    """The user and token for a token that is known, not revoked or expired and whose owner may
    still sign in; otherwise None."""
    if not looks_like_token(plain):
        return None
    token = await db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(plain)))
    now = datetime.now(UTC)
    if token is None or not is_active(token, now):
        return None
    user = await get_active_user(db, token.user_id)
    if user is None:
        return None
    if token.last_used_at is None or now - token.last_used_at > TOUCH_EVERY:
        token.last_used_at = now
        await db.flush()
    return user, token
