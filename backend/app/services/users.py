"""User accounts and local (email + password) authentication."""

import uuid
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    burn_password_check,
    hash_password,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.models import User


class UserAlreadyExistsError(ValueError):
    """Raised when an account with the email address already exists."""


class InvalidEmailError(ValueError):
    """Raised when an email address is not syntactically valid."""


def normalise_email(email: str) -> str:
    """Validate an email address and return its normalised form.

    Raises:
        InvalidEmailError: If the address is not valid.
    """
    try:
        # No DNS lookups: institutions may run OCMP without outbound network access.
        return validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise InvalidEmailError(str(exc)) from exc


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Find a non-deleted user by email address, ignoring case."""
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email.strip().lower(),
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_active_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Load a user who is allowed to use the platform (active, not deleted)."""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_local_user(
    db: AsyncSession,
    settings: Settings,
    *,
    email: str,
    display_name: str,
    password: str,
    created_by_id: uuid.UUID | None = None,
) -> User:
    """Create a user who signs in with email and password.

    Raises:
        InvalidEmailError: If the email address is not valid.
        PasswordPolicyError: If the password does not meet the policy.
        UserAlreadyExistsError: If the email address is already registered.
    """
    email = normalise_email(email)
    validate_password(
        password,
        email=email,
        min_length=settings.password_min_length,
        max_length=settings.password_max_length,
    )
    if await get_user_by_email(db, email) is not None:
        raise UserAlreadyExistsError("An account with this email address already exists.")

    user = User(
        email=email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        created_by_id=created_by_id,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Return the user if the email and password are correct and the account may sign in.

    Takes the same time whether or not the account exists. Upgrades the stored
    hash when hashing parameters have changed, and records the login time.
    """
    user = await get_user_by_email(db, email)
    if user is None or user.password_hash is None:
        burn_password_check(password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    if not user.is_active:
        return None

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


async def change_password(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> bool:
    """Change a user's password after checking the current one.

    Returns:
        False if the current password is wrong.

    Raises:
        PasswordPolicyError: If the new password does not meet the policy.
    """
    if user.password_hash is None or not verify_password(user.password_hash, current_password):
        return False
    validate_password(
        new_password,
        email=user.email,
        min_length=settings.password_min_length,
        max_length=settings.password_max_length,
    )
    user.password_hash = hash_password(new_password)
    await db.flush()
    return True


async def list_users(
    db: AsyncSession, *, search: str | None = None, offset: int = 0, limit: int = 50
) -> tuple[list[User], int]:
    """Non-deleted users, newest first, optionally filtered by name or email."""
    query = select(User).where(User.deleted_at.is_(None))
    if search:
        # Escape LIKE wildcards so the search text is matched literally.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            User.email.ilike(pattern, escape="\\") | User.display_name.ilike(pattern, escape="\\")
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)
    )
    return list(result.scalars()), int(total or 0)
