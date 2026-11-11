"""Unit tests for schema versioning, upcasters, and golden payload compatibility per ADR-010 §7 and FIN-006."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from finchly_domain.schemas import (
    CanonicalEnvelope,
    DocumentType,
    Field,
    SupplierInvoicePayload,
)
from finchly_domain.versioning import (
    SchemaVersion,
    UpcasterRegistry,
)

GOLDEN_PAYLOADS_DIR = Path(__file__).resolve().parents[3] / "tests" / "golden" / "payloads"


def test_schema_version_parsing_and_str() -> None:
    """Verify SemVer strings parse accurately and format to string."""
    v = SchemaVersion("1.0.0")
    assert v.major == 1
    assert v.minor == 0
    assert v.patch == 0
    assert str(v) == "1.0.0"
    assert v.version_string == "1.0.0"
    assert repr(v) == "SchemaVersion('1.0.0')"

    v2 = SchemaVersion("2.14.3")
    assert (v2.major, v2.minor, v2.patch) == (2, 14, 3)
    assert str(v2) == "2.14.3"


def test_schema_version_invalid_strings_rejected() -> None:
    """Verify invalid SemVer formats raise ValueError."""
    invalid_versions = ["", "1", "1.0", "v1.0.0", "1.0.0-beta", "1.0.0+20130313144700", "a.b.c"]
    for inv in invalid_versions:
        with pytest.raises(ValueError, match="Invalid SemVer schema version"):
            SchemaVersion(inv)


def test_schema_version_ordering_and_equality() -> None:
    """Verify comparison operators and equality for SchemaVersion."""
    v100 = SchemaVersion("1.0.0")
    v101 = SchemaVersion("1.0.1")
    v110 = SchemaVersion("1.1.0")
    v200 = SchemaVersion("2.0.0")

    assert v100 < v101 < v110 < v200
    assert v200 > v110 > v101 > v100
    assert v100 == SchemaVersion("1.0.0")
    assert v100 == "1.0.0"
    assert v100 != "2.0.0"
    assert v100 != 100
    assert hash(v100) == hash(SchemaVersion("1.0.0"))


def test_schema_version_breaking_change_check() -> None:
    """Verify is_breaking_relative_to correctly identifies major version bumps."""
    v1 = SchemaVersion("1.0.0")
    v1_minor = SchemaVersion("1.1.0")
    v2 = SchemaVersion("2.0.0")

    assert not v1.is_breaking_relative_to(v1_minor)
    assert v1.is_breaking_relative_to(v2)
    assert not v2.is_breaking_relative_to(v1)


def test_upcaster_registry_registration_validation() -> None:
    """Verify UpcasterRegistry rejects invalid transitions."""
    registry = UpcasterRegistry()

    # Target must be strictly greater than source
    with pytest.raises(ValueError, match="must be strictly greater"):
        registry.register("supplier_invoice", "1.1.0", "1.0.0", lambda d: d)

    with pytest.raises(ValueError, match="must be strictly greater"):
        registry.register("supplier_invoice", "1.0.0", "1.0.0", lambda d: d)


def test_upcaster_registry_chained_transformations() -> None:
    """Verify UpcasterRegistry can apply multi-step chained upcasters via BFS."""
    registry = UpcasterRegistry()

    def upcast_10_to_11(data: dict[str, Any]) -> dict[str, Any]:
        data["step_1"] = True
        return data

    def upcast_11_to_12(data: dict[str, Any]) -> dict[str, Any]:
        data["step_2"] = True
        return data

    registry.register("supplier_invoice", "1.0.0", "1.1.0", upcast_10_to_11)
    registry.register("supplier_invoice", "1.1.0", "1.2.0", upcast_11_to_12)

    initial = {"original": "value"}
    result = registry.upcast("supplier_invoice", initial, "1.0.0", "1.2.0")

    assert result["original"] == "value"
    assert result["step_1"] is True
    assert result["step_2"] is True

    # Same version returns deepcopy
    same = registry.upcast("supplier_invoice", initial, "1.0.0", "1.0.0")
    assert same == initial
    assert same is not initial

    # Downcast is forbidden
    with pytest.raises(ValueError, match="Cannot downcast"):
        registry.upcast("supplier_invoice", result, "1.2.0", "1.0.0")

    # Missing path raises ValueError
    with pytest.raises(ValueError, match="No registered upcaster path found"):
        registry.upcast("supplier_invoice", initial, "1.0.0", "2.0.0")


def test_golden_v1_0_0_loads_and_validates() -> None:
    """Verify golden v1.0.0 payload loads into CanonicalEnvelope and validates strictly."""
    payload_file = GOLDEN_PAYLOADS_DIR / "supplier_invoice_v1.0.0.json"
    assert payload_file.exists(), f"Golden payload missing: {payload_file}"

    raw_json = payload_file.read_text(encoding="utf-8")
    data = json.loads(raw_json)

    envelope = CanonicalEnvelope.model_validate(data)
    assert envelope.schema_version == "1.0.0"
    assert envelope.document_type == DocumentType.SUPPLIER_INVOICE
    assert isinstance(envelope.payload, SupplierInvoicePayload)

    # Check payload fields
    payload = envelope.payload
    assert payload.document_number.value == "INV-2026-001"
    assert payload.document_date.value is not None
    assert payload.document_date.value.raw == "31/10/2026"
    assert payload.issuer.name.value == "Bharat Textiles Ltd"
    assert len(payload.line_items) == 1
    assert payload.line_items[0].description.value == "100% Cotton Carded Yarn 40s"
    assert payload.line_items[0].line_total.value is not None
    assert str(payload.line_items[0].line_total.value.amount) == "105000.00"

    # Deterministic RFC 8785 hash
    h1 = envelope.rfc8785_hash()
    h2 = envelope.rfc8785_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string


def test_golden_v1_0_0_under_simulated_v1_1_0_upcaster() -> None:
    """Verify loading golden v1.0.0 payload under simulated v1.1.0 using an upcaster (FIN-006)."""
    payload_file = GOLDEN_PAYLOADS_DIR / "supplier_invoice_v1.0.0.json"
    envelope_data = json.loads(payload_file.read_text(encoding="utf-8"))

    # Define a simulated v1.1.0 payload model extending v1.0.0 with a new field
    class SimulatedSupplierInvoicePayloadV11(SupplierInvoicePayload):
        payment_terms: Field[str]

    # Create an upcaster that migrates v1.0.0 payload to v1.1.0 by adding payment_terms
    def upcast_invoice_100_to_110(data: dict[str, Any]) -> dict[str, Any]:
        data["payment_terms"] = {
            "raw": "Net 30",
            "value": "Net 30",
            "status": "present",
            "normalizer_version": None,
            "evidence": [],
        }
        return data

    registry = UpcasterRegistry()
    registry.register("supplier_invoice", "1.0.0", "1.1.0", upcast_invoice_100_to_110)

    # 1. Direct validation under v1.1.0 without upcaster FAILS because payment_terms is required
    with pytest.raises(ValidationError):
        SimulatedSupplierInvoicePayloadV11.model_validate(envelope_data["payload"])

    # 2. Applying the upcaster transforms the payload dict to v1.1.0
    upcasted_payload = registry.upcast(
        "supplier_invoice", envelope_data["payload"], "1.0.0", "1.1.0"
    )

    # 3. Upcasted payload validates successfully under v1.1.0
    v11_instance = SimulatedSupplierInvoicePayloadV11.model_validate(upcasted_payload)
    assert v11_instance.payment_terms.value == "Net 30"
    assert v11_instance.document_number.value == "INV-2026-001"


def test_breaking_change_without_upcaster_fails() -> None:
    """Verify that breaking schema changes without an upcaster fail in CI/validation (FIN-006)."""

    # A hypothetical v2.0.0 schema requires a new mandatory audit field
    class SimulatedV2Envelope(BaseModel):
        model_config = ConfigDict(extra="forbid")
        document_id: str
        schema_version: str
        document_type: str
        compliance_check_id: str  # Mandatory in v2.0.0, absent in v1.0.0
        payload: dict[str, Any]

    payload_file = GOLDEN_PAYLOADS_DIR / "supplier_invoice_v1.0.0.json"
    data = json.loads(payload_file.read_text(encoding="utf-8"))

    # Direct validation fails because compliance_check_id is missing
    with pytest.raises(ValidationError) as exc_info:
        SimulatedV2Envelope.model_validate(data)
    assert "compliance_check_id" in str(exc_info.value)
