"""Finchly error code catalogue.

Defines all standard domain and API error codes specified in Finchly Spec §13
and AGENTS.md §8. Pure domain models with no framework dependencies.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable domain error codes for Finchly."""

    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
    EXTRACTION_INVALID = "EXTRACTION_INVALID"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    ERP_CONNECTION_FAILED = "ERP_CONNECTION_FAILED"
    ERP_OUTCOME_UNKNOWN = "ERP_OUTCOME_UNKNOWN"
    POSTING_DUPLICATE = "POSTING_DUPLICATE"
    MAPPING_MISSING = "MAPPING_MISSING"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"


@dataclass(frozen=True)
class ErrorDetail:
    """Metadata describing a cataloged error."""

    code: ErrorCode
    http_status: int
    category: str
    message: str
    retryable: bool
    recovery_suggestion: str


ERROR_CATALOGUE: Mapping[ErrorCode, ErrorDetail] = {
    ErrorCode.UPLOAD_TOO_LARGE: ErrorDetail(
        code=ErrorCode.UPLOAD_TOO_LARGE,
        http_status=413,
        category="ingestion",
        message="The uploaded document exceeds the maximum permitted payload size.",
        retryable=False,
        recovery_suggestion="Compress the file or reduce the page resolution before re-uploading.",
    ),
    ErrorCode.UNSUPPORTED_FILE: ErrorDetail(
        code=ErrorCode.UNSUPPORTED_FILE,
        http_status=415,
        category="ingestion",
        message="The file format or magic bytes are not supported.",
        retryable=False,
        recovery_suggestion="Provide a valid PDF, JPEG, or PNG document.",
    ),
    ErrorCode.ENCRYPTED_PDF: ErrorDetail(
        code=ErrorCode.ENCRYPTED_PDF,
        http_status=422,
        category="ingestion",
        message="The PDF file is encrypted or password-protected.",
        retryable=False,
        recovery_suggestion="Decrypt or remove the password protection from the document before uploading.",
    ),
    ErrorCode.DUPLICATE_DOCUMENT: ErrorDetail(
        code=ErrorCode.DUPLICATE_DOCUMENT,
        http_status=409,
        category="ingestion",
        message="A document with identical content hash already exists for this tenant.",
        retryable=False,
        recovery_suggestion="Refer to the existing document record or upload a different file.",
    ),
    ErrorCode.EXTRACTION_INVALID: ErrorDetail(
        code=ErrorCode.EXTRACTION_INVALID,
        http_status=422,
        category="extraction",
        message="Model extraction output is malformed, truncated, or schema-invalid.",
        retryable=True,
        recovery_suggestion="Reprocess the document with adjusted parameters or route to manual review.",
    ),
    ErrorCode.EVIDENCE_NOT_FOUND: ErrorDetail(
        code=ErrorCode.EVIDENCE_NOT_FOUND,
        http_status=422,
        category="provenance",
        message="Cited evidence reference could not be resolved to a persisted layout block.",
        retryable=False,
        recovery_suggestion="Re-run layout analysis or correct the evidence bounding box manually.",
    ),
    ErrorCode.VALIDATION_FAILED: ErrorDetail(
        code=ErrorCode.VALIDATION_FAILED,
        http_status=422,
        category="validation",
        message="Deterministic validation rules discovered fatal inconsistencies or calculation mismatches.",
        retryable=False,
        recovery_suggestion="Review highlighted field discrepancies and submit corrections.",
    ),
    ErrorCode.REVIEW_REQUIRED: ErrorDetail(
        code=ErrorCode.REVIEW_REQUIRED,
        http_status=422,
        category="review",
        message="Document requires human verification due to uncertainty or compliance policy.",
        retryable=False,
        recovery_suggestion="Assign document to an authorized reviewer in the review console.",
    ),
    ErrorCode.APPROVAL_STALE: ErrorDetail(
        code=ErrorCode.APPROVAL_STALE,
        http_status=409,
        category="approval",
        message="Document version, payload hash, or mapping version changed after approval was granted.",
        retryable=False,
        recovery_suggestion="Re-validate the updated document and submit a new approval.",
    ),
    ErrorCode.ERP_CONNECTION_FAILED: ErrorDetail(
        code=ErrorCode.ERP_CONNECTION_FAILED,
        http_status=502,
        category="erp",
        message="Failed to establish a network connection or authenticate with the configured ERP system.",
        retryable=True,
        recovery_suggestion="Verify ERP endpoint connectivity, credentials, and allowlist configuration.",
    ),
    ErrorCode.ERP_OUTCOME_UNKNOWN: ErrorDetail(
        code=ErrorCode.ERP_OUTCOME_UNKNOWN,
        http_status=504,
        category="erp",
        message="ERP posting transaction timed out or was severed before an outcome was confirmed.",
        retryable=False,
        recovery_suggestion="Execute ERP readback reconciliation by reference before attempting retry.",
    ),
    ErrorCode.POSTING_DUPLICATE: ErrorDetail(
        code=ErrorCode.POSTING_DUPLICATE,
        http_status=409,
        category="erp",
        message="This document version has already been successfully posted to the ERP.",
        retryable=False,
        recovery_suggestion="Inspect the existing ERP transaction record or reconcile status.",
    ),
    ErrorCode.MAPPING_MISSING: ErrorDetail(
        code=ErrorCode.MAPPING_MISSING,
        http_status=422,
        category="erp",
        message="Required ERP field mapping is absent or incomplete for the target document type.",
        retryable=False,
        recovery_suggestion="Configure required field mappings in the ERP settings console.",
    ),
    ErrorCode.TENANT_ACCESS_DENIED: ErrorDetail(
        code=ErrorCode.TENANT_ACCESS_DENIED,
        http_status=403,
        category="security",
        message="Access to the requested object or action is denied by tenant boundary isolation.",
        retryable=False,
        recovery_suggestion="Authenticate with credentials belonging to the target tenant.",
    ),
}


def get_error_detail(code: ErrorCode) -> ErrorDetail:
    """Retrieve the error detail descriptor for a code."""
    return ERROR_CATALOGUE[code]
