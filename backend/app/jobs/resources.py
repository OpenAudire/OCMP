"""Database and Redis connections for background jobs.

Each job runs its coroutine with ``asyncio.run``, i.e. on a fresh event loop,
so connections are opened per job rather than pooled across loops.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings


@asynccontextmanager
async def job_resources(settings: Settings) -> AsyncIterator[tuple[AsyncSession, Redis]]:
    """A database session (committed on success) and a Redis client for one job."""
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
    redis = Redis.from_url(str(settings.redis_url), encoding="utf-8", decode_responses=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session, redis
            await session.commit()
    finally:
        await redis.aclose()
        await engine.dispose()
