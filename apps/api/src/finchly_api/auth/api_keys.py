"""Programmatic API key generation, parsing, and SHA-256 secret hashing per ADR-009 §2 and SEC-001."""

import hashlib
import secrets


def hash_api_key_secret(secret: str) -> str:
    """Hash the secret portion of an API key using SHA-256."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a high-entropy API key.

    Returns:
        tuple of (full_plaintext_key, key_prefix, key_hash)
        Only key_hash and key_prefix should ever be stored in the database.
    """
    prefix = secrets.token_hex(4)  # 8 hex chars
    secret = secrets.token_urlsafe(32)  # High entropy secret (43+ urlsafe chars)
    full_key = f"fin_{prefix}_{secret}"
    key_hash = hash_api_key_secret(secret)
    return full_key, prefix, key_hash


def parse_api_key(key_str: str) -> tuple[str, str]:
    """Parse an API key string of the format 'fin_<prefix>_<secret>'.

    Returns:
        tuple of (key_prefix, secret)
    Raises:
        ValueError: If key does not match required format.
    """
    parts = key_str.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != "fin":
        raise ValueError("Invalid API key format. Expected 'fin_<prefix>_<secret>'.")
    return parts[1], parts[2]
