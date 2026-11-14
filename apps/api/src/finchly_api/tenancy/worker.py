"""Worker tenant resolution and transaction-scoping helper per ADR-009 §4."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg

from finchly_api.tenancy.context import set_current_tenant_id

AGGREGATE_TABLE_MAP = {
    "document": ("documents", "id", "tenant_id"),
    "processing_run": ("processing_runs", "id", "tenant_id"),
    "validation_run": ("validation_runs", "id", "tenant_id"),
    "approval": ("approvals", "id", "tenant_id"),
}


async def resolve_aggregate_tenant_id(
    conn: asyncpg.Connection,
    aggregate_type: str,
    aggregate_id: UUID,
) -> UUID:
    """Resolve tenant ID from the referenced database aggregate row.

    Per ADR-009 §4, background workers never trust tenant IDs from message content.
    Instead, they resolve tenant context from the persisted database aggregate.
    """
    mapping = AGGREGATE_TABLE_MAP.get(aggregate_type.lower())
    if not mapping:
        raise ValueError(
            f"Unsupported aggregate type '{aggregate_type}'. Known types: {list(AGGREGATE_TABLE_MAP.keys())}"
        )

    table_name, id_col, tenant_col = mapping
    row = await conn.fetchrow(
        f"SELECT {tenant_col} FROM {table_name} WHERE {id_col} = $1",  # noqa: S608
        aggregate_id,
    )
    if not row:
        raise ValueError(
            f"Aggregate '{aggregate_type}' with ID '{aggregate_id}' not found in database."
        )

    tenant_id: UUID = row[tenant_col]
    return tenant_id


@asynccontextmanager
async def worker_tenant_scope(
    conn: asyncpg.Connection,
    aggregate_type: str,
    aggregate_id: UUID,
) -> AsyncGenerator[UUID, None]:
    """Resolve tenant from aggregate and establish transaction-scoped PostgreSQL RLS context."""
    tenant_id = await resolve_aggregate_tenant_id(conn, aggregate_type, aggregate_id)

    async with conn.transaction():
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, true);",
            str(tenant_id),
        )
        set_current_tenant_id(tenant_id)
        try:
            yield tenant_id
        finally:
            set_current_tenant_id(None)
            await conn.execute("SELECT set_config('app.tenant_id', '', true);")
