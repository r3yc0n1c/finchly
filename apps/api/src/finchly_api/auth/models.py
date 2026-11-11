"""Pydantic models for authentication and API key management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """User login request payload."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password")


class LoginResponse(BaseModel):
    """User login response payload."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    tenant_id: UUID
    csrf_token: str


class CurrentUserResponse(BaseModel):
    """Current authenticated user metadata."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None
    tenant_id: UUID
    auth_type: str  # "session" | "api_key"
    role: str | None
    scopes: list[str]


class CreateApiKeyRequest(BaseModel):
    """Request payload to generate a new API key."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", description="Descriptive label for this API key")
    scopes: list[str] = Field(default_factory=lambda: ["*"], description="Authorized scopes")
    expires_in_days: int | None = Field(
        default=None, ge=1, le=365, description="Optional validity window in days"
    )


class ApiKeyResponse(BaseModel):
    """API key creation and query response.

    Note: The 'key' attribute contains the full plaintext key and is ONLY populated
    on initial creation. It is never stored or returned again.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    key_prefix: str
    key: str | None = None
    scopes: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class RevokeApiKeyResponse(BaseModel):
    """Confirmation payload for API key revocation."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    revoked: bool
    revoked_at: datetime
