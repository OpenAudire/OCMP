"""Redis connection management."""

from redis.asyncio import Redis

from app.core.config import Settings

# Redis client (initialized on startup)
_redis_client: Redis | None = None


def init_redis(settings: Settings) -> None:
    """Initialize the Redis client.

    Args:
        settings: Application settings containing Redis URL.
    """
    global _redis_client
    _redis_client = Redis.from_url(
        str(settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
    )


async def close_redis() -> None:
    """Close the Redis client and release connections."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> Redis:
    """Get the Redis client instance.

    Returns:
        The Redis client.

    Raises:
        RuntimeError: If Redis has not been initialized.
    """
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client


async def check_redis_connection() -> bool:
    """Check if the Redis connection is healthy.

    Returns:
        True if Redis is reachable, False otherwise.
    """
    if _redis_client is None:
        return False

    try:
        await _redis_client.ping()
        return True
    except Exception:
        return False
