"""Health check endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.database import check_database_connection
from app.core.redis import check_redis_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "unhealthy"]


class ReadyResponse(BaseModel):
    """Readiness check response with component status."""

    status: Literal["ready", "not_ready"]
    database: Literal["up", "down"]
    redis: Literal["up", "down"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns a simple health status. Used by load balancers and
    container orchestrators to check if the service is alive.

    This endpoint does NOT check dependencies - use /ready for that.
    """
    return HealthResponse(status="healthy")


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness check endpoint.

    Checks if the service is ready to handle requests by verifying
    connections to all required dependencies (database, Redis).

    Returns detailed status of each component.
    """
    db_healthy = await check_database_connection()
    redis_healthy = await check_redis_connection()

    all_healthy = db_healthy and redis_healthy

    return ReadyResponse(
        status="ready" if all_healthy else "not_ready",
        database="up" if db_healthy else "down",
        redis="up" if redis_healthy else "down",
    )
