"""Pytest configuration and fixtures."""

import os
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.redis import get_redis

# Importing app.main builds a module-level app from the environment. Provide safe
# defaults so that works anywhere; tests needing specific settings override them.
# (Do not patch app.core.config.get_settings instead: modules imported under the
# patch would capture the mock in their Depends(...) declarations.)
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Database tests need a disposable PostgreSQL (with pgvector). Locally:
#   docker run -d --name ocmp-test-db -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
#     -e POSTGRES_DB=ocmp_test -p 55432:5432 pgvector/pgvector:pg16
#   TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/ocmp_test pytest
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio backend for async tests."""
    return "asyncio"


def alembic_config(database_url: str) -> Config:
    """Build an Alembic config pointing at the given database."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


def run_alembic(fn: Callable[[], None]) -> None:
    """Run an Alembic command in a worker thread.

    The migration environment calls ``asyncio.run``, which must not share a
    thread with the test event loop.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(fn).result()


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of the test database; skips database tests when it is not configured."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    """Reset the test database and apply all migrations once per test session."""
    config = alembic_config(database_url)
    run_alembic(lambda: command.downgrade(config, "base"))
    run_alembic(lambda: command.upgrade(config, "head"))
    return database_url


@pytest.fixture
async def db_session(migrated_database: str) -> AsyncGenerator[AsyncSession, None]:
    """Session bound to an outer transaction that is rolled back after each test.

    Code under test may call ``commit()``; with ``create_savepoint`` those
    commits only release savepoints inside the outer transaction.
    """
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def test_settings() -> Settings:
    """Settings for API tests (never read from the environment's secrets)."""
    return Settings(
        secret_key="test-secret-key-that-is-at-least-32-characters-long",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        login_rate_limit_per_ip=20,
        # The test client connects directly (no proxy).
        trusted_proxies=[],
    )


@pytest.fixture
async def redis_client() -> AsyncGenerator[FakeAsyncRedis, None]:
    """In-memory Redis, fresh for each test."""
    client = FakeAsyncRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def api_app(
    test_settings: Settings, db_session: AsyncSession, redis_client: FakeAsyncRedis
) -> FastAPI:
    """The FastAPI app wired to the test database session, fake Redis and test settings."""
    with patch("app.main.get_settings", return_value=test_settings):
        from app.main import create_app

        app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    return app


@pytest.fixture
async def api_client(api_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """HTTPS client (so Secure cookies are sent) for the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="https://testserver"
    ) as client:
        yield client
