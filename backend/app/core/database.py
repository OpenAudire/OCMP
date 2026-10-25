"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

# Engine and session factory (initialized on startup)
_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_database(settings: Settings) -> None:
    """Initialize the database engine and session factory.

    Args:
        settings: Application settings containing database URL.
    """
    global _engine, _async_session_factory

    _engine = create_async_engine(
        str(settings.database_url),
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def close_database() -> None:
    """Close the database engine and release connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection.

    Yields:
        An async database session.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """A session outside a request (commands, scripts), committed on success."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Check if the database connection is healthy.

    Returns:
        True if the database is reachable, False otherwise.
    """
    if _engine is None:
        return False

    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# Type alias for dependency injection. "function" scope commits when the endpoint
# returns, before the response is sent: a client that reads right after a write sees
# the change, and a failed commit is an error response instead of a false success.
# (FastAPI's default for dependencies with yield ends them after the response.)
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
