"""Finchly API entrypoint and application factory."""

from fastapi import APIRouter, FastAPI

from finchly_api.health import router as health_router
from finchly_domain.errors import ERROR_CATALOGUE, ErrorDetail

app = FastAPI(
    title="Finchly API",
    description="Finchly control plane API for auditable business document processing.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

# Root level health probes (K8s / Compose standard)
app.include_router(health_router)

# Base API v1 router
api_v1_router = APIRouter(prefix="/api/v1")


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
