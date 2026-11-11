"""Finchly domain package.

Pure domain definitions, canonical schemas, lifecycle, and validation interfaces.
Zero framework dependencies (enforced by import-linter).
"""

from finchly_domain.errors import ErrorCode, ErrorDetail, get_error_detail

__all__ = ["ErrorCode", "ErrorDetail", "get_error_detail"]
