"""Canonical Document Envelope conforming to ADR-010 §1, §8, §9 and FINCHLY_SPEC §6."""

import hashlib
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField

from finchly_domain.schemas.canonical import SupplierInvoicePayload
from finchly_domain.schemas.evidence import Evidence
from finchly_domain.schemas.primitives import DocumentType
from finchly_domain.schemas.stubs import (
    CreditNotePayload,
    DeliveryChallanPayload,
    ElectricityBillPayload,
    PurchaseOrderPayload,
    UnknownDocumentPayload,
)


class ValidationIssue(BaseModel):
    """Structured validation issue conforming to AGENTS.md §11."""

    model_config = ConfigDict(frozen=True)

    rule_key: str = PydanticField(..., description="Unique deterministic validator rule key.")
    severity: Literal["error", "warning", "info"] = PydanticField(
        ...,
        description="Severity level; error severity blocks approval.",
    )
    field_paths: list[str] = PydanticField(
        default_factory=list,
        description="JSON pointer or dotted field paths related to this issue.",
    )
    expected: str | None = PydanticField(
        default=None,
        description="Expected value or invariant description.",
    )
    observed: str | None = PydanticField(
        default=None,
        description="Observed value or state that triggered the issue.",
    )
    message: str = PydanticField(..., description="Human-readable explanation.")


class ValidationSummary(BaseModel):
    """Validation status and collected issues for a canonical document."""

    model_config = ConfigDict(frozen=True)

    status: Literal["pending", "passed", "failed", "requires_review"] = PydanticField(
        default="pending",
        description="Aggregate validation status.",
    )
    issues: list[ValidationIssue] = PydanticField(
        default_factory=list,
        description="List of structured validation issues produced by deterministic validators.",
    )


DOCUMENT_TYPE_PAYLOAD_MAP: dict[DocumentType, type[BaseModel]] = {
    DocumentType.SUPPLIER_INVOICE: SupplierInvoicePayload,
    DocumentType.CREDIT_NOTE: CreditNotePayload,
    DocumentType.PURCHASE_ORDER: PurchaseOrderPayload,
    DocumentType.DELIVERY_CHALLAN: DeliveryChallanPayload,
    DocumentType.ELECTRICITY_BILL: ElectricityBillPayload,
    DocumentType.UNKNOWN: UnknownDocumentPayload,
}


TypedPayload = (
    SupplierInvoicePayload
    | CreditNotePayload
    | PurchaseOrderPayload
    | DeliveryChallanPayload
    | ElectricityBillPayload
    | UnknownDocumentPayload
)


class CanonicalEnvelope(BaseModel):
    """Top-level immutable versioned envelope for all canonical business documents."""

    model_config = ConfigDict(frozen=True)

    document_id: str = PydanticField(..., description="UUID of the parent document intake record.")
    tenant_id: str = PydanticField(..., description="UUID of the owning tenant.")
    document_type: DocumentType = PydanticField(
        ..., description="Closed document classification type."
    )
    schema_version: str = PydanticField(
        default="1.0.0",
        description="SemVer schema version of this payload.",
    )
    payload: TypedPayload = PydanticField(
        ...,
        description="Strictly-typed domain payload corresponding to document_type.",
    )
    evidence: list[Evidence] = PydanticField(
        default_factory=list,
        description="Document-level and unassigned evidence references.",
    )
    validation: ValidationSummary = PydanticField(
        default_factory=ValidationSummary,
        description="Deterministic validation results for this version.",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_payload_type(cls, data: Any) -> Any:
        """Resolve raw payload dict to specific typed payload model based on document_type."""
        if isinstance(data, dict):
            raw_type = data.get("document_type")
            raw_payload = data.get("payload")
            if raw_type and isinstance(raw_payload, dict):
                try:
                    dt = DocumentType(raw_type)
                except ValueError:
                    dt = DocumentType.UNKNOWN
                payload_cls = DOCUMENT_TYPE_PAYLOAD_MAP.get(dt)
                if payload_cls:
                    data = dict(data)
                    data["payload"] = payload_cls.model_validate(raw_payload)
        return data

    @model_validator(mode="after")
    def validate_payload_matches_document_type(self) -> "CanonicalEnvelope":
        """Verify that payload model instance strictly matches document_type."""
        expected_cls = DOCUMENT_TYPE_PAYLOAD_MAP.get(self.document_type)
        if expected_cls and not isinstance(self.payload, expected_cls):
            raise ValueError(
                f"Payload type mismatch: document_type '{self.document_type.value}' "
                f"requires payload of type {expected_cls.__name__}, but got {type(self.payload).__name__}."
            )
        return self

    def canonical_payload_json_bytes(self) -> bytes:
        """Compute RFC 8785 canonical bytes of the canonical payload.

        Per ADR-010 §8: payload hash = SHA-256 over RFC 8785 (JSON Canonicalization Scheme)
        bytes of the canonical payload.
        """
        payload_data = self.payload.model_dump(mode="json")
        return rfc8785.dumps(payload_data)

    def canonical_envelope_json_bytes(self) -> bytes:
        """Compute RFC 8785 canonical bytes of the full envelope."""
        envelope_data = self.model_dump(mode="json")
        return rfc8785.dumps(envelope_data)

    def rfc8785_hash(self) -> str:
        """Compute SHA-256 hex digest of the canonical RFC 8785 payload bytes per ADR-010 §8."""
        return hashlib.sha256(self.canonical_payload_json_bytes()).hexdigest()
