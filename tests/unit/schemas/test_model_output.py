"""Unit tests for untrusted ModelOutput schema per ADR-010 §1, AI-005, AI-006, and FIN-005."""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from finchly_domain.schemas.model_output import (
    ModelLineItem,
    ModelOutput,
    ModelParty,
    ModelTaxComponent,
    ModelTotals,
)


def test_valid_minimal_model_output_parses() -> None:
    """Verify valid minimal ModelOutput parses cleanly with raw text strings and citations."""
    raw_output = {
        "document_type_hint": "supplier_invoice",
        "cited_block_ids": ["b1", "b2"],
        "invoice": {
            "issuer": {
                "name": "Textile Mills Ltd",
                "tax_id": "27ABCDE1234F1Z5",
                "cited_block_ids": ["b1"],
            },
            "recipient": {
                "name": "Garments Co",
                "tax_id": "29ABCDE1234F1Z2",
                "cited_block_ids": ["b2"],
            },
            "document_number": "INV-1001",
            "document_date": "2026-10-31",
            "currency": "INR",
            "totals": {
                "subtotal": "100000.00",
                "tax_total": "18000.00",
                "grand_total": "118000.00",
                "cited_block_ids": ["b3"],
            },
            "line_items": [
                {
                    "description": "Cotton Yarn",
                    "quantity": "500",
                    "unit": "KGS",
                    "unit_price": "200.00",
                    "line_total": "100000.00",
                    "tax_components": [
                        {
                            "tax_type": "CGST",
                            "rate": "9%",
                            "amount": "9000.00",
                            "cited_block_ids": ["b4"],
                        }
                    ],
                    "cited_block_ids": ["b4"],
                }
            ],
            "cited_block_ids": ["b1", "b2", "b3"],
        },
    }

    parsed = ModelOutput.model_validate(raw_output)
    assert parsed.document_type_hint == "supplier_invoice"
    assert parsed.invoice is not None
    assert parsed.invoice.issuer.name == "Textile Mills Ltd"
    assert parsed.invoice.totals.grand_total == "118000.00"
    assert len(parsed.invoice.line_items) == 1
    assert parsed.invoice.line_items[0].tax_components[0].rate == "9%"


def test_model_output_rejects_extra_keys_at_all_levels() -> None:
    """Verify extra=forbid rejects any unexpected keys at top level and nested models (AI-005)."""
    # Extra key at top level
    with pytest.raises(ValidationError) as exc_info:
        ModelOutput.model_validate({"unexpected_key": "value"})
    assert "extra_forbidden" in str(exc_info.value)

    # Extra key in totals
    with pytest.raises(ValidationError) as exc_info:
        ModelTotals.model_validate(
            {
                "grand_total": "500.00",
                "hallucinated_total": "100.00",
            }
        )
    assert "extra_forbidden" in str(exc_info.value)

    # Extra key in line item
    with pytest.raises(ValidationError) as exc_info:
        ModelLineItem.model_validate(
            {
                "description": "Item A",
                "line_total": "50.00",
                "invented_sku_category": "fabrics",
            }
        )
    assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.parametrize(
    "system_field",
    [
        "document_id",
        "tenant_id",
        "schema_version",
        "validation",
        "evidence_id",
        "normalizer_version",
        "status",
        "normalized_value",
    ],
)
def test_model_output_rejects_system_owned_fields(system_field: str) -> None:
    """Verify system-owned authoritative fields are rejected if supplied by model (ADR-010 §1)."""
    with pytest.raises(ValidationError) as exc_info:
        ModelOutput.model_validate({system_field: "system_generated_value"})
    assert "extra_forbidden" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        ModelParty.model_validate(
            {
                "name": "Supplier A",
                system_field: "injected_value",
            }
        )
    assert "extra_forbidden" in str(exc_info.value)


def test_model_output_rejects_normalized_numerics_and_booleans() -> None:
    """Verify model output rejects float, int, Decimal, and bool (AI-006: raw text only)."""
    # Rejects float in totals
    with pytest.raises(ValidationError) as exc_info:
        ModelTotals.model_validate({"grand_total": 118000.50})
    assert "Normalized numerics" in str(exc_info.value)

    # Rejects integer in totals
    with pytest.raises(ValidationError) as exc_info:
        ModelTotals.model_validate({"grand_total": 1000})
    assert "Normalized numerics" in str(exc_info.value)

    # Rejects Decimal in totals
    with pytest.raises(ValidationError) as exc_info:
        ModelTotals.model_validate({"grand_total": Decimal("1000.00")})
    assert "Normalized numerics" in str(exc_info.value)

    # Rejects boolean in totals or party
    with pytest.raises(ValidationError) as exc_info:
        ModelParty.model_validate({"name": True})
    assert "Booleans are forbidden" in str(exc_info.value)

    # Rejects float in tax component rate
    with pytest.raises(ValidationError) as exc_info:
        ModelTaxComponent.model_validate(
            {
                "tax_type": "CGST",
                "rate": 9.0,
                "amount": "900.00",
            }
        )
    assert "Normalized numerics" in str(exc_info.value)


def test_model_output_schema_file_matches_zero_drift() -> None:
    """Verify schemas/model_output/model_output.json matches current ModelOutput model."""
    schema_path = (
        Path(__file__).resolve().parents[3] / "schemas" / "model_output" / "model_output.json"
    )
    assert schema_path.exists(), "schemas/model_output/model_output.json missing"
    committed_content = schema_path.read_text(encoding="utf-8")
    import json

    current_schema = json.dumps(ModelOutput.model_json_schema(), indent=2, sort_keys=True) + "\n"
    assert committed_content == current_schema, (
        "Schema drift detected in schemas/model_output/model_output.json"
    )
