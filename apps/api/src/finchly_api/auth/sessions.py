"""Server-side session generation and CSRF tokens per ADR-009 §1."""

import secrets
from datetime import UTC, datetime, timedelta

SESSION_COOKIE_NAME = "finchly_session"
DEFAULT_SESSION_TTL_HOURS = 24


def generate_session_id() -> str:
    """Generate a 64-character cryptographically secure session ID."""
    return secrets.token_hex(32)


def generate_csrf_token() -> str:
    """Generate a 64-character cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def calculate_session_expiry(ttl_hours: int = DEFAULT_SESSION_TTL_HOURS) -> datetime:
    """Calculate future timestamp for session expiration."""
    return datetime.now(UTC) + timedelta(hours=ttl_hours)
