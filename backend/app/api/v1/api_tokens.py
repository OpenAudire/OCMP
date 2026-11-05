"""Personal API tokens (Slice 1.30, ADR 060).

A person makes, lists and revokes their own tokens in the web app (a token cannot make tokens).
Someone with ``users.manage`` can list and revoke another person's tokens, for example when they
leave. The token itself is returned once, when it is made.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionAuth, require_permission
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.permissions import Permission
from app.models import ApiToken, User
from app.services import api_tokens
from app.services.audit import audit_operation
from app.services.authorization import has_permission

router = APIRouter(tags=["api-tokens"])
logger = get_logger(__name__)

UserManager = Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))]


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    # The first characters, to tell tokens apart.
    token_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    # "active", "expired" or "revoked".
    state: str = "active"


class TokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    scopes: Annotated[list[str], Field(min_length=1, max_length=2)] = ["read"]
    days: Annotated[int, Field(ge=1, le=api_tokens.MAX_DAYS)] = api_tokens.DEFAULT_DAYS


class TokenCreated(TokenRead):
    # The token itself. It is shown this once and cannot be read again.
    token: str


def _read(token: ApiToken) -> TokenRead:
    read = TokenRead.model_validate(token)
    if token.revoked_at is not None:
        read.state = "revoked"
    elif not api_tokens.is_active(token):
        read.state = "expired"
    return read


@router.get("/api-tokens", response_model=list[TokenRead])
async def my_tokens(auth: SessionAuth, db: DbSession) -> list[TokenRead]:
    """The signed-in person's tokens (never the tokens themselves)."""
    return [_read(t) for t in await api_tokens.list_tokens(db, auth.user.id)]


@router.post("/api-tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenCreate, auth: SessionAuth, db: DbSession) -> TokenCreated:
    """Make a token for the signed-in person. The token is in the answer, once."""
    with audit_operation("api_token.create", actor_id=auth.user.id):
        token, plain = await api_tokens.create_token(
            db, auth.user, name=body.name, scopes=body.scopes, days=body.days
        )
    logger.info("api_token_created", user_id=str(auth.user.id), token_id=str(token.id))
    return TokenCreated(**_read(token).model_dump(), token=plain)


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, auth: SessionAuth, db: DbSession) -> Response:
    """Revoke a token: your own, or (with users.manage) anyone's."""
    token = await api_tokens.get_token(db, token_id)
    foreign = token is not None and token.user_id != auth.user.id
    if foreign and not await has_permission(db, auth.user, Permission.USERS_MANAGE):
        token = None  # someone else's token: do not say it exists
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found.")
    with audit_operation("api_token.revoke", actor_id=auth.user.id):
        await api_tokens.revoke(db, token)
    logger.info("api_token_revoked", token_id=str(token.id), actor_id=str(auth.user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/api-tokens", response_model=list[TokenRead])
async def users_tokens(user_id: uuid.UUID, _actor: UserManager, db: DbSession) -> list[TokenRead]:
    """Someone's tokens (to revoke them), for administrators."""
    return [_read(t) for t in await api_tokens.list_tokens(db, user_id)]
