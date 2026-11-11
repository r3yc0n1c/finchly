"""Login rate limiting and lockout backoff tracking per ADR-009 §1 and SEC-001."""

from datetime import UTC, datetime, timedelta

import asyncpg

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 15


async def is_account_locked(conn: asyncpg.Connection, email: str) -> bool:
    """Check if an account is locked due to >= 5 failed login attempts in the past 15 minutes."""
    cutoff = datetime.now(UTC) - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
    failed_count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM login_attempts
        WHERE email = $1
          AND success = false
          AND attempted_at >= $2
        """,
        email.lower().strip(),
        cutoff,
    )
    return (failed_count or 0) >= MAX_FAILED_LOGIN_ATTEMPTS


async def record_login_attempt(
    conn: asyncpg.Connection,
    email: str,
    ip_address: str,
    success: bool,
) -> None:
    """Record an authentication attempt in the login_attempts table."""
    await conn.execute(
        """
        INSERT INTO login_attempts (email, ip_address, success)
        VALUES ($1, $2, $3)
        """,
        email.lower().strip(),
        ip_address,
        success,
    )
