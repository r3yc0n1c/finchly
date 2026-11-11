"""Authentication and API key management routes."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from finchly_api.auth.api_keys import generate_api_key
from finchly_api.auth.context import AuthContext
from finchly_api.auth.dependencies import get_current_auth, get_db_connection
from finchly_api.auth.models import (
    ApiKeyResponse,
    CreateApiKeyRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RevokeApiKeyResponse,
)
from finchly_api.auth.password import verify_password
from finchly_api.auth.rate_limit import is_account_locked, record_login_attempt
from finchly_api.auth.sessions import (
    DEFAULT_SESSION_TTL_HOURS,
    SESSION_COOKIE_NAME,
    calculate_session_expiry,
    generate_csrf_token,
    generate_session_id,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    summary="Authenticate user and establish session",
    response_model=LoginResponse,
)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> LoginResponse:
    """Authenticate with email and Argon2id password, establishing a server-side session."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 1. Rate limiting / Lockout check (5 failed attempts / 15 minutes)
    if await is_account_locked(conn, login_data.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to excessive failed login attempts. Try again in 15 minutes.",
        )

    # 2. Lookup user and verify Argon2id password
    user_row = await conn.fetchrow(
        "SELECT id, email, password_hash FROM users WHERE email = $1",
        login_data.email.lower().strip(),
    )

    if not user_row or not verify_password(user_row["password_hash"], login_data.password):
        await record_login_attempt(conn, login_data.email, client_ip, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # 3. Successful login - record and find user's tenant
    await record_login_attempt(conn, login_data.email, client_ip, success=True)

    member_row = await conn.fetchrow(
        "SELECT tenant_id, role FROM tenant_members WHERE user_id = $1 ORDER BY created_at ASC LIMIT 1",
        user_row["id"],
    )
    if not member_row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any tenant organization.",
        )

    # 4. Create server-side session and CSRF token
    session_id = generate_session_id()
    csrf_token = generate_csrf_token()
    expires_at = calculate_session_expiry(DEFAULT_SESSION_TTL_HOURS)

    await conn.execute(
        """
        INSERT INTO sessions (id, user_id, tenant_id, csrf_token, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        session_id,
        user_row["id"],
        member_row["tenant_id"],
        csrf_token,
        expires_at,
    )

    # 5. Set HttpOnly, SameSite=Lax session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in HTTPS production environments
        samesite="lax",
        max_age=DEFAULT_SESSION_TTL_HOURS * 3600,
    )

    return LoginResponse(
        user_id=user_row["id"],
        email=user_row["email"],
        tenant_id=member_row["tenant_id"],
        csrf_token=csrf_token,
    )


@router.post(
    "/logout",
    summary="Terminate current session",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> None:
    """Invalidate session in database and clear cookie."""
    if session_cookie:
        await conn.execute("DELETE FROM sessions WHERE id = $1", session_cookie)

    response.delete_cookie(key=SESSION_COOKIE_NAME)


@router.get(
    "/me",
    summary="Get current authenticated user info",
    response_model=CurrentUserResponse,
)
async def get_me(
    auth: AuthContext = Depends(get_current_auth),
) -> CurrentUserResponse:
    """Retrieve security context for current authenticated caller."""
    return CurrentUserResponse(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        auth_type=auth.auth_type,
        role=auth.role,
        scopes=auth.scopes,
    )


@router.post(
    "/api-keys",
    summary="Generate a new API key for the tenant",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: CreateApiKeyRequest,
    auth: AuthContext = Depends(get_current_auth),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ApiKeyResponse:
    """Issue a new scoped API key. Returns the plaintext secret exactly once."""
    full_key, prefix, key_hash = generate_api_key()

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=request.expires_in_days)

    row = await conn.fetchrow(
        """
        INSERT INTO api_keys (tenant_id, name, key_prefix, key_hash, scopes, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, name, key_prefix, scopes, expires_at, revoked_at, created_at
        """,
        auth.tenant_id,
        request.name,
        prefix,
        key_hash,
        json.dumps(request.scopes),
        expires_at,
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record generated API key.",
        )

    scopes_val = row["scopes"]
    if isinstance(scopes_val, str):
        scopes = json.loads(scopes_val)
    elif isinstance(scopes_val, list):
        scopes = scopes_val
    else:
        scopes = []

    return ApiKeyResponse(
        id=row["id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        key=full_key,  # Full key returned ONLY ONCE upon creation
        scopes=scopes,
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        created_at=row["created_at"],
    )


@router.post(
    "/api-keys/{key_id}/revoke",
    summary="Revoke an existing API key",
    response_model=RevokeApiKeyResponse,
)
async def revoke_api_key(
    key_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> RevokeApiKeyResponse:
    """Revoke an API key immediately so it can no longer be used."""
    now = datetime.now(UTC)
    res = await conn.execute(
        """
        UPDATE api_keys
        SET revoked_at = $1
        WHERE id = $2 AND tenant_id = $3 AND revoked_at IS NULL
        """,
        now,
        key_id,
        auth.tenant_id,
    )

    if res == "UPDATE 0":
        # Check if already revoked or not found
        row = await conn.fetchrow(
            "SELECT id, revoked_at FROM api_keys WHERE id = $1 AND tenant_id = $2",
            key_id,
            auth.tenant_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key '{key_id}' not found.",
            )
        return RevokeApiKeyResponse(id=row["id"], revoked=True, revoked_at=row["revoked_at"])

    return RevokeApiKeyResponse(id=key_id, revoked=True, revoked_at=now)
