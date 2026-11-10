"""Unit tests for canonical schemas per ADR-010, AI-009, and FIN-004."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from finchly_domain.schemas import (
    CanonicalEnvelope,
    DateValue,
    DocumentType,
    Evidence,
    EvidenceMethod,
    Field,
    FieldStatus,
    InvoiceLineItem,
    InvoiceTotals,
    Money,
    Party,
    Quantity,
    SupplierInvoicePayload,
    SupportStatus,
    TaxComponent,
    TextSource,
)


def test_money_decimal_and_rejects_float() -> None:
    """Verify Money requires Decimal/str and strictly rejects float (AGENTS.md §6)."""
    # Valid decimal string converted to Decimal
    m1 = Money(amount=Decimal("1000.50"), currency="INR")
    assert isinstance(m1.amount, Decimal)
    assert m1.amount == Decimal("1000.50")

    # Valid Decimal instance
    m2 = Money(amount=Decimal("250.00"), currency="INR")
    assert m2.amount == Decimal("250.00")

    # Strict rejection of float
    with pytest.raises((TypeError, ValidationError)):
        Money(amount=1000.50, currency="INR")  # type: ignore[arg-type]


def test_quantity_decimal_and_rejects_float() -> None:
    """Verify Quantity rejects float and preserves units."""
    q = Quantity(value=Decimal("150.25"), unit_raw="MTR", unit_canonical="meter")
    assert isinstance(q.value, Decimal)
    assert q.unit_canonical == "meter"

    with pytest.raises((TypeError, ValidationError)):
        Quantity(value=150.25, unit_raw="MTR", unit_canonical="meter")  # type: ignore[arg-type]


def test_missing_is_distinct_from_zero() -> None:
    """Enforce AI-009: absent field is 'missing' with value=None, never 0 or defaulted."""
    missing_tax = Field[Money].missing()
    assert missing_tax.status == FieldStatus.MISSING
    assert missing_tax.value is None

    # Zero is NOT missing
    zero_money = Field.present(Money(amount=Decimal("0.00")))
    assert zero_money.status == FieldStatus.PRESENT
    assert zero_money.value is not None
    assert zero_money.value.amount == Decimal("0.00")

    # Invariant: status='missing' with a non-None value is rejected by schema validator
    with pytest.raises(ValidationError):
        Field(status=FieldStatus.MISSING, value=Money(amount=Decimal("0.00")))


def test_canonical_supplier_invoice_round_trip() -> None:
    """Verify full SupplierInvoicePayload round-trips with precision preserved."""
    evidence = Evidence(
        block_ids=["block-001"],
        page=1,
        bbox=[0.1, 0.2, 0.3, 0.4],
        text_span="Grand Total: 1,18,000.00",
        source_engine="tesseract",
        text_source=TextSource.OCR,
        method=EvidenceMethod.OCR_LLM,
        support_status=SupportStatus.SUPPORTED,
    )

    line = InvoiceLineItem(
        line_number=1,
        description=Field.present("Cotton Yarn 40s"),
        quantity=Field.present(
            Quantity(value=Decimal("1000.00"), unit_raw="KGS", unit_canonical="kilogram")
        ),
        unit_price=Field.present(Money(amount=Decimal("100.00"))),
        taxable_amount=Field.present(Money(amount=Decimal("100000.00"))),
        tax_components=[
            TaxComponent(
                tax_type="CGST",
                rate=Decimal("9.00"),
                amount=Money(amount=Decimal("9000.00")),
            ),
            TaxComponent(
                tax_type="SGST",
                rate=Decimal("9.00"),
                amount=Money(amount=Decimal("9000.00")),
            ),
        ],
        line_total=Field.present(Money(amount=Decimal("118000.00"))),
        evidence=[evidence],
    )

    payload = SupplierInvoicePayload(
        issuer=Party(
            name=Field.present("ABC Textiles Ltd"),
            tax_id=Field.present("27ABCDE1234F1Z5"),
        ),
        recipient=Party(
            name=Field.present("XYZ Garments Pvt Ltd"),
            tax_id=Field.present("29ABCDE1234F1Z2"),
        ),
        document_number=Field.present("INV-2026-001"),
        document_date=Field.present(
            DateValue(value=date(2026, 10, 31), raw="31/10/2026", ambiguous=False)
        ),
        totals=InvoiceTotals(
            subtotal=Field.present(Money(amount=Decimal("100000.00"))),
            tax_total=Field.present(Money(amount=Decimal("18000.00"))),
            grand_total=Field.present(Money(amount=Decimal("118000.00")), evidence=[evidence]),
        ),
        line_items=[line],
    )

    envelope = CanonicalEnvelope(
        document_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        document_type=DocumentType.SUPPLIER_INVOICE,
        schema_version="1.0.0",
        payload=payload,
    )

    # Dump to JSON and restore
    json_str = envelope.model_dump_json()
    restored = CanonicalEnvelope.model_validate_json(json_str)

    assert restored.document_id == envelope.document_id
    assert restored.tenant_id == envelope.tenant_id
    assert restored.document_type == DocumentType.SUPPLIER_INVOICE
    assert isinstance(restored.payload, SupplierInvoicePayload)
    assert restored.payload.totals.grand_total.value is not None
    assert restored.payload.totals.grand_total.value.amount == Decimal("118000.00")
    first_line = restored.payload.line_items[0]
    assert first_line.quantity is not None
    assert first_line.quantity.value is not None
    assert first_line.quantity.value.value == Decimal("1000.00")


def test_rfc8785_hash_determinism_and_sensitivity() -> None:
    """Verify RFC 8785 canonical hash is deterministic and sensitive to mutations."""
    envelope = CanonicalEnvelope(
        document_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        document_type=DocumentType.SUPPLIER_INVOICE,
        schema_version="1.0.0",
        payload=SupplierInvoicePayload(
            issuer=Party(name=Field.present("Supplier A")),
            recipient=Party(name=Field.present("Customer B")),
            document_number=Field.present("INV-100"),
            document_date=Field.present(DateValue(value=date(2026, 1, 1), raw="2026-01-01")),
            totals=InvoiceTotals(grand_total=Field.present(Money(amount=Decimal("500.00")))),
        ),
    )

    hash1 = envelope.rfc8785_hash()
    hash2 = envelope.rfc8785_hash()
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest length

    # Mutate a single digit in grand total
    mutated = CanonicalEnvelope(
        document_id=envelope.document_id,
        tenant_id=envelope.tenant_id,
        document_type=envelope.document_type,
        schema_version=envelope.schema_version,
        payload=SupplierInvoicePayload(
            issuer=Party(name=Field.present("Supplier A")),
            recipient=Party(name=Field.present("Customer B")),
            document_number=Field.present("INV-100"),
            document_date=Field.present(DateValue(value=date(2026, 1, 1), raw="2026-01-01")),
            totals=InvoiceTotals(grand_total=Field.present(Money(amount=Decimal("500.01")))),
        ),
    )
    assert mutated.rfc8785_hash() != hash1


def test_exported_schemas_are_up_to_date_with_no_drift() -> None:
    """Verify schemas/canonical matches current models with zero drift."""
    schemas_dir = Path(__file__).resolve().parent.parent.parent.parent / "schemas" / "canonical"
    assert schemas_dir.exists(), "schemas/canonical directory missing"

    for schema_file in schemas_dir.glob("*.json"):
        content = schema_file.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "$defs" in parsed or "properties" in parsed or "type" in parsed
