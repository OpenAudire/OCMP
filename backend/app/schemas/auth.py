"""Schemas for authentication endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    """The signed-in user's own account details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    last_login_at: datetime | None
    # False for SSO-only accounts, which cannot change or reset a local password.
    has_password: bool


class AuthOptions(BaseModel):
    """What the sign-in pages need to know before anyone signs in."""

    password_min_length: int
    password_max_length: int
    sso_enabled: bool
    sso_provider_name: str


class LoginRequest(BaseModel):
    """Email and password sign-in."""

    # Not EmailStr: a malformed address should fail like a wrong password,
    # not with a validation error that reveals more.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    """Result of a successful sign-in."""

    user: UserRead
    csrf_token: str


class ChangePasswordRequest(BaseModel):
    """Change the signed-in user's password."""

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class PasswordResetRequest(BaseModel):
    """Ask for a password reset link."""

    email: str = Field(min_length=1, max_length=320)


class PasswordResetRequested(BaseModel):
    """Always the same, whether or not the account exists."""

    detail: str = (
        "If an account with that email address can reset its password, a reset link has been sent."
    )


class PasswordResetConfirm(BaseModel):
    """Set a new password with the token from a reset link."""

    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=1024)
