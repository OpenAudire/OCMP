"""FastAPI application entry point."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.errors import AIRefusedError, ProviderError
from app.api.health import router as health_router
from app.api.v1 import router as v1_router
from app.core.audit_context import AuditContextMiddleware
from app.core.config import Settings, get_settings
from app.core.csrf import CSRFMiddleware
from app.core.database import close_database, init_database, session_scope
from app.core.logging import get_logger, setup_logging
from app.core.proxy import TrustedProxies
from app.core.redis import close_redis, init_redis
from app.services.authorization import AuthorizationError, ConflictError, InvalidRequestError
from app.services.setup import setup_needed, setup_token

logger = get_logger(__name__)


async def _announce_setup_token(settings: Settings) -> None:
    """While first-run setup is pending, log the token the operator needs for it."""
    try:
        async with session_scope() as db:
            pending = await setup_needed(db)
    except Exception:  # database not reachable or not migrated yet
        logger.warning("setup_status_unknown")
        return
    if pending:
        logger.warning(
            "First-run setup is pending: open the site and enter this setup token",
            setup_token=setup_token(settings),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for the application.
    """
    settings = get_settings()

    # Setup logging
    setup_logging(
        log_level=settings.log_level,
        json_logs=not settings.debug,
    )

    logger.info(
        "Starting Curriculum in Context API",
        version=settings.app_version,
        debug=settings.debug,
    )

    if settings.secrets_key_missing_in_production:
        logger.warning(
            "SECRETS_ENCRYPTION_KEYS is not set in production: AI provider keys cannot be "
            "saved until it is. Make one with 'python -m app.cli new-encryption-key' and add "
            "it to .env (ADR 041)."
        )

    # Initialize database
    init_database(settings)
    logger.info("Database initialized")

    # Initialize Redis
    init_redis(settings)
    logger.info("Redis initialized")

    await _announce_setup_token(settings)

    yield

    # Cleanup
    logger.info("Shutting down Curriculum in Context API")
    oidc_client = getattr(app.state, "oidc_client", None)
    if oidc_client is not None:
        await oidc_client.http.aclose()
    await close_database()
    await close_redis()


def _error_handler(status_code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Curriculum in Context API",
        description="Curriculum mapping: programmes, objectives, frameworks and mappings.",
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.state.trusted_proxies = TrustedProxies(settings.trusted_proxies)

    # Service-layer errors become HTTP errors with the service's message.
    for error, code in (
        (AuthorizationError, status.HTTP_403_FORBIDDEN),
        (InvalidRequestError, status.HTTP_422_UNPROCESSABLE_CONTENT),
        (ConflictError, status.HTTP_409_CONFLICT),
        # AI calls: refused before anything was sent, or the provider failed.
        (AIRefusedError, status.HTTP_409_CONFLICT),
        (ProviderError, status.HTTP_502_BAD_GATEWAY),
    ):
        app.add_exception_handler(error, _error_handler(code))

    # CSRF check for cookie-authenticated unsafe requests (inside CORS, so
    # rejections still carry CORS headers)
    app.add_middleware(CSRFMiddleware, settings=settings)

    # Outermost: each request starts with no audit actor.
    app.add_middleware(AuditContextMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check routes (no /api/v1 prefix)
    app.include_router(health_router)
    app.include_router(v1_router)

    return app


# Create application instance
app = create_app()
