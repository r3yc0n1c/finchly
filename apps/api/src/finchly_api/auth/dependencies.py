"""Authentication and authorization dependencies for FastAPI endpoints."""

import json
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime

import asyncpg
from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from finchly_api.auth.api_keys import hash_api_key_secret, parse_api_key
from finchly_api.auth.context import AuthContext
from finchly_api.auth.sessions import SESSION_COOKIE_NAME
from finchly_api.db import get_db_pool


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Provide a database connection from the pool."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        yield conn


async def get_current_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_token_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> AuthContext:
    """Resolve and authenticate caller identity via API key or server-side session.

    Enforces:
    - Opaque API key verification with SHA-256 hash lookup and expiry/revocation checks.
    - Server-side session verification with expiry check.
    - CSRF protection for session-based state-changing requests (POST, PUT, PATCH, DELETE).
    """
    # 1. Bearer API Key Authentication
    if authorization and authorization.startswith("Bearer "):
        key_str = authorization.removeprefix("Bearer ").strip()
        try:
            prefix, secret = parse_api_key(key_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key format.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        key_hash = hash_api_key_secret(secret)
        row = await conn.fetchrow(
            """
            SELECT id, tenant_id, scopes, expires_at, revoked_at
            FROM api_keys
            WHERE key_prefix = $1 AND key_hash = $2
            """,
            prefix,
            key_hash,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unknown API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if row["revoked_at"] is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if row["expires_at"] is not None and row["expires_at"] <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        scopes_raw = row["scopes"]
        if isinstance(scopes_raw, str):
            scopes = json.loads(scopes_raw)
        elif isinstance(scopes_raw, list):
            scopes = scopes_raw
        else:
            scopes = []

        return AuthContext(
            tenant_id=row["tenant_id"],
            user_id=None,
            auth_type="api_key",
            scopes=scopes,
            role=None,
        )

    # 2. Server-Side Session Cookie Authentication
    if session_cookie:
        row = await conn.fetchrow(
            """
            SELECT s.id, s.user_id, s.tenant_id, s.csrf_token, s.expires_at, tm.role
            FROM sessions s
            JOIN tenant_members tm ON tm.tenant_id = s.tenant_id AND tm.user_id = s.user_id
            WHERE s.id = $1
            """,
            session_cookie,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session invalid or expired.",
            )

        if row["expires_at"] <= datetime.now(UTC):
            await conn.execute("DELETE FROM sessions WHERE id = $1;", session_cookie)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired.",
            )

        # Enforce CSRF token check on state-changing browser requests
        if request.method in (
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ) and (not csrf_token_header or csrf_token_header != row["csrf_token"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed: missing or invalid X-CSRF-Token header.",
            )

        return AuthContext(
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            auth_type="session",
            scopes=["*"],
            role=row["role"],
        )

    # 3. Unauthenticated request
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a valid Bearer API key or session cookie.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scope(required_scope: str) -> Callable[[AuthContext], AuthContext]:
    """Dependency factory checking that authenticated caller possesses required scope."""

    def _scope_checker(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if not auth.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires scope '{required_scope}'.",
            )
        return auth

    return _scope_checker
