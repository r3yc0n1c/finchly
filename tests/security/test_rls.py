"""Security tests for PostgreSQL Row-Level Security (RLS) and tenancy isolation per ADR-009, SEC-002, and FIN-007."""

import os
import uuid

import asyncpg
import pytest

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "finchly")
DB_PASS = os.environ.get("DB_PASSWORD", "finchly_dev")
DB_NAME = os.environ.get("DB_NAME", "finchly")


@pytest.fixture
async def pg_admin_conn() -> asyncpg.Connection:
    """Connection using standard administrative/migration user."""
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            timeout=3,
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    yield conn
    await conn.close()


@pytest.fixture
async def pg_app_conn() -> asyncpg.Connection:
    """Connection using non-bypass application role finchly_app."""
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user="finchly_app",
            password="finchly_app_dev",
            database=DB_NAME,
            timeout=3,
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL app connection not reachable: {exc}")
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_disposable_db_migration_cycle(pg_admin_conn: asyncpg.Connection) -> None:
    """Verify that baseline migrations apply forward and rollback cleanly on a disposable database (FIN-007)."""
    disposable_db_name = f"finchly_disposable_{uuid.uuid4().hex[:8]}"

    # 1. Create disposable database
    await pg_admin_conn.execute(f'CREATE DATABASE "{disposable_db_name}" OWNER "{DB_USER}";')

    disposable_db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{disposable_db_name}"

    try:
        # 2. Run alembic upgrade head using subprocess
        import subprocess

        env = os.environ.copy()
        env["DATABASE_URL"] = disposable_db_url
        upgrade_res = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert upgrade_res.returncode == 0, f"Upgrade failed: {upgrade_res.stderr}"

        # 3. Verify tables created in disposable db
        disp_conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=disposable_db_name,
        )
        tables = await disp_conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
        )
        table_names = {row["tablename"] for row in tables}
        expected = {"tenants", "users", "tenant_members", "api_keys", "documents", "sessions"}
        assert expected.issubset(table_names), f"Missing tables in {table_names}"
        await disp_conn.close()

        # 4. Run alembic downgrade base
        downgrade_res = subprocess.run(
            ["uv", "run", "alembic", "downgrade", "base"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert downgrade_res.returncode == 0, f"Downgrade failed: {downgrade_res.stderr}"

    finally:
        # 5. Clean up disposable database
        await pg_admin_conn.execute(
            f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{disposable_db_name}' AND pid <> pg_backend_pid();
            """
        )
        await pg_admin_conn.execute(f'DROP DATABASE IF EXISTS "{disposable_db_name}";')


@pytest.mark.asyncio
async def test_rls_returns_zero_rows_without_tenant_context(
    pg_admin_conn: asyncpg.Connection,
    pg_app_conn: asyncpg.Connection,
) -> None:
    """Verify that a query under the application role with no tenant context returns zero rows (SEC-002, FIN-007)."""
    # 1. Seed two distinct tenants and records using admin connection
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    user_id = uuid.uuid4()

    await pg_admin_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2), ($3, $4);",
        tenant_a_id,
        "Tenant Alpha",
        tenant_b_id,
        "Tenant Beta",
    )
    await pg_admin_conn.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3);",
        user_id,
        f"testuser_{uuid.uuid4().hex[:6]}@example.com",
        "argon2id$mocked",
    )
    await pg_admin_conn.execute(
        "INSERT INTO documents (tenant_id, sha256, object_key, mime_detected, byte_size) VALUES ($1, $2, $3, $4, $5);",
        tenant_a_id,
        uuid.uuid4().hex,
        "tenant/a/doc1.pdf",
        "application/pdf",
        1024,
    )
    await pg_admin_conn.execute(
        "INSERT INTO documents (tenant_id, sha256, object_key, mime_detected, byte_size) VALUES ($1, $2, $3, $4, $5);",
        tenant_b_id,
        uuid.uuid4().hex,
        "tenant/b/doc2.pdf",
        "application/pdf",
        2048,
    )

    # 2. Query as finchly_app WITHOUT setting app.tenant_id
    # Every tenant-owned table MUST return 0 rows
    docs = await pg_app_conn.fetch("SELECT * FROM documents;")
    assert len(docs) == 0, f"Expected 0 rows without tenant context, got {len(docs)}"

    members = await pg_app_conn.fetch("SELECT * FROM tenant_members;")
    assert len(members) == 0

    api_keys = await pg_app_conn.fetch("SELECT * FROM api_keys;")
    assert len(api_keys) == 0

    sessions = await pg_app_conn.fetch("SELECT * FROM sessions;")
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_rls_tenant_isolation_with_context(
    pg_admin_conn: asyncpg.Connection,
    pg_app_conn: asyncpg.Connection,
) -> None:
    """Verify that setting app.tenant_id makes only the designated tenant's rows visible."""
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    doc_a_sha = uuid.uuid4().hex
    doc_b_sha = uuid.uuid4().hex

    await pg_admin_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2), ($3, $4);",
        tenant_a_id,
        "Isolation Alpha",
        tenant_b_id,
        "Isolation Beta",
    )
    await pg_admin_conn.execute(
        "INSERT INTO documents (tenant_id, sha256, object_key, mime_detected, byte_size) VALUES ($1, $2, $3, $4, $5);",
        tenant_a_id,
        doc_a_sha,
        "tenant/a/doc.pdf",
        "application/pdf",
        512,
    )
    await pg_admin_conn.execute(
        "INSERT INTO documents (tenant_id, sha256, object_key, mime_detected, byte_size) VALUES ($1, $2, $3, $4, $5);",
        tenant_b_id,
        doc_b_sha,
        "tenant/b/doc.pdf",
        "application/pdf",
        512,
    )

    # In transaction with tenant A context
    async with pg_app_conn.transaction():
        await pg_app_conn.execute("SELECT set_config('app.tenant_id', $1, true);", str(tenant_a_id))
        docs_a = await pg_app_conn.fetch("SELECT * FROM documents;")
        assert len(docs_a) == 1
        assert docs_a[0]["sha256"] == doc_a_sha
        assert docs_a[0]["tenant_id"] == tenant_a_id

    # In transaction with tenant B context
    async with pg_app_conn.transaction():
        await pg_app_conn.execute("SELECT set_config('app.tenant_id', $1, true);", str(tenant_b_id))
        docs_b = await pg_app_conn.fetch("SELECT * FROM documents;")
        assert len(docs_b) == 1
        assert docs_b[0]["sha256"] == doc_b_sha
        assert docs_b[0]["tenant_id"] == tenant_b_id


@pytest.mark.asyncio
async def test_rls_cross_tenant_insert_blocked(
    pg_admin_conn: asyncpg.Connection,
    pg_app_conn: asyncpg.Connection,
) -> None:
    """Verify that an application connection with Tenant A context cannot write Tenant B data."""
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    await pg_admin_conn.execute(
        "INSERT INTO tenants (id, name) VALUES ($1, $2), ($3, $4);",
        tenant_a_id,
        "Insert Alpha",
        tenant_b_id,
        "Insert Beta",
    )

    async with pg_app_conn.transaction():
        # Set context to Tenant A
        await pg_app_conn.execute("SELECT set_config('app.tenant_id', $1, true);", str(tenant_a_id))

        # Attempt to insert a document for Tenant B -> must violate RLS policy
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await pg_app_conn.execute(
                "INSERT INTO documents (tenant_id, sha256, object_key, mime_detected, byte_size) VALUES ($1, $2, $3, $4, $5);",
                tenant_b_id,
                uuid.uuid4().hex,
                "malicious/cross_tenant.pdf",
                "application/pdf",
                128,
            )
