"""Unit tests for /readyz endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finchly_api.main import app


@pytest.mark.asyncio
async def test_readyz_returns_200_when_all_healthy() -> None:
    """Verify /readyz returns 200 when Postgres, NATS, and MinIO are healthy."""
    with (
        patch("finchly_api.health.check_postgres", new_callable=AsyncMock) as mock_pg,
        patch("finchly_api.health.check_nats", new_callable=AsyncMock) as mock_nats,
        patch("finchly_api.health.check_minio", new_callable=AsyncMock) as mock_minio,
    ):
        mock_pg.return_value = (True, "ok")
        mock_nats.return_value = (True, "ok")
        mock_minio.return_value = (True, "ok")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["checks"] == {
                "postgres": "ok",
                "nats": "ok",
                "minio": "ok",
            }


@pytest.mark.asyncio
async def test_readyz_fails_when_postgres_stopped_and_recovers() -> None:
    """Verify /readyz returns 503 when Postgres is down, and recovers to 200 when restored."""
    with (
        patch("finchly_api.health.check_postgres", new_callable=AsyncMock) as mock_pg,
        patch("finchly_api.health.check_nats", new_callable=AsyncMock) as mock_nats,
        patch("finchly_api.health.check_minio", new_callable=AsyncMock) as mock_minio,
    ):
        mock_nats.return_value = (True, "ok")
        mock_minio.return_value = (True, "ok")

        # Step 1: Postgres is down
        mock_pg.return_value = (False, "connection failed: ConnectionRefusedError")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert "connection failed" in data["checks"]["postgres"]

            # Step 2: Postgres recovers
            mock_pg.return_value = (True, "ok")
            response = await client.get("/readyz")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["checks"]["postgres"] == "ok"
