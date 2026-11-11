"""Security tests for authentication, sessions, CSRF, and API keys per ADR-009, SEC-001, and FIN-008."""

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from finchly_api.auth.api_keys import hash_api_key_secret, parse_api_key
from finchly_api.auth.dependencies import get_db_connection
from finchly_api.auth.password import hash_password, verify_password
from finchly_api.auth.sessions import SESSION_COOKIE_NAME
from finchly_api.main import app

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "finchly")
DB_PASS = os.environ.get("DB_PASSWORD", "finchly_dev")
DB_NAME = os.environ.get("DB_NAME", "finchly")


@pytest.fixture
async def pg_conn() -> asyncpg.Connection:
    """Connection fixture for test setup and tear down."""
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            timeout=3,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    yield conn
    await conn.close()


@pytest.fixture
def override_db(pg_conn: asyncpg.Connection) -> Generator[None, None, None]:
    """Override database dependency to use test connection."""

    async def _get_test_db() -> AsyncGenerator[asyncpg.Connection, None]:
        yield pg_conn

    app.dependency_overrides[get_db_connection] = _get_test_db
    yield
    app.dependency_overrides.pop(get_db_connection, None)


def test_argon2id_password_hashing() -> None:
    """Verify password hashing generates valid Argon2id hashes and verifies correctly (SEC-001)."""
    password = "SuperSecretPassword123!"
    pw_hash = hash_password(password)

    # Must be valid Argon2id hash format
    assert pw_hash.startswith("$argon2id$")
    assert verify_password(pw_hash, password) is True
    assert verify_password(pw_hash, "WrongPassword") is False
    assert verify_password("invalid$hash$string", password) is False


@pytest.mark.asyncio
async def test_login_successful_sets_cookie_and_returns_csrf(
    pg_conn: asyncpg.Connection, override_db: None
) -> None:
    """Verify successful login returns CSRF token and sets HttpOnly session cookie (SEC-001, FIN-008)."""
    # 1. Setup tenant and user
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    password = "CorrectPassword123!"

    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "Test Tenant"
    )
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
        user_id,
        email,
        hash_password(password),
    )
    await pg_conn.execute(
        "INSERT INTO tenant_members (tenant_id, user_id, role) VALUES ($1, $2, $3)",
        tenant_id,
        user_id,
        "reviewer",
    )

    # 2. Perform login
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == str(user_id)
        assert data["email"] == email
        assert data["tenant_id"] == str(tenant_id)
        assert len(data["csrf_token"]) == 64

        # Verify HttpOnly session cookie is present
        assert SESSION_COOKIE_NAME in resp.cookies
        session_id = resp.cookies[SESSION_COOKIE_NAME]
        assert len(session_id) == 64

        # Verify session is persisted in DB
        session_row = await pg_conn.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
        assert session_row is not None
        assert session_row["user_id"] == user_id
        assert session_row["tenant_id"] == tenant_id
        assert session_row["csrf_token"] == data["csrf_token"]


@pytest.mark.asyncio
async def test_wrong_password_lockout(pg_conn: asyncpg.Connection, override_db: None) -> None:
    """Verify 5 failed login attempts trigger lockout for 15 minutes (SEC-001, FIN-008)."""
    email = f"lockout_{uuid.uuid4().hex[:6]}@example.com"
    password = "CorrectPassword123!"

    user_id = uuid.uuid4()
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
        user_id,
        email,
        hash_password(password),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First 4 attempts return 401
        for _ in range(4):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "WrongPassword"},
            )
            assert resp.status_code == 401

        # 5th attempt returns 401 and records 5th failure
        resp_5 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword"},
        )
        assert resp_5.status_code == 401

        # 6th attempt is blocked by rate limiting/lockout -> 429
        resp_6 = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword"},
        )
        assert resp_6.status_code == 429
        assert "temporarily locked" in resp_6.json()["detail"]

        # Even with the correct password, login is blocked during lockout
        resp_correct = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp_correct.status_code == 429


