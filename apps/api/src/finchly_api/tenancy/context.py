"""Tenant context storage using contextvars per ADR-009 §3."""

from contextvars import ContextVar, Token
from uuid import UUID

_current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> UUID | None:
    """Retrieve tenant ID for current execution context."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: UUID | None) -> Token[UUID | None]:
    """Set tenant ID for current execution context and return the restoration token."""
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token[UUID | None]) -> None:
    """Restore previous tenant ID using the token from set_current_tenant_id."""
    _current_tenant_id.reset(token)
