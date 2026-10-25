"""First-run setup (works without signing in, protected by the setup token)."""

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import (
    ClientIP,
    RedisDep,
    SettingsDep,
    session_ttl_seconds,
    set_session_cookies,
    too_many_attempts,
)
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.security import PasswordPolicyError, csrf_token_for
from app.schemas.auth import LoginResponse, UserRead
from app.services import rate_limit, sessions
from app.services.authorization import InvalidRequestError
from app.services.setup import SetupRequest, complete_setup, setup_needed
from app.services.users import InvalidEmailError, UserAlreadyExistsError

router = APIRouter(prefix="/setup", tags=["setup"])
logger = get_logger(__name__)

_IP_SCOPE = "setup-ip"
_ATTEMPTS_PER_WINDOW = 10


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupBody(BaseModel):
    token: str = Field(min_length=1, max_length=64)
    institution_name: str = Field(min_length=2, max_length=255)
    institution_short_code: str = Field(pattern=r"^[A-Za-z0-9-]{2,32}$")
    # ISO 3166-1 alpha-2, e.g. ZA.
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    health_profile: bool = False
    admin_display_name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_password: str = Field(min_length=1, max_length=1024)


@router.get("/status", response_model=SetupStatus)
async def setup_status(db: DbSession) -> SetupStatus:
    """Whether this instance still needs first-run setup."""
    return SetupStatus(needs_setup=await setup_needed(db))


@router.post("", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def run_setup(
    body: SetupBody,
    request: Request,
    response: Response,
    client_ip: ClientIP,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> LoginResponse:
    """Create the institution and first platform admin, and sign the admin in."""
    limited = await rate_limit.check(redis, _IP_SCOPE, client_ip, _ATTEMPTS_PER_WINDOW)
    if not limited.allowed:
        raise too_many_attempts(limited.retry_after_seconds)
    await rate_limit.hit(redis, _IP_SCOPE, client_ip, settings.login_rate_limit_window_seconds)

    try:
        admin = await complete_setup(
            db,
            settings,
            SetupRequest(
                token=body.token,
                institution_name=body.institution_name,
                institution_short_code=body.institution_short_code,
                country=body.country,
                health_profile=body.health_profile,
                admin_display_name=body.admin_display_name,
                admin_email=body.admin_email,
                admin_password=body.admin_password,
            ),
        )
    except (InvalidEmailError, PasswordPolicyError, UserAlreadyExistsError) as exc:
        raise InvalidRequestError(str(exc)) from exc

    old_token = request.cookies.get(settings.session_cookie_name)
    if old_token:
        await sessions.delete_session(redis, old_token)
    token = await sessions.create_session(redis, admin.id, session_ttl_seconds(settings))
    set_session_cookies(response, settings, token)
    logger.info("setup_completed", user_id=str(admin.id))
    return LoginResponse(
        user=UserRead.model_validate(admin), csrf_token=csrf_token_for(token, settings.secret_key)
    )
