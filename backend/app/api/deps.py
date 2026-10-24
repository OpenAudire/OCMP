"""Shared FastAPI dependencies."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.database import DbSession
from app.core.redis import get_redis
from app.core.security import csrf_token_for
from app.models import User
from app.services import sessions
from app.services.users import get_active_user

SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def session_ttl_seconds(settings: Settings) -> int:
    """Session lifetime in seconds."""
    return settings.session_expire_hours * 3600


def set_session_cookies(response: Response, settings: Settings, token: str) -> None:
    """Set (or renew) the session cookie and the matching CSRF cookie.

    The session cookie is HTTP-only. The CSRF cookie is readable by the
    frontend, which echoes it in the CSRF header on state-changing requests.
    """
    max_age = session_ttl_seconds(settings)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token_for(token, settings.secret_key),
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Remove the session and CSRF cookies."""
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            name, path="/", secure=settings.session_cookie_secure, samesite="lax"
        )


@dataclass(frozen=True)
class AuthContext:
    """The signed-in user and the session token they used."""

    user: User
    session_token: str


_NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
)


async def get_auth_context(
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> AuthContext:
    """Resolve the session cookie to an active user, renewing the session.

    Raises:
        HTTPException: 401 if there is no valid session or the account may not sign in.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _NOT_AUTHENTICATED

    ttl = session_ttl_seconds(settings)
    session = await sessions.get_session(redis, token, ttl)
    if session is None:
        raise _NOT_AUTHENTICATED

    user = await get_active_user(db, session.user_id)
    if user is None:
        # Account deactivated or deleted since sign-in: end all of its sessions.
        await sessions.revoke_user_sessions(redis, session.user_id)
        raise _NOT_AUTHENTICATED

    set_session_cookies(response, settings, token)
    return AuthContext(user=user, session_token=token)


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]


async def get_current_user(auth: CurrentAuth) -> User:
    """The signed-in user."""
    return auth.user


CurrentUser = Annotated[User, Depends(get_current_user)]
