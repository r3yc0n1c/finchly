"""Finchly API entrypoint and application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI

from finchly_api.auth import auth_router
from finchly_api.db import close_db_pool, init_db_pool
from finchly_api.health import router as health_router
from finchly_domain.errors import ERROR_CATALOGUE, ErrorDetail


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle resources."""
    with suppress(Exception):
        await init_db_pool()
    yield
    await close_db_pool()


app = FastAPI(
    title="Finchly API",
    description="Finchly control plane API for auditable business document processing.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# Root level health probes (K8s / Compose standard)
app.include_router(health_router)

# Base API v1 router
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)


@api_v1_router.get("/info", tags=["system"], summary="System metadata")
async def get_system_info() -> dict[str, str]:
    """Retrieve Finchly service metadata."""
    return {
        "service": "finchly-api",
        "version": "0.1.0",
        "status": "operational",
    }


@api_v1_router.get(
    "/error-catalogue",
    tags=["system"],
    summary="Cataloged system error codes",
    response_model=dict[str, ErrorDetail],
)
async def get_error_catalogue() -> dict[str, ErrorDetail]:
    """Expose the canonical catalogue of system error codes."""
    return {code.value: detail for code, detail in ERROR_CATALOGUE.items()}


app.include_router(api_v1_router)
