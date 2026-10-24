"""Pytest configuration and fixtures."""

import os
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

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
