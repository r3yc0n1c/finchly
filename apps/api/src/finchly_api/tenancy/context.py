"""Tenant context storage using contextvars per ADR-009 §3."""

from contextvars import ContextVar
from uuid import UUID

_current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> UUID | None:
    """Retrieve tenant ID for current execution context."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: UUID | None) -> None:
    """Set tenant ID for current execution context."""
    _current_tenant_id.set(tenant_id)
