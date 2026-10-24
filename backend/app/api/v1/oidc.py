"""Sign-in with an OpenID Connect provider (e.g. Microsoft Entra ID).

These endpoints are browser navigations, not API calls: they answer with
redirects, and report failures to the frontend as ``/login?sso_error=<code>``.
"""

import json
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api.deps import ClientIP, RedisDep, SettingsDep, session_ttl_seconds, set_session_cookies
from app.core.config import Settings
from app.core.database import DbSession
from app.core.logging import get_logger
from app.core.security import generate_token, hash_token
from app.services import rate_limit, sessions
from app.services.oidc import OIDCClient, OIDCError
from app.services.sso import ExternalIdentity, SSOSignInError, sign_in_external

router = APIRouter(prefix="/auth/oidc", tags=["auth"])
logger = get_logger(__name__)

STATE_COOKIE = "ocmp_oidc_state"
STATE_COOKIE_PATH = "/api/v1/auth/oidc"
STATE_TTL_SECONDS = 600
_STATE_KEY = "ocmp:oidc-state:{}"
_IP_SCOPE = "login-ip"  # SSO starts count toward the same per-address sign-in limit


class OIDCInfo(BaseModel):
    """What the sign-in page needs to show an SSO button."""

    enabled: bool
    provider_name: str


def get_oidc_client(request: Request, settings: SettingsDep) -> OIDCClient:
    """The app's OIDC client; 404 when SSO is not configured."""
    if not settings.oidc_configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO is not enabled.")
    client: OIDCClient | None = getattr(request.app.state, "oidc_client", None)
    if client is None:
        client = OIDCClient(settings, httpx.AsyncClient(timeout=10.0))
        request.app.state.oidc_client = client
    return client


OIDCClientDep = Annotated[OIDCClient, Depends(get_oidc_client)]


def safe_next(target: str | None) -> str:
    """Only allow redirects to a path on this site (no open redirects)."""
    if (
        not target
        or len(target) > 2048
        or not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or any(ord(c) < 0x20 for c in target)
    ):
        return "/"
    return target


def _fail(code: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?sso_error={code}", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return response


@router.get("", response_model=OIDCInfo)
async def oidc_info(settings: SettingsDep) -> OIDCInfo:
    """Whether SSO sign-in is available, and what to call it."""
    return OIDCInfo(enabled=settings.oidc_configured, provider_name=settings.oidc_provider_name)


@router.get("/login")
async def oidc_login(
    client_ip: ClientIP,
    redis: RedisDep,
    settings: SettingsDep,
    client: OIDCClientDep,
    next: Annotated[str | None, Query(max_length=2048)] = None,
) -> RedirectResponse:
    """Start SSO sign-in: redirect to the provider."""
    limited = await rate_limit.check(redis, _IP_SCOPE, client_ip, settings.login_rate_limit_per_ip)
    if not limited.allowed:
        return _fail("too_many_attempts")
    await rate_limit.hit(redis, _IP_SCOPE, client_ip, settings.login_rate_limit_window_seconds)

    state, nonce, code_verifier = generate_token(), generate_token(), generate_token()
    try:
        url = await client.authorization_url(state=state, nonce=nonce, code_verifier=code_verifier)
    except OIDCError as exc:
        logger.warning("oidc_unavailable", reason=exc.detail)
        return _fail(exc.code)

    await redis.set(
        _STATE_KEY.format(hash_token(state)),
        json.dumps({"nonce": nonce, "code_verifier": code_verifier, "next": safe_next(next)}),
        ex=STATE_TTL_SECONDS,
    )
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    # Binds the transaction to this browser (RFC 9700 section 4.7.1). SameSite=Lax
    # cookies are sent on the provider's top-level redirect back to the callback.
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=STATE_COOKIE_PATH,
    )
    return response


async def _take_state(redis: Redis, request: Request, state: str | None) -> dict[str, str]:
    """Consume the sign-in transaction for this callback (single use)."""
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not state or not cookie_state or cookie_state != state:
        raise OIDCError("sso_expired", "Sign-in state missing or does not match this browser.")
    raw = await redis.getdel(_STATE_KEY.format(hash_token(state)))
    if raw is None:
        raise OIDCError("sso_expired", "Sign-in state unknown, expired or already used.")
    data: dict[str, str] = json.loads(raw)
    return data


def _identity_from_claims(issuer: str, claims: dict[str, object]) -> ExternalIdentity:
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        # Entra ID often omits `email`; its username is usually the address.
        username = claims.get("preferred_username")
        email = username if isinstance(username, str) and "@" in username else None
    name = claims.get("name")
    return ExternalIdentity(
        protocol="oidc",
        issuer=issuer,
        subject=str(claims["sub"]),
        email=email,
        display_name=name if isinstance(name, str) else None,
    )


async def _complete(
    request: Request,
    db: DbSession,
    redis: Redis,
    settings: Settings,
    client: OIDCClient,
    code: str | None,
    state: str | None,
) -> RedirectResponse:
    transaction = await _take_state(redis, request, state)
    if not code:
        raise OIDCError("sso_failed", "Provider returned no authorization code.")
    id_token = await client.exchange_code(code=code, code_verifier=transaction["code_verifier"])
    claims = await client.validate_id_token(id_token, nonce=transaction["nonce"])
    issuer = (await client.metadata()).issuer
    user = await sign_in_external(db, settings, _identity_from_claims(issuer, claims))

    old_token = request.cookies.get(settings.session_cookie_name)
    if old_token:
        await sessions.delete_session(redis, old_token)
    token = await sessions.create_session(redis, user.id, session_ttl_seconds(settings))

    response = RedirectResponse(
        safe_next(transaction.get("next")), status_code=status.HTTP_302_FOUND
    )
    set_session_cookies(response, settings, token)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    logger.info("oidc_login_succeeded", user_id=str(user.id))
    return response


@router.get("/callback")
async def oidc_callback(
    request: Request,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    client: OIDCClientDep,
    code: Annotated[str | None, Query(max_length=4096)] = None,
    state: Annotated[str | None, Query(max_length=512)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> RedirectResponse:
    """Finish SSO sign-in after the provider redirects back."""
    if error:
        # e.g. access_denied when the user cancels at the provider.
        logger.info("oidc_provider_error", error=error)
        return _fail("sso_cancelled" if error == "access_denied" else "sso_failed")
    try:
        return await _complete(request, db, redis, settings, client, code, state)
    except OIDCError as exc:
        logger.warning("oidc_login_failed", code=exc.code, reason=exc.detail)
        return _fail(exc.code)
    except SSOSignInError as exc:
        logger.info("oidc_login_refused", code=exc.code)
        return _fail(exc.code)
