"""Authentication endpoints for local accounts."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import (
    CurrentAuth,
    CurrentUser,
    RedisDep,
    SettingsDep,
    clear_session_cookies,
    session_ttl_seconds,
    set_session_cookies,
)
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.security import PasswordPolicyError, csrf_token_for
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, UserRead
from app.services import rate_limit, sessions
from app.services.users import authenticate, change_password

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)

_IP_SCOPE = "login-ip"
_ACCOUNT_SCOPE = "login-account"


def _too_many_attempts(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many sign-in attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> LoginResponse:
    """Sign in with email and password and start a session."""
    client_ip = request.client.host if request.client else "unknown"
    window = settings.login_rate_limit_window_seconds

    for scope, identifier, limit in (
        (_IP_SCOPE, client_ip, settings.login_rate_limit_per_ip),
        (_ACCOUNT_SCOPE, body.email, settings.login_rate_limit_per_account),
    ):
        limited = await rate_limit.check(redis, scope, identifier, limit)
        if not limited.allowed:
            logger.warning("login_rate_limited", scope=scope)
            raise _too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _IP_SCOPE, client_ip, window)

    user = await authenticate(db, body.email, body.password)
    if user is None:
        await rate_limit.hit(redis, _ACCOUNT_SCOPE, body.email, window)
        # No email in logs: failed attempts are often typos of someone's address.
        logger.info("login_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    await rate_limit.reset(redis, _ACCOUNT_SCOPE, body.email)

    # Always a new token on sign-in (prevents session fixation).
    old_token = request.cookies.get(settings.session_cookie_name)
    if old_token:
        await sessions.delete_session(redis, old_token)
    token = await sessions.create_session(redis, user.id, session_ttl_seconds(settings))
    set_session_cookies(response, settings, token)
    logger.info("login_succeeded", user_id=str(user.id))

    return LoginResponse(
        user=UserRead.model_validate(user),
        csrf_token=csrf_token_for(token, settings.secret_key),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    redis: RedisDep,
    settings: SettingsDep,
) -> None:
    """End the current session. Succeeds even if the session already expired."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await sessions.delete_session(redis, token)
    clear_session_cookies(response, settings)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    """The signed-in user's account."""
    return UserRead.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    body: ChangePasswordRequest,
    auth: CurrentAuth,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> None:
    """Change the signed-in user's password and sign out their other sessions."""
    user_id = str(auth.user.id)
    limited = await rate_limit.check(
        redis, _ACCOUNT_SCOPE, auth.user.email, settings.login_rate_limit_per_account
    )
    if not limited.allowed:
        raise _too_many_attempts(limited.retry_after_seconds)

    try:
        changed = await change_password(
            db,
            settings,
            auth.user,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    if not changed:
        await rate_limit.hit(
            redis, _ACCOUNT_SCOPE, auth.user.email, settings.login_rate_limit_window_seconds
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    revoked = await sessions.revoke_user_sessions(
        redis, auth.user.id, keep_token=auth.session_token
    )
    logger.info("password_changed", user_id=user_id, other_sessions_revoked=revoked)
