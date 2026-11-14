"""Generated IDOR test suite and worker tenant resolution verification per ADR-009, SEC-003, and FIN-009."""

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import asyncpg
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from finchly_api.auth.dependencies import get_current_auth, get_db_connection
from finchly_api.auth.password import hash_password
from finchly_api.auth.sessions import SESSION_COOKIE_NAME
from finchly_api.main import app
from finchly_api.tenancy import (
    find_unscoped_routes,
    resolve_aggregate_tenant_id,
    verify_routes_are_tenant_scoped,
    worker_tenant_scope,
)

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


def test_all_api_routes_are_strictly_tenant_scoped() -> None:
    """Verify that every protected endpoint in the application route table enforces tenant scoping (SEC-003, FIN-009)."""
    # Will raise AssertionError if any non-public route lacks tenant scoping
    verify_routes_are_tenant_scoped(app)
    unscoped = find_unscoped_routes(app)
    assert unscoped == [], f"Found unscoped routes: {unscoped}"


def test_generated_idor_test_fails_on_deliberately_unscoped_route() -> None:
    """Verify that the generated route test fails when a route lacks tenant scoping (FIN-009 acceptance criteria)."""
    # Create test FastAPI app with compliant routes and one deliberately unscoped route
    test_app = FastAPI()

    # 1. Compliant route
    @test_app.get("/api/v1/protected-data")
    async def protected_endpoint(auth: Any = Depends(get_current_auth)) -> dict[str, str]:
        return {"status": "ok"}

    # 2. Deliberately unscoped route missing authentication / tenant dependency
    @test_app.get("/api/v1/deliberately-unscoped-leak")
    async def unscoped_endpoint() -> dict[str, str]:
        return {"leaked": "data"}

    unscoped = find_unscoped_routes(test_app)
    assert ("GET", "/api/v1/deliberately-unscoped-leak") in unscoped

    with pytest.raises(AssertionError) as exc_info:
        verify_routes_are_tenant_scoped(test_app)

    assert "Tenant scoping violation" in str(exc_info.value)
    assert "/api/v1/deliberately-unscoped-leak" in str(exc_info.value)


@pytest.mark.asyncio
async def test_worker_tenant_resolution_from_aggregate(pg_conn: asyncpg.Connection) -> None:
    """Verify workers resolve tenant from database aggregate and set RLS context (ADR-009 §4, FIN-009)."""
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sha256 = uuid.uuid4().hex

    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2)", tenant_id, "Worker Tenant"
    )
    await pg_conn.execute(
        """
        INSERT INTO documents (id, tenant_id, sha256, object_key, mime_detected, byte_size)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        doc_id,
        tenant_id,
        sha256,
        "tenant/doc.pdf",
        "application/pdf",
        1024,
    )

    # 1. Direct resolution from aggregate
    resolved_tenant = await resolve_aggregate_tenant_id(pg_conn, "document", doc_id)
    assert resolved_tenant == tenant_id

    # 2. Resolution for unknown aggregate fails
    with pytest.raises(ValueError, match="not found in database"):
        await resolve_aggregate_tenant_id(pg_conn, "document", uuid.uuid4())

    # 3. Context manager establishes transaction-scoped RLS setting
    async with worker_tenant_scope(pg_conn, "document", doc_id) as scoped_tenant:
        assert scoped_tenant == tenant_id
        current_setting = await pg_conn.fetchval("SELECT current_setting('app.tenant_id', true);")
        assert current_setting == str(tenant_id)


@pytest.mark.asyncio
async def test_cross_tenant_idor_rejection(pg_conn: asyncpg.Connection, override_db: None) -> None:
    """Verify that Tenant B cannot access or revoke an API key belonging to Tenant A (IDOR protection)."""
    # Tenant A
    tenant_a_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    email_a = f"tenant_a_{uuid.uuid4().hex[:6]}@example.com"

    # Tenant B
    tenant_b_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    email_b = f"tenant_b_{uuid.uuid4().hex[:6]}@example.com"

    pw = "CommonPassword123!"
    pw_hash = hash_password(pw)

    await pg_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2), ($3, $4)",
        tenant_a_id,
        "A",
        tenant_b_id,
        "B",
    )
    await pg_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3), ($4, $5, $6)",
        user_a_id,
        email_a,
        pw_hash,
        user_b_id,
        email_b,
        pw_hash,
    )
    await pg_conn.execute(
        "INSERT INTO tenant_members (tenant_id, user_id, role) VALUES ($1, $2, $3), ($4, $5, $6)",
        tenant_a_id,
        user_a_id,
        "tenant_admin",
        tenant_b_id,
        user_b_id,
        "tenant_admin",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Tenant A logs in and creates an API key
        login_a = await client.post("/api/v1/auth/login", json={"email": email_a, "password": pw})
        session_a = login_a.cookies[SESSION_COOKIE_NAME]
        csrf_a = login_a.json()["csrf_token"]

        client.cookies.set(SESSION_COOKIE_NAME, session_a)
        key_a_resp = await client.post(
            "/api/v1/auth/api-keys",
            headers={"X-CSRF-Token": csrf_a},
            json={"name": "key-a", "scopes": ["documents:read"]},
        )
        assert key_a_resp.status_code == 201
        key_a_id = key_a_resp.json()["id"]

        # Tenant B logs in
        client.cookies.clear()
        login_b = await client.post("/api/v1/auth/login", json={"email": email_b, "password": pw})
        session_b = login_b.cookies[SESSION_COOKIE_NAME]
        csrf_b = login_b.json()["csrf_token"]

        # Tenant B attempts IDOR attack: revoke Tenant A's API key
        client.cookies.set(SESSION_COOKIE_NAME, session_b)
        idor_resp = await client.post(
            f"/api/v1/auth/api-keys/{key_a_id}/revoke",
            headers={"X-CSRF-Token": csrf_b},
        )
        # Must be rejected (404 Not Found within Tenant B's boundary)
        assert idor_resp.status_code == 404
        assert "not found" in idor_resp.json()["detail"].lower()
