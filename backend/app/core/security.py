"""Password hashing, password policy and token helpers."""

import hashlib
import hmac
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2-cffi defaults to Argon2id with the RFC 9106 low-memory profile
# (t=3, m=64 MiB, p=4), which fits the 8 GB reference server.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against an Argon2 hash in constant time."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Whether a hash was made with weaker parameters than the current ones."""
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(32))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real verification.

    Called when no account (or no password) exists, so response timing does not
    reveal which email addresses are registered.
    """
    verify_password(_dummy_hash(), password)


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the password policy."""


def validate_password(password: str, *, email: str, min_length: int, max_length: int) -> None:
    """Enforce the password policy (length bounds, not the email address).

    Raises:
        PasswordPolicyError: With a user-facing reason.
    """
    if len(password) < min_length:
        raise PasswordPolicyError(f"Password must be at least {min_length} characters long.")
    if len(password) > max_length:
        raise PasswordPolicyError(f"Password must be at most {max_length} characters long.")
    if password.strip().casefold() == email.strip().casefold():
        raise PasswordPolicyError("Password must not be your email address.")


def generate_token() -> str:
    """Generate an unguessable URL-safe token (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage, so a leaked store does not yield usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(session_token: str, secret_key: str) -> str:
    """Derive the CSRF token bound to a session.

    Deriving it (rather than storing it) lets the CSRF check run without a
    session lookup.
    """
    return hmac.new(
        secret_key.encode(), b"csrf:" + session_token.encode(), hashlib.sha256
    ).hexdigest()


def csrf_token_matches(session_token: str, csrf_token: str, secret_key: str) -> bool:
    """Compare a submitted CSRF token with the expected one in constant time."""
    return hmac.compare_digest(csrf_token_for(session_token, secret_key), csrf_token)
