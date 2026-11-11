"""Canonical primitive types conforming to ADR-010.

Enforces:
- Money as Decimal with optional ISO 4217 currency (never binary float).
- Quantity as Decimal with raw and canonical unit registry tags.
- DateValue as ISO 8601 date with raw preservation and ambiguity flag.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    WithJsonSchema,
)
from pydantic import (
    Field as PydanticField,
)


def _validate_decimal(v: Any) -> Decimal:
    """Validate and convert decimal inputs while strictly rejecting floats and booleans.

    Enforces AGENTS.md §6 financial precision rules across all monetary and numeric fields.
    """
    if isinstance(v, bool):
        raise ValueError("Booleans are strictly forbidden as numeric Decimal values.")
    if isinstance(v, float):
        raise ValueError("Float is strictly forbidden for Decimal values; use Decimal or string.")
    if isinstance(v, (str, int)):
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Malformed decimal value '{v}': {exc}") from exc
    elif isinstance(v, Decimal):
        d = v
    else:
        raise ValueError(f"Unsupported type {type(v).__name__} for Decimal field.")

    if not d.is_finite():
        raise ValueError(f"Non-finite Decimal value '{d}' is strictly forbidden.")

    return d


DecimalStr = Annotated[
    Decimal,
    BeforeValidator(_validate_decimal),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "description": "Decimal represented as a string to guarantee exact financial precision.",
        }
    ),
]


class DocumentType(StrEnum):
    """Closed enumeration of document types per ADR-010 §2."""

    SUPPLIER_INVOICE = "supplier_invoice"
    CREDIT_NOTE = "credit_note"
    PURCHASE_ORDER = "purchase_order"
    DELIVERY_CHALLAN = "delivery_challan"
    ELECTRICITY_BILL = "electricity_bill"
    UNKNOWN = "unknown"


class FieldStatus(StrEnum):
    """Field status indicating extraction and support disposition per ADR-010 §3."""

    PRESENT = "present"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    DERIVED = "derived"
    UNSUPPORTED = "unsupported"


class Money(BaseModel):
    """Financial amount with optional ISO 4217 currency.

    Floats and booleans are strictly rejected to guarantee decimal financial arithmetic (AGENTS.md §6).
    If currency is not present on the document, it remains None rather than fabricating a default.
    """

    model_config = ConfigDict(frozen=True)

    amount: DecimalStr
    currency: str | None = PydanticField(
        default=None,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (e.g. INR, USD, EUR) if stated on document, or None if absent.",
    )


class Quantity(BaseModel):
    """Physical quantity with raw and canonical unit representations.

    Supports primary quantity and optional secondary quantity.
    """

    model_config = ConfigDict(frozen=True)

    value: DecimalStr
    unit_raw: str = PydanticField(
        ..., description="Unit string exactly as written on the document."
    )
    unit_canonical: str = PydanticField(..., description="Canonical unit identifier from registry.")
    secondary_value: DecimalStr | None = None
    secondary_unit: str | None = None


class DateValue(BaseModel):
    """Date representation retaining raw text and ambiguity status per ADR-010 §4."""

    model_config = ConfigDict(frozen=True)

    value: date | None = PydanticField(
        default=None,
        description="Normalized ISO 8601 calendar date (YYYY-MM-DD), or None if unparseable.",
    )
    raw: str = PydanticField(..., description="Raw date string from source document.")
    ambiguous: bool = PydanticField(
        default=False,
        description="True if format is ambiguous (e.g. 04/05/2026 where DD/MM vs MM/DD is unresolved).",
    )
