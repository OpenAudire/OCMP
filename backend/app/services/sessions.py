"""Server-side sessions stored in Redis.

The browser holds an opaque random token; Redis holds only its SHA-256 hash,
mapped to the user id. Each user also has a set of their session hashes so all
sessions can be revoked at once (password change, deactivation).
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.security import generate_token, hash_token

_SESSION_KEY = "ocmp:session:{}"
_USER_SESSIONS_KEY = "ocmp:user-sessions:{}"


@dataclass(frozen=True)
class SessionData:
    """What a session resolves to."""

    user_id: uuid.UUID
    created_at: datetime


async def create_session(redis: Redis, user_id: uuid.UUID, ttl_seconds: int) -> str:
    """Create a session and return the token to put in the cookie."""
    token = generate_token()
    token_hash = hash_token(token)
    payload = json.dumps({"user_id": str(user_id), "created_at": datetime.now(UTC).isoformat()})
    user_key = _USER_SESSIONS_KEY.format(user_id)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(_SESSION_KEY.format(token_hash), payload, ex=ttl_seconds)
        pipe.sadd(user_key, token_hash)
        pipe.expire(user_key, ttl_seconds)
        await pipe.execute()
    return token


async def get_session(redis: Redis, token: str, ttl_seconds: int) -> SessionData | None:
    """Resolve a session token and extend its lifetime (sliding expiry)."""
    key = _SESSION_KEY.format(hash_token(token))
    raw = await redis.get(key)
    if raw is None:
        return None

    data = json.loads(raw)
    user_id = uuid.UUID(data["user_id"])
    async with redis.pipeline(transaction=True) as pipe:
        pipe.expire(key, ttl_seconds)
        pipe.expire(_USER_SESSIONS_KEY.format(user_id), ttl_seconds)
        await pipe.execute()
    return SessionData(user_id=user_id, created_at=datetime.fromisoformat(data["created_at"]))


async def delete_session(redis: Redis, token: str) -> None:
    """Delete one session (logout)."""
    token_hash = hash_token(token)
    key = _SESSION_KEY.format(token_hash)
    raw = await redis.get(key)
    await redis.delete(key)
    if raw is not None:
        user_id = json.loads(raw)["user_id"]
        await redis.srem(_USER_SESSIONS_KEY.format(user_id), token_hash)


async def revoke_user_sessions(
    redis: Redis, user_id: uuid.UUID, *, keep_token: str | None = None
) -> int:
    """Delete every session of a user, optionally keeping the current one.

    Returns:
        The number of sessions deleted.
    """
    user_key = _USER_SESSIONS_KEY.format(user_id)
    keep_hash = hash_token(keep_token) if keep_token else None
    hashes = [h for h in await redis.smembers(user_key) if h != keep_hash]
    if not hashes:
        return 0

    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(*(_SESSION_KEY.format(h) for h in hashes))
        pipe.srem(user_key, *hashes)
        await pipe.execute()
    return len(hashes)
