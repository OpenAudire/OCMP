"""CSRF protection for cookie-authenticated requests.

Every state-changing request under ``/api/`` that carries a session cookie must
send the session's CSRF token (see ``csrf_token_for``) in the CSRF header.
Requests without a session cookie are not authenticated by cookie, so they are
not exposed to CSRF; endpoints that need a user reject them anyway.

Sign-in and first-run setup are exempt: a stale cookie from an expired
session must not block them, and both always issue a fresh session.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.security import csrf_token_matches

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
EXEMPT_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/setup"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject unsafe requests whose CSRF header does not match the session."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        session_token = request.cookies.get(self.settings.session_cookie_name)
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.url.path not in EXEMPT_PATHS
            and session_token
        ):
            submitted = request.headers.get(self.settings.csrf_header_name, "")
            if not csrf_token_matches(session_token, submitted, self.settings.secret_key):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid."},
                )
        return await call_next(request)