@pytest.mark.asyncio
async def test_csrf_rejection_and_acceptance(
    pg_conn: asyncpg.Connection, override_db: None
) -> None:
    """Verify state-changing requests reject missing/invalid CSRF tokens and accept valid ones (SEC-001, FIN-008)."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = f"csrf_{uuid.uuid4().hex[:6]}@example.com"
    password = "Password123!"

    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "CSRF Tenant"
    )
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
        user_id,
        email,
        hash_password(password),
    )
    await pg_conn.execute(
        "INSERT INTO tenant_members (tenant_id, user_id, role) VALUES ($1, $2, $3)",
        tenant_id,
        user_id,
        "tenant_admin",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        csrf_token = login_resp.json()["csrf_token"]
        session_id = login_resp.cookies[SESSION_COOKIE_NAME]

        # 1. State-changing POST without CSRF header -> 403 Forbidden
        client.cookies.set(SESSION_COOKIE_NAME, session_id)
        post_no_csrf = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "test-key", "scopes": ["documents:read"]},
        )
        assert post_no_csrf.status_code == 403
        assert "CSRF validation failed" in post_no_csrf.json()["detail"]

        # 2. State-changing POST with invalid CSRF token -> 403 Forbidden
        post_bad_csrf = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-CSRF-Token": "invalid_token_12345"},
            json={"name": "test-key", "scopes": ["documents:read"]},
        )
        assert post_bad_csrf.status_code == 403

        # 3. State-changing POST with matching CSRF token -> 201 Created
        post_good_csrf = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-CSRF-Token": csrf_token},
            json={"name": "valid-key", "scopes": ["documents:read"]},
        )
        assert post_good_csrf.status_code == 201
        assert post_good_csrf.json()["name"] == "valid-key"


@pytest.mark.asyncio
async def test_api_key_no_plaintext_secret_stored(
    pg_conn: asyncpg.Connection, override_db: None
) -> None:
    """Verify that only the hash of the API key secret is stored in PostgreSQL (SEC-001, FIN-008)."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = f"keyuser_{uuid.uuid4().hex[:6]}@example.com"
    password = "Password123!"

    await pg_conn.execute("INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "Key Tenant")
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
        user_id,
        email,
        hash_password(password),
    )
    await pg_conn.execute(
        "INSERT INTO tenant_members (tenant_id, user_id, role) VALUES ($1, $2, $3)",
        tenant_id,
        user_id,
        "tenant_admin",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        csrf_token = login_resp.json()["csrf_token"]
        session_id = login_resp.cookies[SESSION_COOKIE_NAME]

        # Create API key
        client.cookies.set(SESSION_COOKIE_NAME, session_id)
        key_resp = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-CSRF-Token": csrf_token},
            json={"name": "integration-key", "scopes": ["documents:read"]},
        )
        assert key_resp.status_code == 201
        data = key_resp.json()
        full_key = data["key"]
        prefix, secret = parse_api_key(full_key)

        # Inspect database record
        db_row = await pg_conn.fetchrow(
            "SELECT * FROM api_keys WHERE id = $1", uuid.UUID(data["id"])
        )
        assert db_row is not None
        assert db_row["key_prefix"] == prefix

        # Database stores only hash of secret
        expected_hash = hash_api_key_secret(secret)
        assert db_row["key_hash"] == expected_hash

        # Assert full key and secret are NEVER in DB
        assert full_key not in str(dict(db_row))
        assert secret not in str(dict(db_row))


@pytest.mark.asyncio
async def test_api_key_scope_and_revocation(pg_conn: asyncpg.Connection, override_db: None) -> None:
    """Verify API key scope enforcement and revocation (SEC-001, FIN-008)."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    email = f"scope_{uuid.uuid4().hex[:6]}@example.com"
    password = "Password123!"

    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "Scope Tenant"
    )
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
        user_id,
        email,
        hash_password(password),
    )
    await pg_conn.execute(
        "INSERT INTO tenant_members (tenant_id, user_id, role) VALUES ($1, $2, $3)",
        tenant_id,
        user_id,
        "tenant_admin",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login and generate key with restricted scope
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        csrf_token = login_resp.json()["csrf_token"]
        session_id = login_resp.cookies[SESSION_COOKIE_NAME]

        client.cookies.set(SESSION_COOKIE_NAME, session_id)
        create_key_resp = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-CSRF-Token": csrf_token},
            json={"name": "scoped-key", "scopes": ["documents:read"]},
        )
        key_data = create_key_resp.json()
        api_key = key_data["key"]
        key_id = key_data["id"]

        # Authenticate with API key on /api/v1/auth/me
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["auth_type"] == "api_key"
        assert me_resp.json()["scopes"] == ["documents:read"]

        # Restricted API key cannot manage (create or revoke) API keys -> 403 Forbidden
        attempt_create = await client.post(
            "/api/v1/auth/api-keys",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": "escalation-key", "scopes": ["*"]},
        )
        assert attempt_create.status_code == 403
        assert "INSUFFICIENT_SCOPE" in attempt_create.json()["detail"]

        attempt_revoke = await client.post(
            f"/api/v1/auth/api-keys/{key_id}/revoke",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert attempt_revoke.status_code == 403
        assert "INSUFFICIENT_SCOPE" in attempt_revoke.json()["detail"]

        # Revocation by authorized tenant_admin session succeeds
        revoke_resp = await client.post(
            f"/api/v1/auth/api-keys/{key_id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["revoked"] is True

        # Using revoked API key is rejected
        me_revoked_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert me_revoked_resp.status_code == 401
        assert "revoked" in me_revoked_resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_key_expiry(pg_conn: asyncpg.Connection, override_db: None) -> None:
    """Verify expired API keys are rejected with 401 Unauthorized (SEC-001)."""
    tenant_id = uuid.uuid4()
    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "Expiry Tenant"
    )

    from finchly_api.auth.api_keys import generate_api_key

    full_key, prefix, key_hash = generate_api_key()
    past_expiry = datetime.now(UTC) - timedelta(hours=1)

    await pg_conn.execute(
        """
        INSERT INTO api_keys (tenant_id, name, key_prefix, key_hash, scopes, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        tenant_id,
        "expired-key",
        prefix,
        key_hash,
        '["*"]',
        past_expiry,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {full_key}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"]
