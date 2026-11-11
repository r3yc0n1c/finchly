"""Login rate limiting and lockout backoff tracking per ADR-009 §1 and SEC-001.

Retention policy (AGENTS.md §16):
Authentication attempt audit records in `login_attempts` serve short-term lockout
enforcement and security event tracing. Records older than 15 minutes have passed
the lockout sliding window, and historical records are retained for 30 days under
security audit log retention before being permanently purged by scheduled maintenance.
"""

import asyncpg

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 15


async def is_account_locked(conn: asyncpg.Connection, email: str) -> bool:
    """Check if an account is locked due to >= 5 failed login attempts in the past 15 minutes.

    Evaluated using database server time to avoid clock drift between application nodes.
    """
    failed_count = await conn.fetchval(
        f"""
        SELECT COUNT(*)
        FROM login_attempts
        WHERE email = $1
          AND success = false
          AND attempted_at >= (now() - INTERVAL '{LOCKOUT_WINDOW_MINUTES} minutes')
        """,
        email.lower().strip(),
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
