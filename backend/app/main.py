"""FastAPI application entry point."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1 import router as v1_router
from app.core.audit_context import AuditContextMiddleware
from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.database import close_database, init_database
from app.core.logging import get_logger, setup_logging
from app.core.proxy import TrustedProxies
from app.core.redis import close_redis, init_redis
from app.services.authorization import AuthorizationError, ConflictError, InvalidRequestError

logger = get_logger(__name__)


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
        "Starting OCMP API",
        version=settings.app_version,
        debug=settings.debug,
    )

    # Initialize database
    init_database(settings)
    logger.info("Database initialized")

    # Initialize Redis
    init_redis(settings)
    logger.info("Redis initialized")

    yield

    # Cleanup
    logger.info("Shutting down OCMP API")
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
        title="OCMP API",
        description="Open Curriculum Mapping Platform API",
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
