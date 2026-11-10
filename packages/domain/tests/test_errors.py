"""Tests for domain error catalogue."""

from finchly_domain.errors import ErrorCode, get_error_detail


def test_all_spec_error_codes_present() -> None:
    """Verify that all error codes specified in Finchly Spec §13 exist."""
    required_codes = {
        "UPLOAD_TOO_LARGE",
        "UNSUPPORTED_FILE",
        "DUPLICATE_DOCUMENT",
        "EXTRACTION_INVALID",
        "EVIDENCE_NOT_FOUND",
        "VALIDATION_FAILED",
        "REVIEW_REQUIRED",
        "APPROVAL_STALE",
        "ERP_CONNECTION_FAILED",
        "ERP_OUTCOME_UNKNOWN",
        "POSTING_DUPLICATE",
        "MAPPING_MISSING",
        "TENANT_ACCESS_DENIED",
    }
    actual_codes = {code.value for code in ErrorCode}
    missing = required_codes - actual_codes
    assert not missing, f"Missing error codes from Finchly Spec §13: {missing}"


def test_catalogue_contains_details_for_all_codes() -> None:
    """Verify that every ErrorCode has a complete ErrorDetail entry."""
    for code in ErrorCode:
        detail = get_error_detail(code)
        assert detail.code == code
        assert 400 <= detail.http_status <= 599
        assert len(detail.message) > 0
        assert len(detail.category) > 0
        assert len(detail.recovery_suggestion) > 0
