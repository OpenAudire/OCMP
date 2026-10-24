"""Fixed-window counters backed by Redis, for rate limits and progressive delays."""

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


async def count(redis: Redis, scope: str, identifier: str) -> int:
    """Current number of hits in the identifier's window."""
    value = await redis.get(_key(scope, identifier))
    return int(value) if value is not None else 0


def progressive_delay_seconds(
    failures: int, *, free_failures: int, base_seconds: float, max_seconds: float
) -> float:
    """Delay before the next attempt, doubling with each failure past the free ones.

    With 3 free failures and a 1 s base: failures 0-2 -> 0 s, 3 -> 1 s, 4 -> 2 s,
    5 -> 4 s, ... capped at ``max_seconds``.
    """
    excess = failures - free_failures
    if excess < 0:
        return 0.0
    # Cap the exponent too, so huge failure counts cannot overflow.
    return float(min(base_seconds * 2 ** min(excess, 32), max_seconds))


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
