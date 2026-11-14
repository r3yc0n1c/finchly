"""Tenant-scoped database connection dependency enforcing ADR-009 §3 RLS."""

from collections.abc import AsyncGenerator

import asyncpg
from fastapi import Depends

from finchly_api.auth.context import AuthContext
from finchly_api.auth.dependencies import get_current_auth
from finchly_api.db import get_db_pool
from finchly_api.tenancy.context import set_current_tenant_id


async def get_tenant_db(
    auth: AuthContext = Depends(get_current_auth),
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Provide a database connection scoped to the authenticated caller's tenant.

    Sets transaction-local 'app.tenant_id' in PostgreSQL, activating Row-Level Security
    policies on all tenant-owned tables.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Set transaction-local tenant context
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, true);",
            str(auth.tenant_id),
        )
        set_current_tenant_id(auth.tenant_id)
        try:
            yield conn
        finally:
            set_current_tenant_id(None)
