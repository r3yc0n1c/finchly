"""Untrusted ModelOutput schema conforming to ADR-010 Decision 1, AI-005, and AI-006.

Enforces:
1. 'extra=forbid' on all models: any extra keys trigger immediate validation failure.
2. Complete exclusion of system-owned fields (document_id, tenant_id, schema_version, validation, status, etc.).
3. Raw text strings only: normalized numerics (float, int, Decimal) and booleans are strictly rejected.
4. Block-level evidence citations linking extracted snippets to source visual/OCR block IDs.
"""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
)
from pydantic import (
    Field as PydanticField,
)

SYSTEM_OWNED_FIELDS: frozenset[str] = frozenset(
    {
        "document_id",
        "tenant_id",
        "schema_version",
        "validation",
        "evidence_id",
        "normalizer_version",
        "status",
        "normalized_value",
    }
)


def _validate_raw_text(v: Any) -> str:
    """Validate that value is strictly a raw text string.

    Rejects numerics (float, int, Decimal) and booleans per AI-006:
    the model must never produce normalized business data or arithmetic.
    """
    if isinstance(v, bool):
        raise ValueError("Booleans are forbidden in ModelOutput; raw text only.")
    if isinstance(v, (int, float, Decimal)):
        raise ValueError(
            f"Normalized numerics ({type(v).__name__}) are forbidden in ModelOutput; raw text strings only."
        )
    if not isinstance(v, str):
        raise ValueError(f"Field must be a raw string, got {type(v).__name__}.")
    return v


RawTextStr = Annotated[
    str,
    BeforeValidator(_validate_raw_text),
    PydanticField(description="Unprocessed raw text as extracted directly by the model."),
]


class UntrustedModelBase(BaseModel):
    """Base model for untrusted model extractions with strict key forbidding."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class ModelParty(UntrustedModelBase):
    """Untrusted raw extraction for issuer or recipient party."""

    name: RawTextStr = PydanticField(..., description="Raw party name extracted from document.")
    tax_id: RawTextStr | None = PydanticField(
        default=None,
        description="Raw tax identifier string (GSTIN, PAN, etc.) if extracted.",
    )
    address: RawTextStr | None = PydanticField(
        default=None,
        description="Raw address text if extracted.",
    )
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Source block IDs citing this party extraction.",
    )


class ModelTaxComponent(UntrustedModelBase):
    """Untrusted raw line-level tax component."""

    tax_type: RawTextStr = PydanticField(
        ..., description="Raw tax type string (e.g. 'CGST', 'SGST')."
    )
    rate: RawTextStr | None = PydanticField(
        default=None,
        description="Raw tax rate string (e.g. '9%') if extracted.",
    )
    amount: RawTextStr = PydanticField(..., description="Raw tax amount string.")
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Source block IDs citing this tax component.",
    )


class ModelLineItem(UntrustedModelBase):
    """Untrusted raw invoice line item."""

    line_number: RawTextStr | None = PydanticField(
        default=None,
        description="Raw line number string if stated.",
    )
    description: RawTextStr = PydanticField(..., description="Raw item description text.")
    item_code: RawTextStr | None = PydanticField(
        default=None,
        description="Raw product code or SKU string.",
    )
    hsn_sac: RawTextStr | None = PydanticField(
        default=None,
        description="Raw HSN or SAC code string.",
    )
    quantity: RawTextStr | None = PydanticField(
        default=None,
        description="Raw quantity string (e.g. '100', '1,000.5').",
    )
    unit: RawTextStr | None = PydanticField(
        default=None,
        description="Raw unit string (e.g. 'KGS', 'MTR', 'PCS').",
    )
    unit_price: RawTextStr | None = PydanticField(
        default=None,
        description="Raw rate/unit price string.",
    )
    discount: RawTextStr | None = PydanticField(
        default=None,
        description="Raw line discount string.",
    )
    taxable_amount: RawTextStr | None = PydanticField(
        default=None,
        description="Raw taxable value string.",
    )
    tax_components: list[ModelTaxComponent] = PydanticField(
        default_factory=list,
        description="Raw tax components for this line.",
    )
    line_total: RawTextStr = PydanticField(..., description="Raw line total amount string.")
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Source block IDs citing this line item.",
    )


class ModelTotals(UntrustedModelBase):
    """Untrusted raw totals extracted from invoice."""

    subtotal: RawTextStr | None = PydanticField(
        default=None,
        description="Raw subtotal amount string.",
    )
    discount_total: RawTextStr | None = PydanticField(
        default=None,
        description="Raw document-level discount string.",
    )
    other_charges_total: RawTextStr | None = PydanticField(
        default=None,
        description="Raw freight or ancillary charges string.",
    )
    tax_total: RawTextStr | None = PydanticField(
        default=None,
        description="Raw total tax amount string.",
    )
    round_off: RawTextStr | None = PydanticField(
        default=None,
        description="Raw round-off amount string.",
    )
    grand_total: RawTextStr = PydanticField(..., description="Raw grand total amount string.")
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Source block IDs citing document totals.",
    )


class ModelSupplierInvoice(UntrustedModelBase):
    """Untrusted raw extraction for a supplier invoice."""

    issuer: ModelParty = PydanticField(..., description="Raw seller party extraction.")
    recipient: ModelParty = PydanticField(..., description="Raw buyer party extraction.")
    document_number: RawTextStr = PydanticField(..., description="Raw invoice number string.")
    document_date: RawTextStr = PydanticField(..., description="Raw invoice date string.")
    currency: RawTextStr | None = PydanticField(
        default=None,
        description="Raw currency symbol or code if explicitly present.",
    )
    totals: ModelTotals = PydanticField(..., description="Raw document totals extraction.")
    line_items: list[ModelLineItem] = PydanticField(
        default_factory=list,
        description="Collection of raw extracted line items.",
    )
    references: list[RawTextStr] = PydanticField(
        default_factory=list,
        description="Raw referenced PO or challan strings.",
    )
    reverse_charge: RawTextStr | None = PydanticField(
        default=None,
        description="Raw reverse charge indicator string.",
    )
    place_of_supply: RawTextStr | None = PydanticField(
        default=None,
        description="Raw place of supply string.",
    )
    e_invoice_reference: RawTextStr | None = PydanticField(
        default=None,
        description="Raw IRN or e-invoice acknowledgment string.",
    )
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Document-level cited source block IDs.",
    )


class ModelOutput(UntrustedModelBase):
    """Top-level untrusted extraction output produced directly by model inference.

    Conforms strictly to ADR-010 §1: contains raw text only, no system-owned keys,
    and extra=forbid to reject any unexpected or authoritative data.
    """

    document_type_hint: RawTextStr | None = PydanticField(
        default=None,
        description="Model-suggested document classification hint.",
    )
    invoice: ModelSupplierInvoice | None = PydanticField(
        default=None,
        description="Extracted supplier invoice raw details if classified as an invoice.",
    )
    cited_block_ids: list[str] = PydanticField(
        default_factory=list,
        description="Top-level block IDs referenced by the model.",
    )
