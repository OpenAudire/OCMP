"""Schemas for user administration."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserAdminRead(BaseModel):
    """A user account as administrators see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    has_password: bool


class UserList(BaseModel):
    items: list[UserAdminRead]
    total: int


class UserCreate(BaseModel):
    """Create a local (email and password) account."""

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
