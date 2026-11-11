"""Unit tests for canonical schemas per ADR-010, AI-009, and FIN-004."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import rfc8785
from pydantic import ValidationError

from finchly_domain.schemas import (
    CanonicalEnvelope,
    CreditNotePayload,
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
from finchly_domain.schemas.exporter import export_all_schemas


def test_money_decimal_and_rejects_invalid_types() -> None:
    """Verify Money requires Decimal/str, rejects float/bool, and allows omitted currency."""
    # Valid Decimal instance
    m1 = Money(amount=Decimal("1000.50"), currency="INR")
    assert isinstance(m1.amount, Decimal)
    assert m1.amount == Decimal("1000.50")
    assert m1.currency == "INR"

    # Omitted currency remains None (not fabricated as INR)
    m2 = Money(amount=Decimal("250.00"))
    assert m2.amount == Decimal("250.00")
    assert m2.currency is None

    # Strict rejection of float
    with pytest.raises(ValidationError):
        Money(amount=1000.50, currency="INR")  # type: ignore[arg-type]

    # Strict rejection of boolean
    with pytest.raises(ValidationError):
        Money(amount=True, currency="INR")  # type: ignore[arg-type]

    # Malformed string
    with pytest.raises(ValidationError):
        Money(amount="not_a_number", currency="INR")  # type: ignore[arg-type]


def test_quantity_decimal_and_rejects_float() -> None:
    """Verify Quantity rejects float and preserves units."""
    q = Quantity(value=Decimal("150.25"), unit_raw="MTR", unit_canonical="meter")
    assert isinstance(q.value, Decimal)
    assert q.unit_canonical == "meter"

    with pytest.raises(ValidationError):
        Quantity(value=150.25, unit_raw="MTR", unit_canonical="meter")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        Quantity(value=True, unit_raw="MTR", unit_canonical="meter")  # type: ignore[arg-type]


def test_tax_component_rate_rejects_float() -> None:
    """Verify TaxComponent.rate validates via DecimalStr and rejects float."""
    tc = TaxComponent(
        tax_type="CGST",
        rate=Decimal("9.00"),
        amount=Money(amount=Decimal("900.00"), currency="INR"),
    )
    assert tc.rate == Decimal("9.00")

    with pytest.raises(ValidationError):
        TaxComponent(
            tax_type="CGST",
            rate=9.00,  # type: ignore[arg-type]
            amount=Money(amount=Decimal("900.00"), currency="INR"),
        )


def test_evidence_bounding_box_validation() -> None:
    """Verify bounding box requires 4 coordinates within [0.0, 1.0] and valid order."""
    # Valid bbox
    ev = Evidence(
        page=1,
        bbox=[0.1, 0.2, 0.5, 0.8],
        text_span="Total",
        source_engine="tesseract",
        text_source=TextSource.OCR,
        method=EvidenceMethod.OCR_LLM,
    )
    assert ev.bbox == [0.1, 0.2, 0.5, 0.8]

    # Less than 4 coordinates
    with pytest.raises(ValidationError):
        Evidence(
            page=1,
            bbox=[0.1, 0.2, 0.3],
            text_span="Total",
            source_engine="tesseract",
            text_source=TextSource.OCR,
            method=EvidenceMethod.OCR_LLM,
        )

    # Coordinate out of range [0.0, 1.0]
    with pytest.raises(ValidationError):
        Evidence(
            page=1,
            bbox=[0.1, 0.2, 1.5, 0.8],
            text_span="Total",
            source_engine="tesseract",
            text_source=TextSource.OCR,
            method=EvidenceMethod.OCR_LLM,
        )

    # ymin > ymax
    with pytest.raises(ValidationError):
        Evidence(
            page=1,
            bbox=[0.7, 0.2, 0.5, 0.8],
            text_span="Total",
            source_engine="tesseract",
            text_source=TextSource.OCR,
            method=EvidenceMethod.OCR_LLM,
        )

    # xmin > xmax
    with pytest.raises(ValidationError):
        Evidence(
            page=1,
            bbox=[0.1, 0.9, 0.5, 0.8],
            text_span="Total",
            source_engine="tesseract",
            text_source=TextSource.OCR,
            method=EvidenceMethod.OCR_LLM,
        )


def test_missing_is_distinct_from_zero_and_requires_status() -> None:
    """Enforce AI-009: absent field is 'missing' with value=None; present requires value."""
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

    # Invariant: status='present' with value=None is rejected
    with pytest.raises(ValidationError):
        Field(status=FieldStatus.PRESENT, value=None)

    # Invariant: status='derived' with value=None is rejected
    with pytest.raises(ValidationError):
        Field(status=FieldStatus.DERIVED, value=None)


def test_envelope_payload_document_type_matching() -> None:
    """Verify CanonicalEnvelope rejects payloads whose type does not match document_type."""
    credit_payload = CreditNotePayload(
        credit_note_number=Field.present("CN-001"),
        document_date=Field.present(DateValue(value=date(2026, 1, 1), raw="01/01/2026")),
        total_amount=Field.present(Money(amount=Decimal("50.00"))),
    )

    # Attempting to assign CreditNotePayload to SUPPLIER_INVOICE document_type must fail
    with pytest.raises(ValidationError):
        CanonicalEnvelope(
            document_id="00000000-0000-0000-0000-000000000001",
            tenant_id="00000000-0000-0000-0000-000000000002",
            document_type=DocumentType.SUPPLIER_INVOICE,
            payload=credit_payload,  # Mismatched!
        )


def test_rfc8785_canonicalization_known_vectors() -> None:
    """Verify RFC 8785 canonicalization against official JCS vectors."""
    # 1.0 canonicalizes to 1
    assert rfc8785.dumps({"number": 1.0}) == b'{"number":1}'

    # 1e-7 canonicalizes to 1e-7 per ECMAScript specification
    assert rfc8785.dumps({"small": 1e-7}) == b'{"small":1e-7}'

    # Key ordering follows UTF-16 code units
    data = {"b": 2, "a": 1, "\u00e9": 3}
    assert rfc8785.dumps(data) == b'{"a":1,"b":2,"\xc3\xa9":3}'


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
        currency=Field.present("INR"),
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
    """Verify RFC 8785 canonical payload hash is deterministic and sensitive to mutations."""
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
            currency=Field.present("INR"),
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
            currency=Field.present("INR"),
            totals=InvoiceTotals(grand_total=Field.present(Money(amount=Decimal("500.01")))),
        ),
    )
    assert mutated.rfc8785_hash() != hash1


def test_exported_schemas_are_up_to_date_with_no_drift(tmp_path: Path) -> None:
    """Verify schemas directory matches current models with zero drift."""
    committed_root = Path(__file__).resolve().parents[3] / "schemas"
    assert committed_root.exists(), "schemas directory missing"

    # Export to temp directory
    exported_files = export_all_schemas(target_dir=tmp_path)
    generated_rel_paths = {f.relative_to(tmp_path) for f in exported_files}
    committed_rel_paths = {f.relative_to(committed_root) for f in committed_root.glob("*/*.json")}

    assert generated_rel_paths == committed_rel_paths, (
        f"Schema file set mismatch: extra={committed_rel_paths - generated_rel_paths}, missing={generated_rel_paths - committed_rel_paths}"
    )

    for rel_path in generated_rel_paths:
        generated_content = (tmp_path / rel_path).read_text(encoding="utf-8")
        committed_content = (committed_root / rel_path).read_text(encoding="utf-8")
        assert generated_content == committed_content, (
            f"Schema drift detected in schemas/{rel_path}"
        )
