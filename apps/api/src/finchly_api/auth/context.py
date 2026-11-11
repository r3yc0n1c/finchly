"""Authenticated security context passed to request handlers."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AuthContext:
    """Security context holding tenant, user, scopes, and authentication method."""

    tenant_id: UUID
    user_id: UUID | None
    auth_type: str  # "session" | "api_key"
    scopes: list[str]
    role: str | None = None

    def has_scope(self, required_scope: str) -> bool:
        """Check if context holds the required permission scope or global wildcard."""
        if "*" in self.scopes or "all" in self.scopes:
            return True
        return required_scope in self.scopes
