"""Authentication endpoints for local accounts."""

from asyncio import sleep

from fastapi import APIRouter, HTTPException, Request, Response, status
from redis.asyncio import Redis

from app.api.deps import (
    ClientIP,
    CurrentUser,
    RedisDep,
    SessionAuth,
    SettingsDep,
    clear_session_cookies,
    session_ttl_seconds,
    set_session_cookies,
    too_many_attempts,
)
from app.core.config import Settings
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.security import PasswordPolicyError, csrf_token_for
from app.jobs.auth_emails import send_password_changed_notice, send_password_reset
from app.models import RoleAssignment
from app.schemas.auth import (
    AuthOptions,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequested,
    UserRead,
)
from app.schemas.roles import AssignmentRead
from app.services import rate_limit, sessions
from app.services.authorization import user_assignments
from app.services.password_reset import InvalidResetTokenError, reset_password
from app.services.users import authenticate, change_password

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)

_IP_SCOPE = "login-ip"
_RESET_IP_SCOPE = "password-reset-ip"
_ACCOUNT_SCOPE = "login-account"


def _too_many_attempts(retry_after: int) -> HTTPException:
    return too_many_attempts(retry_after)


async def _throttle_account(redis: Redis, settings: Settings, email: str) -> None:
    """Hold the request back in proportion to the account's recent failures.

    This slows password guessing against one account without ever refusing the
    attempt, so the account owner can always sign in with the right password.
    """
    failures = await rate_limit.count(redis, _ACCOUNT_SCOPE, email)
    delay = rate_limit.progressive_delay_seconds(
        failures,
        free_failures=settings.login_delay_free_failures,
        base_seconds=settings.login_delay_base_seconds,
        max_seconds=settings.login_delay_max_seconds,
    )
    if delay > 0:
        logger.info("login_delayed", seconds=delay)
        await sleep(delay)


@router.get("/options", response_model=AuthOptions)
async def auth_options(settings: SettingsDep) -> AuthOptions:
    """Password rules and SSO availability, for the sign-in pages (no sign-in needed)."""
    return AuthOptions(
        password_min_length=settings.password_min_length,
        password_max_length=settings.password_max_length,
        sso_enabled=settings.oidc_configured,
        sso_provider_name=settings.oidc_provider_name,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    client_ip: ClientIP,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> LoginResponse:
    """Sign in with email and password and start a session.

    Attempts are limited per client address (hard limit, 429) and slowed per
    account (progressive delay, never refused).
    """
    window = settings.login_rate_limit_window_seconds

    # The address limit also caps how many delayed requests one client can hold open.
    limited = await rate_limit.check(redis, _IP_SCOPE, client_ip, settings.login_rate_limit_per_ip)
    if not limited.allowed:
        logger.warning("login_rate_limited")
        raise _too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _IP_SCOPE, client_ip, window)
    await _throttle_account(redis, settings, body.email)

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


@router.get("/me/roles", response_model=list[AssignmentRead])
async def my_roles(user: CurrentUser, db: DbSession) -> list[RoleAssignment]:
    """The signed-in user's current role assignments (for showing the right navigation)."""
    return await user_assignments(db, user.id)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    body: ChangePasswordRequest,
    auth: SessionAuth,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> None:
    """Change the signed-in user's password and sign out their other sessions."""
    user_id = str(auth.user.id)
    # Guessing the current password from a hijacked session is slowed the same way.
    await _throttle_account(redis, settings, auth.user.email)

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
    send_password_changed_notice.send(user_id)


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PasswordResetRequested,
)
async def request_password_reset(
    body: PasswordResetRequest,
    client_ip: ClientIP,
    redis: RedisDep,
    settings: SettingsDep,
) -> PasswordResetRequested:
    """Email a password reset link, if the account exists and can use one.

    The response is the same either way, and the account lookup happens in a
    background job, so neither content nor timing reveals whether it exists.
    """
    limited = await rate_limit.check(
        redis, _RESET_IP_SCOPE, client_ip, settings.password_reset_per_ip
    )
    if not limited.allowed:
        raise _too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(
        redis, _RESET_IP_SCOPE, client_ip, settings.login_rate_limit_window_seconds
    )

    send_password_reset.send(body.email)
    return PasswordResetRequested()


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> None:
    """Set a new password with a reset token and sign out every session."""
    try:
        user = await reset_password(
            db, redis, settings, token=body.token, new_password=body.new_password
        )
    except InvalidResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Please request a new one.",
        ) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    revoked = await sessions.revoke_user_sessions(redis, user.id)
    # Sign-in delays from guesses against this account no longer apply.
    await rate_limit.reset(redis, _ACCOUNT_SCOPE, user.email)
    logger.info("password_reset_completed", user_id=str(user.id), sessions_revoked=revoked)
    send_password_changed_notice.send(str(user.id))
