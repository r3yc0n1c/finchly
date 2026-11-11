"""Authentication and session management module."""

from finchly_api.auth.context import AuthContext
from finchly_api.auth.dependencies import get_current_auth, require_scope
from finchly_api.auth.password import hash_password, verify_password
from finchly_api.auth.router import router as auth_router

__all__ = [
    "AuthContext",
    "auth_router",
    "get_current_auth",
    "hash_password",
    "require_scope",
    "verify_password",
]
