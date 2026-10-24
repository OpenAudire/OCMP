"""Tests for main application endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Create test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """Test health endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_ready(client: AsyncClient):
    """Test ready endpoint returns ready status."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
