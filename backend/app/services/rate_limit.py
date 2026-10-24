"""Fixed-window rate limiting backed by Redis."""

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.security import hash_token

_KEY = "ocmp:ratelimit:{}:{}"


@dataclass(frozen=True)
class RateLimitStatus:
    """Result of a rate limit check."""

    allowed: bool
    retry_after_seconds: int


def _key(scope: str, identifier: str) -> str:
    # Identifiers (email addresses, client IPs) are hashed so Redis holds no personal data.
    return _KEY.format(scope, hash_token(identifier.casefold()))


async def check(redis: Redis, scope: str, identifier: str, limit: int) -> RateLimitStatus:
    """Check whether the identifier is under its limit, without counting a hit."""
    key = _key(scope, identifier)
    count = await redis.get(key)
    if count is not None and int(count) >= limit:
        return RateLimitStatus(allowed=False, retry_after_seconds=max(await redis.ttl(key), 1))
    return RateLimitStatus(allowed=True, retry_after_seconds=0)


async def hit(redis: Redis, scope: str, identifier: str, window_seconds: int) -> None:
    """Count one hit; the window starts at the first hit."""
    key = _key(scope, identifier)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        await pipe.execute()


async def reset(redis: Redis, scope: str, identifier: str) -> None:
    """Clear the counter (e.g. after a successful login)."""
    await redis.delete(_key(scope, identifier))
