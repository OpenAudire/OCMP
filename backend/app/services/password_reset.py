"""Password reset by emailed link.

Tokens are 256-bit random values. Redis stores only their hash, with a TTL,
mapped to the user id and a fingerprint of the user's password hash at issue
time. Any password change alters the fingerprint, so it invalidates every
outstanding link; each user also has at most one live token.
"""

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import generate_token, hash_password, hash_token, validate_password
from app.models import User
from app.services import rate_limit
from app.services.email import EmailMessage, EmailSender
from app.services.users import get_active_user, get_user_by_email

logger = get_logger(__name__)

_TOKEN_KEY = "ocmp:password-reset:{}"  # noqa: S105 (Redis key pattern)
_USER_TOKEN_KEY = "ocmp:password-reset-user:{}"  # noqa: S105
_ACCOUNT_SCOPE = "password-reset-account"


class InvalidResetTokenError(ValueError):
    """The reset link is unknown, expired, already used or superseded."""


def _password_fingerprint(user: User) -> str:
    """Changes whenever the user's password changes (including first being set)."""
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()


def reset_link(settings: Settings, token: str) -> str:
    """Link for the email. The token is in the fragment, which browsers never send
    to the server, so it stays out of access logs and Referer headers."""
    return f"{settings.public_url.rstrip('/')}/reset-password#token={token}"


async def create_reset_token(redis: Redis, settings: Settings, user: User) -> str:
    """Issue a reset token for the user, replacing any earlier one."""
    token = generate_token()
    token_hash = hash_token(token)
    ttl = settings.password_reset_token_minutes * 60
    user_key = _USER_TOKEN_KEY.format(user.id)
    payload = json.dumps({"user_id": str(user.id), "fingerprint": _password_fingerprint(user)})

    previous = await redis.get(user_key)
    async with redis.pipeline(transaction=True) as pipe:
        if previous:
            pipe.delete(_TOKEN_KEY.format(previous))
        pipe.set(_TOKEN_KEY.format(token_hash), payload, ex=ttl)
        pipe.set(user_key, token_hash, ex=ttl)
        await pipe.execute()
    return token


def _reset_email(settings: Settings, user: User, token: str) -> EmailMessage:
    minutes = settings.password_reset_token_minutes
    return EmailMessage(
        to=user.email,
        subject=f"Reset your {settings.app_name} password",
        body=(
            f"Hello {user.display_name},\n\n"
            f"Someone asked to reset the password for your {settings.app_name} account. "
            f"To choose a new password, open this link within {minutes} minutes:\n\n"
            f"{reset_link(settings, token)}\n\n"
            "If you did not ask for this, you can ignore this email; "
            "your password will not change.\n"
        ),
    )


def password_changed_email(settings: Settings, user: User) -> EmailMessage:
    """Notice sent after any password change."""
    return EmailMessage(
        to=user.email,
        subject=f"Your {settings.app_name} password was changed",
        body=(
            f"Hello {user.display_name},\n\n"
            f"The password for your {settings.app_name} account was just changed, "
            "and you were signed out on all other devices.\n\n"
            "If you did not do this, reset your password straight away and tell "
            "your platform administrator.\n"
        ),
    )


async def send_reset_email(
    db: AsyncSession,
    redis: Redis,
    settings: Settings,
    sender: EmailSender | None,
    email: str,
) -> bool:
    """Send a reset link if the address belongs to an account that can use one.

    Runs in the worker, so the API responds identically whether or not the
    account exists. Returns whether an email was sent.
    """
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        logger.info("password_reset_skipped", reason="no_active_account")
        return False
    if user.password_hash is None:
        # SSO-only account: there is no local password to reset.
        logger.info("password_reset_skipped", reason="sso_only", user_id=str(user.id))
        return False
    if sender is None:
        logger.warning("password_reset_not_sent", reason="smtp_not_configured")
        return False

    # Silent cap on emails per account, so the form cannot be used to flood an inbox.
    limit = settings.password_reset_per_account_per_hour
    if not (await rate_limit.check(redis, _ACCOUNT_SCOPE, user.email, limit)).allowed:
        logger.info("password_reset_skipped", reason="account_limit", user_id=str(user.id))
        return False
    await rate_limit.hit(redis, _ACCOUNT_SCOPE, user.email, 3600)

    token = await create_reset_token(redis, settings, user)
    await asyncio.to_thread(sender.send, _reset_email(settings, user, token))
    logger.info("password_reset_sent", user_id=str(user.id))
    return True


@dataclass(frozen=True)
class _TokenRecord:
    key: str
    user: User


async def _lookup(db: AsyncSession, redis: Redis, token: str) -> _TokenRecord:
    key = _TOKEN_KEY.format(hash_token(token))
    raw = await redis.get(key)
    if raw is None:
        raise InvalidResetTokenError
    data = json.loads(raw)
    user = await get_active_user(db, uuid.UUID(data["user_id"]))
    if user is None or user.password_hash is None:
        raise InvalidResetTokenError
    if data["fingerprint"] != _password_fingerprint(user):
        raise InvalidResetTokenError  # password changed since the link was sent
    return _TokenRecord(key=key, user=user)


async def reset_password(
    db: AsyncSession, redis: Redis, settings: Settings, *, token: str, new_password: str
) -> User:
    """Set a new password using a reset token, consuming the token.

    The password policy is checked before the token is consumed, so a rejected
    password does not use up the link.

    Raises:
        InvalidResetTokenError: If the token cannot be used.
        PasswordPolicyError: If the new password does not meet the policy.
    """
    record = await _lookup(db, redis, token)
    validate_password(
        new_password,
        email=record.user.email,
        min_length=settings.password_min_length,
        max_length=settings.password_max_length,
    )
    # GETDEL makes the token single-use even under concurrent requests.
    if await redis.getdel(record.key) is None:
        raise InvalidResetTokenError
    await redis.delete(_USER_TOKEN_KEY.format(record.user.id))

    record.user.password_hash = hash_password(new_password)
    await db.flush()
    return record.user
