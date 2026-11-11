"""Canonical Supplier Invoice schema conforming to ADR-010 §5 and FINCHLY_SPEC §6."""

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from finchly_domain.schemas.evidence import Evidence
from finchly_domain.schemas.field import Field
from finchly_domain.schemas.primitives import DateValue, DecimalStr, Money, Quantity


class Party(BaseModel):
    """Issuer or recipient party details."""

    model_config = ConfigDict(frozen=True)

    name: Field[str] = PydanticField(..., description="Legal business or trading name.")
    tax_id: Field[str] | None = PydanticField(
        default=None,
        description="Tax identifier (e.g. GSTIN, PAN, VAT number).",
    )
    address: Field[str] | None = PydanticField(
        default=None,
        description="Registered or billing address string.",
    )


class TaxComponent(BaseModel):
    """Itemized tax component (e.g. CGST, SGST, IGST)."""

    model_config = ConfigDict(frozen=True)

    tax_type: str = PydanticField(..., description="Tax category (e.g. CGST, SGST, IGST).")
    rate: DecimalStr | None = PydanticField(
        default=None,
        description="Percentage tax rate (e.g. 9.00 for 9%), or None if unstated.",
    )
    amount: Money = PydanticField(..., description="Calculated or stated tax monetary amount.")


class InvoiceLineItem(BaseModel):
    """Line item extracted from a supplier invoice."""

    model_config = ConfigDict(frozen=True)

    line_number: int = PydanticField(ge=1, description="1-based ordinal line item position.")
    description: Field[str] = PydanticField(..., description="Item or service description.")
    item_code: Field[str] | None = PydanticField(
        default=None,
        description="Supplier SKU or internal product code.",
    )
    hsn_sac: Field[str] | None = PydanticField(
        default=None,
        description="Harmonized System of Nomenclature (HSN) or SAC code.",
    )
    quantity: Field[Quantity] | None = PydanticField(
        default=None,
        description="Billed physical quantity with units.",
    )
    unit_price: Field[Money] | None = PydanticField(
        default=None,
        description="Price per individual unit.",
    )
    discount: Field[Money] | None = PydanticField(
        default=None,
        description="Line-level discount amount.",
    )
    taxable_amount: Field[Money] | None = PydanticField(
        default=None,
        description="Base amount subject to taxation.",
    )
    tax_components: list[TaxComponent] = PydanticField(
        default_factory=list,
        description="Breakdown of taxes levied on this line.",
    )
    line_total: Field[Money] = PydanticField(
        ...,
        description="Total monetary amount for this line including taxes and discounts.",
    )
    evidence: list[Evidence] = PydanticField(
        default_factory=list,
        description="Evidence records citing source rows/cells for this line.",
    )


class InvoiceTotals(BaseModel):
    """Document-level monetary totals per ADR-010 §5."""

    model_config = ConfigDict(frozen=True)

    subtotal: Field[Money] | None = PydanticField(
        default=None,
        description="Sum of item taxable amounts prior to taxes and charges.",
    )
    discount_total: Field[Money] | None = PydanticField(
        default=None,
        description="Document-level trade discount.",
    )
    other_charges_total: Field[Money] | None = PydanticField(
        default=None,
        description="Freight, insurance, packaging or other ancillary charges.",
    )
    tax_total: Field[Money] | None = PydanticField(
        default=None,
        description="Total aggregate tax amount.",
    )
    round_off: Field[Money] | None = PydanticField(
        default=None,
        description="First-class round-off adjustment line.",
    )
    grand_total: Field[Money] = PydanticField(
        ...,
        description="Final payable invoice amount.",
    )


class SupplierInvoicePayload(BaseModel):
    """Canonical payload for a supplier invoice per ADR-010 §5."""

    model_config = ConfigDict(frozen=True)

    issuer: Party = PydanticField(..., description="Selling or billing supplier party.")
    recipient: Party = PydanticField(..., description="Buying or customer party.")
    document_number: Field[str] = PydanticField(..., description="Invoice identifier/number.")
    document_date: Field[DateValue] = PydanticField(
        ..., description="Stated invoice issuance date."
    )
    currency: Field[str] = PydanticField(
        ...,
        description="Stated document currency code (ISO 4217), or missing if unstated.",
    )
    totals: InvoiceTotals = PydanticField(..., description="Aggregate document totals.")
    line_items: list[InvoiceLineItem] = PydanticField(
        default_factory=list,
        description="Collection of extracted invoice line items.",
    )
    references: list[str] = PydanticField(
        default_factory=list,
        description="Referenced purchase orders, delivery challans, or contract numbers.",
    )
    # Captured-only fields per ADR-010 §5 (no compliance claims made)
    reverse_charge: Field[bool] | None = PydanticField(
        default=None,
        description="Captured reverse-charge indication without legal compliance claim.",
    )
    place_of_supply: Field[str] | None = PydanticField(
        default=None,
        description="Captured place of supply (e.g. State code or name).",
    )
    e_invoice_reference: Field[str] | None = PydanticField(
        default=None,
        description="Captured IRN / e-invoice acknowledgement reference.",
    )
