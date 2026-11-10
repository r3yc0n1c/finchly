"""Document type payload stubs per ADR-010 §2.

Defines initial typed payloads for credit_note, purchase_order, delivery_challan,
electricity_bill, and unknown documents.
"""

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from finchly_domain.schemas.field import Field
from finchly_domain.schemas.primitives import DateValue, Money


class CreditNotePayload(BaseModel):
    """Stub schema for credit notes."""

    model_config = ConfigDict(frozen=True)

    credit_note_number: Field[str]
    original_invoice_number: Field[str] | None = None
    document_date: Field[DateValue]
    total_amount: Field[Money]
    reason: Field[str] | None = None


class PurchaseOrderPayload(BaseModel):
    """Stub schema for purchase orders."""

    model_config = ConfigDict(frozen=True)

    po_number: Field[str]
    po_date: Field[DateValue]
    buyer_name: Field[str]
    vendor_name: Field[str]
    total_amount: Field[Money] | None = None


class DeliveryChallanPayload(BaseModel):
    """Stub schema for delivery challans."""

    model_config = ConfigDict(frozen=True)

    challan_number: Field[str]
    challan_date: Field[DateValue]
    consignor_name: Field[str]
    consignee_name: Field[str]
    vehicle_number: Field[str] | None = None


class ElectricityBillPayload(BaseModel):
    """Stub schema for electricity bills."""

    model_config = ConfigDict(frozen=True)

    utility_provider: Field[str]
    consumer_account_number: Field[str]
    bill_number: Field[str] | None = None
    bill_date: Field[DateValue]
    due_date: Field[DateValue] | None = None
    amount_due: Field[Money]


class UnknownDocumentPayload(BaseModel):
    """Payload for documents whose classification is unresolved or unsupported."""

    model_config = ConfigDict(frozen=True)

    unclassified_text: str = PydanticField(
        default="",
        description="Captured unclassified raw text snippet for review.",
    )
    detected_keywords: list[str] = PydanticField(
        default_factory=list,
        description="List of domain keywords detected during intake classification.",
    )
