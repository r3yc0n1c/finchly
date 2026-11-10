"""Canonical primitive types conforming to ADR-010.

Enforces:
- Money as Decimal with ISO 4217 currency (never binary float).
- Quantity as Decimal with raw and canonical unit registry tags.
- DateValue as ISO 8601 date with raw preservation and ambiguity flag.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
)
from pydantic import (
    Field as PydanticField,
)

DecimalStr = Annotated[
    Decimal,
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
    """Financial amount with ISO 4217 currency.

    Floats are strictly rejected to guarantee decimal financial arithmetic (AGENTS.md §6).
    """

    model_config = ConfigDict(frozen=True)

    amount: DecimalStr
    currency: str = PydanticField(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (e.g. INR, USD, EUR).",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError("Float is strictly forbidden for Money amounts; use Decimal or string.")
        if isinstance(v, (str, int)):
            return Decimal(str(v))
        return v


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

    @field_validator("value", "secondary_value", mode="before")
    @classmethod
    def reject_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError(
                "Float is strictly forbidden for Quantity values; use Decimal or string."
            )
        if isinstance(v, (str, int)):
            return Decimal(str(v))
        return v


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
