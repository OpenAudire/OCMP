"""Tests for health check endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        secret_key="test-secret-key-that-is-at-least-32-characters-long",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        debug=True,
    )


@pytest.fixture
def app(mock_settings: Settings):
    """Create test application with mocked settings."""
    with patch("app.main.get_settings", return_value=mock_settings):
        # Import here to get fresh app with mocked settings
        from app.main import create_app

        return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_returns_healthy(client: AsyncClient):
    """Test health endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_with_healthy_dependencies(client: AsyncClient):
    """Test ready endpoint when all dependencies are healthy."""
    with (
        patch(
            "app.api.health.check_database_connection",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.api.health.check_redis_connection",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "up"
        assert data["redis"] == "up"


@pytest.mark.asyncio
async def test_ready_with_database_down(client: AsyncClient):
    """Test ready endpoint when database is down."""
    with (
        patch(
            "app.api.health.check_database_connection",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.api.health.check_redis_connection",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        response = await client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "down"
        assert data["redis"] == "up"


@pytest.mark.asyncio
async def test_ready_with_redis_down(client: AsyncClient):
    """Test ready endpoint when Redis is down."""
    with (
        patch(
            "app.api.health.check_database_connection",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.api.health.check_redis_connection",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        response = await client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "up"
        assert data["redis"] == "down"


@pytest.mark.asyncio
async def test_ready_with_all_dependencies_down(client: AsyncClient):
    """Test ready endpoint when all dependencies are down."""
    with (
        patch(
            "app.api.health.check_database_connection",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.api.health.check_redis_connection",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        response = await client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "down"
        assert data["redis"] == "down"
