"""Schemas for roles, permissions and role assignments."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import ScopeType


class PermissionRead(BaseModel):
    """A permission and the permissions it implies."""

    key: str
    implies: list[str]


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    scope_types: list[str]
    requires_expiry: bool


class RoleCreate(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    permissions: list[str] = Field(min_length=1, max_length=100)
    scope_types: list[ScopeType] = Field(min_length=1)
    requires_expiry: bool = False


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] | None = Field(default=None, min_length=1, max_length=100)
    scope_types: list[ScopeType] | None = Field(default=None, min_length=1)
    requires_expiry: bool | None = None


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: RoleSummary
    scope_type: ScopeType
    scope_id: uuid.UUID | None
    expires_at: datetime | None
    created_at: datetime


class AssignmentCreate(BaseModel):
    user_id: uuid.UUID
    role_key: str = Field(min_length=1, max_length=64)
    scope_type: ScopeType
    scope_id: uuid.UUID | None = None
    expires_at: datetime | None = None
