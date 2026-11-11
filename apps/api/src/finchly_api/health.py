"""Health and readiness endpoints for Finchly API."""

import asyncio
from typing import Any

import asyncpg
import httpx
import nats
from fastapi import APIRouter, Response, status

from finchly_api.config import settings

router = APIRouter(tags=["health"])


async def check_postgres() -> tuple[bool, str]:
    """Check connectivity to PostgreSQL database."""
    try:
        # Use timeout=2.0s to avoid blocking during network failure
        conn = await asyncio.wait_for(
            asyncpg.connect(settings.database_url, timeout=2.0),
            timeout=2.5,
        )
        try:
            val = await conn.fetchval("SELECT 1")
            if val == 1:
                return True, "ok"
            return False, f"unexpected query result: {val}"
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"connection failed: {exc.__class__.__name__}: {exc}"


async def check_nats() -> tuple[bool, str]:
    """Check connectivity to NATS message broker."""
    try:
        nc = await asyncio.wait_for(
            nats.connect(settings.nats_url, connect_timeout=2.0),
            timeout=2.5,
        )
        try:
            if nc.is_connected:
                return True, "ok"
            return False, "nats not connected"
        finally:
            await nc.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"connection failed: {exc.__class__.__name__}: {exc}"


async def check_minio() -> tuple[bool, str]:
    """Check connectivity to MinIO / S3 storage."""
    try:
        # MinIO provides /minio/health/live for unauthenticated liveness probes
        health_url = f"{settings.s3_endpoint_url.rstrip('/')}/minio/health/live"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                return True, "ok"
            return False, f"unexpected status code: {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"connection failed: {exc.__class__.__name__}: {exc}"


@router.get(
    "/healthz",
    summary="Liveness probe",
    description="Returns 200 when the process is alive.",
    status_code=status.HTTP_200_OK,
)
async def healthz() -> dict[str, str]:
    """Process liveness probe."""
    return {"status": "ok"}


@router.get(
    "/readyz",
    summary="Readiness probe",
    description="Returns 200 when all dependencies (Postgres, NATS, MinIO) are reachable, 503 otherwise.",
)
async def readyz(response: Response) -> dict[str, Any]:
    """Cluster readiness probe verifying external dependency connectivity."""
    pg_ok, pg_msg = await check_postgres()
    nats_ok, nats_msg = await check_nats()
    minio_ok, minio_msg = await check_minio()

    all_ready = pg_ok and nats_ok and minio_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": {
            "postgres": pg_msg,
            "nats": nats_msg,
            "minio": minio_msg,
        },
    }
