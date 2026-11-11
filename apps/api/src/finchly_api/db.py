"""Asynchronous PostgreSQL database connection and pooling for Finchly API."""

import asyncpg

from finchly_api.config import settings

_pool: asyncpg.Pool | None = None


async def init_db_pool() -> asyncpg.Pool:
    """Initialize global asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
            timeout=5.0,
            command_timeout=10.0,
        )
    return _pool


async def close_db_pool() -> None:
    """Close global asyncpg connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_db_pool() -> asyncpg.Pool:
    """Retrieve existing connection pool, initializing if necessary."""
    global _pool
    if _pool is None:
        return await init_db_pool()
    return _pool
